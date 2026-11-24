"""常驻音频流 + 自绘混音器。

替代 QMediaPlayer 的老路：老实现每炮都要 stop()、换源、重开声卡流，
一路下来有 50 ms 量级的重新灌缓冲，还会因为素材采样率不同而反复重配设备。

这里的做法：
* 解码和重采样只在第一次用到时做一次，之后常驻内存（float32 / 设备采样率 / 双声道）；
* 声卡流在启动时开一次，常驻不关，空闲时照常写静音；
* 一炮 = 往混音器里加一个"声部"，不碰设备；
* 起播和收尾各有几毫秒淡入淡出，被下一炮打断时淡出而不是硬切；
* 整个音频线程独立，主线程卡住不影响出声。

如果设备打不开或格式不支持，is_ready() 会返回 False，调用方回退到老的 AudioPlayer。
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Iterable

import av
import numpy as np
from PySide6.QtCore import QIODevice, QObject, QThread, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

FADE_MS = 8.0          # 起播/收尾的淡入淡出
RESTART_FADE_MS = 3.0   # 同一素材重触发时，旧声部收得多快
MAX_VOICES = 0         # 同时最多几路；0 = 不限（声部只是引用，不复制 PCM）
BUS_CURVE = 0.35       # 总线增益随路数衰减的指数：1 路 = 0 dB，8 路 ≈ +3 dB
BUS_TAU_MS = 50.0      # 总线增益的变化时间常数，避免路数跳变造成台阶
SOFT_KNEE = 0.85       # 超过这个电平开始软限幅，避免多声部相加后硬削
DUCK_LEVEL = 0.22      # 新的一炮起声时，已在响的声部压到多少（≈ -13 dB）
DUCK_ATTACK_MS = 4.0   # 压下去要多快（太快会咔，太慢新一炮起声又被掩蔽）
DUCK_HOLD_MS = 140     # 压住不动多久，再把位置让回去
DUCK_RECOVER_MS = 420  # 恢复时长：慢一点才有"被顶开"的层次感
BUFFER_MS = 20         # 设备缓冲：实测 40→20 ms 能把起播延迟砍掉约 23 ms
BYTES_PER_FRAME = 8    # float32 双声道


def decode_clip(path: Path, rate: int, channels: int = 2) -> np.ndarray | None:
    """把任意格式解成 (frames, channels) 的 float32，一次到位。"""
    source_channels = 0
    try:
        with av.open(str(path), timeout=5.0) as container:
            if not container.streams.audio:
                return None
            stream = container.streams.audio[0]
            source_channels = stream.codec_context.channels or 1
            layout = "stereo" if channels == 2 else "mono"
            resampler = av.AudioResampler(format="fltp", layout=layout, rate=rate)
            blocks: list[np.ndarray] = []
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    blocks.append(out.to_ndarray())
            for out in resampler.resample(None):
                blocks.append(out.to_ndarray())
    except Exception:
        return None

    if not blocks:
        return None

    planes: list[np.ndarray] = []
    for block in blocks:
        if block.ndim == 1:
            block = block.reshape(1, -1)
        elif block.shape[0] > block.shape[1]:
            block = block.T
        planes.append(block)

    data = np.concatenate(planes, axis=1)
    if data.shape[0] == 1 and channels == 2:
        data = np.repeat(data, 2, axis=0)
    if data.shape[0] < channels:
        data = np.repeat(data, channels, axis=0)
    result = data.T[: data.shape[1], :channels].astype(np.float32)
    if source_channels == 1 and channels == 2:
        # swr 的 mono→stereo 是等功率矩阵，每声道会低 3 dB；
        # 这里补回来，免得单声道素材比立体声素材听起来小声。
        result = result * np.float32(np.sqrt(2.0))
    np.clip(result, -1.0, 1.0, out=result)
    return np.ascontiguousarray(result)


class _Voice:
    __slots__ = (
        "data", "pos", "gain", "fade_in", "fade_out", "stop_pos", "key",
        "duck", "duck_target", "duck_recover_at",
    )

    def __init__(
        self,
        data: np.ndarray,
        gain: float,
        fade_in: int,
        fade_out: int,
        key: str = "",
    ) -> None:
        self.data = data
        self.pos = 0
        self.gain = float(max(0.0, min(gain, 1.0)))
        self.fade_in = max(1, fade_in)
        self.fade_out = max(1, fade_out)
        self.stop_pos: int | None = None
        self.key = key
        # 侧链闪避：新的一炮起声时，正在响的声部先被压下去再慢慢回来
        self.duck = 1.0
        self.duck_target = 1.0
        self.duck_recover_at = 0.0

    def dying(self) -> bool:
        return self.stop_pos is not None

    def finished(self) -> bool:
        end = len(self.data)
        if self.stop_pos is not None:
            end = min(end, self.stop_pos + self.fade_out)
        return self.pos >= end


class _MixerIO(QIODevice):
    def __init__(self, worker: "_AudioWorker") -> None:
        super().__init__()
        self._worker = worker

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        return 1 << 16

    def readData(self, maxlen: int) -> bytes:  # noqa: N802 (Qt 接口)
        return self._worker.fill(maxlen)

    def writeData(self, data) -> int:  # noqa: N802
        return 0


class _AudioWorker(QThread):
    readyChanged = Signal(bool, str)

    def __init__(self, commands: queue.SimpleQueue) -> None:
        super().__init__()
        self._commands = commands
        self._voices: list[_Voice] = []
        self._clips: dict[str, np.ndarray] = {}
        self._rate = 0
        self._silence = b""
        self._sink: QAudioSink | None = None
        self._sink_ok = False
        self._frames_served = 0
        self._detail = ""
        self._bus_gain = 1.0

    # ── 主循环 ───────────────────────────────────────────────────────────
    def run(self) -> None:
        device = QMediaDevices.defaultAudioOutput()
        fmt = self._pick_format(device)
        if fmt is None:
            self.readyChanged.emit(False, "找不到能用的输出格式")
            return

        self._rate = fmt.sampleRate()
        io = _MixerIO(self)
        io.open(QIODevice.OpenModeFlag.ReadOnly)
        sink = QAudioSink(device, fmt)
        sink.setBufferSize(max(int(self._rate * BYTES_PER_FRAME * BUFFER_MS / 1000), 8192))
        sink.start(io)
        self._sink = sink

        # start() 之后状态是异步的，判定"就绪"以真的收到音频请求为准
        self._detail = f"{device.description()} / {fmt.sampleRate()} Hz / {fmt.channelCount()} ch"
        QTimer.singleShot(400, self._verify_stream)
        self.exec()

        self._sink = None
        sink.stop()

    def _verify_stream(self) -> None:
        if self._frames_served > 0:
            self.readyChanged.emit(True, self._detail)
            return
        name = self._sink.error().name if self._sink is not None else "?"
        self.readyChanged.emit(False, f"音频流没有回数据（{name}）")

    def _pick_format(self, device) -> QAudioFormat | None:
        candidates: list[tuple[int, QAudioFormat.SampleFormat]] = [
            (device.preferredFormat().sampleRate(), QAudioFormat.SampleFormat.Float),
            (96000, QAudioFormat.SampleFormat.Float),
            (48000, QAudioFormat.SampleFormat.Float),
            (44100, QAudioFormat.SampleFormat.Float),
        ]
        for rate, sample_format in candidates:
            if rate <= 0:
                continue
            fmt = QAudioFormat()
            fmt.setSampleRate(int(rate))
            fmt.setChannelCount(2)
            fmt.setSampleFormat(sample_format)
            if device.isFormatSupported(fmt):
                return fmt
        return None

    # ── 供 QIODevice 调用（在音频线程上）────────────────────────────────
    def fill(self, maxlen: int) -> bytes:
        frames = maxlen // BYTES_PER_FRAME
        if frames <= 0:
            return b""
        self._frames_served += frames

        self._drain_commands()
        if not self._voices:
            # 静音期间没有信号可缩放，把总线增益直接复位，
            # 免得下一炮从压低的状态里爬起来（会听到一个渐强）
            self._bus_gain = 1.0
            if len(self._silence) != frames * BYTES_PER_FRAME:
                self._silence = bytes(frames * BYTES_PER_FRAME)
            return self._silence

        out = np.zeros((frames, 2), dtype=np.float32)
        survivors: list[_Voice] = []
        for voice in self._voices:
            total = len(voice.data)
            take = min(frames, total - voice.pos)
            if take > 0:
                idx = np.arange(voice.pos, voice.pos + take)
                envelope = np.ones(take, dtype=np.float32)
                if voice.fade_in:
                    envelope *= np.clip((idx + 1) / voice.fade_in, 0.0, 1.0)
                if voice.fade_out:
                    envelope *= np.clip((total - idx) / voice.fade_out, 0.0, 1.0)
                if voice.stop_pos is not None:
                    envelope *= np.clip(
                        (voice.stop_pos + voice.fade_out - idx) / voice.fade_out, 0.0, 1.0
                    )
                # 侧链闪避：被新的一炮压下去时用快攻，回涨用慢放。
                # 压的过程跨整块线性过渡，不会有台阶。
                if voice.duck_target < 1.0 and time.monotonic() >= voice.duck_recover_at:
                    voice.duck_target = 1.0
                duck_start = voice.duck
                if duck_start != voice.duck_target:
                    span_ms = take / self._rate * 1000.0
                    tau = DUCK_ATTACK_MS if voice.duck_target < duck_start else DUCK_RECOVER_MS
                    coef = min(1.0, span_ms / tau) if tau > 0 else 1.0
                    voice.duck = duck_start + (voice.duck_target - duck_start) * coef
                if duck_start != 1.0 or voice.duck != 1.0:
                    envelope *= np.linspace(
                        duck_start, voice.duck, take, dtype=np.float32
                    )
                out[:take] += voice.data[voice.pos : voice.pos + take] * (
                    envelope * voice.gain
                )[:, None]
                voice.pos += take
            if not voice.finished():
                survivors.append(voice)

        self._voices = survivors

        # 总线增益：路数越多，每一路越轻。8 路时总响度只比单路高约 3 dB，
        # 而不是随路数线性爆炸；增益本身按时间常数缓动，避免路数变化出台阶。
        count = max(1, len(self._voices))
        target = float(count) ** -BUS_CURVE
        block_ms = frames / self._rate * 1000.0 if self._rate else 20.0
        coefficient = min(1.0, block_ms / BUS_TAU_MS) if BUS_TAU_MS > 0 else 1.0
        start_gain = self._bus_gain
        self._bus_gain = start_gain + (target - start_gain) * coefficient

        if abs(self._bus_gain - 1.0) > 1e-4 or abs(start_gain - 1.0) > 1e-4:
            ramp = np.linspace(start_gain, self._bus_gain, frames, dtype=np.float32)
            out *= ramp[:, None]

        peak = float(np.max(np.abs(out))) if frames else 0.0
        if peak > SOFT_KNEE:
            # 多声部叠加接近满幅时软限幅，避免硬削产生刺耳失真
            sign = np.sign(out)
            over = np.abs(out)
            out = sign * (
                SOFT_KNEE + (1.0 - SOFT_KNEE) * np.tanh((over - SOFT_KNEE) / (1.0 - SOFT_KNEE))
            )
        return out.tobytes()

    def _drain_commands(self) -> None:
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            kind = command[0]
            if kind == "clip":
                self._clips[command[1]] = command[2]
            elif kind == "play":
                _, key, data, volume = command
                self._clips.setdefault(key, data)
                self._start_voice(key, data, volume)
            elif kind == "stop":
                self._stop_all()
            elif kind == "quit":
                self.quit()

    def _start_voice(self, key: str, data: np.ndarray, volume: float) -> None:
        """新的一炮立刻起声，不排队、不等上一炮。

        同一素材重复触发时把旧的那一份收掉（否则两路同相位叠在一起会发闷）；
        设了上限时，超过上限就让最老的那一路淡出，绝不硬切。

        已经在响的声部全部被压低（侧链闪避）：不打断、不缩短，只是让出位置，
        这样新一炮的起声不会被前面几路盖住，密集连杀也听得出一炮一炮。
        """
        fade_in = int(self._rate * FADE_MS / 1000)
        fade_out = int(self._rate * FADE_MS / 1000)
        short = int(self._rate * RESTART_FADE_MS / 1000)

        for voice in self._voices:
            if voice.key == key and not voice.dying():
                voice.stop_pos = voice.pos
                voice.fade_out = short
            if not voice.dying():
                voice.duck_target = DUCK_LEVEL
                voice.duck_recover_at = time.monotonic() + DUCK_HOLD_MS / 1000.0

        active = [v for v in self._voices if not v.dying()]
        while MAX_VOICES > 0 and len(active) >= MAX_VOICES:
            oldest = active.pop(0)
            oldest.stop_pos = oldest.pos
            oldest.fade_out = short

        self._voices.append(_Voice(data, volume, fade_in, fade_out, key))

    def _stop_all(self) -> None:
        for voice in self._voices:
            if voice.stop_pos is None:
                voice.stop_pos = voice.pos


class AudioEngine(QObject):
    """对外只有 play / stop / preload / is_ready，和老的 AudioPlayer 语义一致。"""

    error = Signal(str)
    stateChanged = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._commands: queue.SimpleQueue = queue.SimpleQueue()
        self._clips: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()
        self._worker = _AudioWorker(self._commands)
        self._worker.readyChanged.connect(self._on_ready)
        self._ready = False
        self._detail = "未启动"
        self._clip_rate = 0
        self._pending: list[Path] = []

    # ── 生命周期 ─────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._worker.isRunning():
            return
        self._worker.start()

    def shutdown(self) -> None:
        self._commands.put(("stop",))
        self._commands.put(("quit",))
        if self._worker.isRunning():
            self._worker.wait(1500)
        self._ready = False

    def _on_ready(self, ok: bool, detail: str) -> None:
        if ok:
            rate = self._worker._rate
            if rate and rate != self._clip_rate:
                # 设备采样率变了，旧缓存得按新采样率重建
                self._clips.clear()
                self._clip_rate = rate
        self._ready = ok
        self._detail = detail
        self.stateChanged.emit(ok, detail)
        if not ok:
            self.error.emit(detail)
        else:
            self._kick_preload()

    # ── 查询 ─────────────────────────────────────────────────────────────
    def is_ready(self) -> bool:
        return self._ready and self._worker.isRunning()

    def describe(self) -> str:
        return self._detail

    # ── 播放 ─────────────────────────────────────────────────────────────
    def play(self, path: Path, volume: float) -> bool:
        if not self.is_ready():
            return False
        data = self._ensure_clip(path)
        if data is None:
            return False
        key = str(path)
        self._commands.put(("play", key, data, float(volume)))
        return True

    def stop(self) -> None:
        if self.is_ready():
            self._commands.put(("stop",))

    def preload(self, paths: Iterable[Path]) -> None:
        """后台把素材解成 PCM 并塞给音频线程，避免第一次播放时才解码。"""
        wanted = [Path(p) for p in dict.fromkeys(paths) if p]
        if not wanted:
            return
        self._pending = wanted
        self._kick_preload()

    def _kick_preload(self) -> None:
        wanted = [p for p in self._pending if p.is_file()]
        if not wanted or not self.is_ready():
            return
        self._pending = []

        def run() -> None:
            for path in wanted:
                if path in self._clips:
                    continue
                data = self._ensure_clip(path)
                if data is not None:
                    self._commands.put(("clip", str(path), data))

        threading.Thread(target=run, daemon=True).start()

    # ── 解码缓存 ─────────────────────────────────────────────────────────
    def _ensure_clip(self, path: Path) -> np.ndarray | None:
        key = str(path)
        cached = self._clips.get(key)
        if cached is not None:
            return cached
        if not path.is_file():
            return None
        with self._lock:
            cached = self._clips.get(key)
            if cached is not None:
                return cached
            data = decode_clip(path, self._clip_rate or 96000)
            if data is None:
                return None
            self._clips[key] = data
            return data
