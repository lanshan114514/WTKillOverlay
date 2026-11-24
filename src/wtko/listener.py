from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

from PySide6.QtCore import QThread, Signal

MIN_POLL_MS = 40    # 轮询节拍的下限：实测 30~45 ms 也不会拖慢游戏的本地接口


@dataclass(frozen=True)
class ListenerSettings:
    player_name: str
    base_url: str
    poll_interval_ms: int
    kill_keywords: tuple[str, ...]


from .parser import extract_hud_items, is_own_kill, item_id


class WarThunderListener(QThread):
    connectionChanged = Signal(bool, str)
    rawMessage = Signal(str)
    killDetected = Signal(str)
    diagnostic = Signal(str)
    gameReset = Signal()

    def __init__(self, settings: ListenerSettings) -> None:
        super().__init__()
        self._settings = settings
        self._settings_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._last_event_id = 0
        self._last_damage_id = 0
        self._synced = False
        self._connected = False

    def update_settings(self, settings: ListenerSettings) -> None:
        with self._settings_lock:
            self._settings = settings

    def stop(self) -> None:
        self._stop_event.set()

    def _settings_snapshot(self) -> ListenerSettings:
        with self._settings_lock:
            return self._settings

    def _set_connected(self, connected: bool, detail: str) -> None:
        if connected != self._connected:
            self._connected = connected
            self.connectionChanged.emit(connected, detail)

    def run(self) -> None:
        # 按固定节拍轮询：周期里要扣掉请求本身花掉的时间，
        # 否则实际节奏是"请求耗时 + 间隔"，白白多等 10 ms 上下。
        deadline = time.monotonic()
        while not self._stop_event.is_set():
            settings = self._settings_snapshot()
            try:
                payload = self._request(settings)
                self._set_connected(True, "已连接 8111 接口")
                self._process_payload(payload, settings)
            except Exception as exc:
                if self._connected:
                    self._set_connected(False, str(exc))
                self._synced = False
                self._last_event_id = 0
                self._last_damage_id = 0

            period = max(settings.poll_interval_ms, MIN_POLL_MS) / 1000
            deadline += period
            remaining = deadline - time.monotonic()
            if remaining > 0:
                self._stop_event.wait(remaining)
            else:
                deadline = time.monotonic()   # 这一轮已经超时，从当下重新对齐

        self._set_connected(False, "监听已停止")

    def _request(self, settings: ListenerSettings) -> dict[str, Any]:
        base = settings.base_url.rstrip("/")
        query = urllib.parse.urlencode(
            {"lastEvt": self._last_event_id, "lastDmg": self._last_damage_id}
        )
        req = urllib.request.Request(
            f"{base}/hudmsg?{query}",
            headers={"User-Agent": "WTKillOverlay/0.1"},
        )
        with urllib.request.urlopen(req, timeout=0.9) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hudmsg 返回的不是 JSON 对象")
        return payload

    def _process_payload(
        self,
        payload: dict[str, Any],
        settings: ListenerSettings,
    ) -> None:
        events, damage = extract_hud_items(payload)

        new_event_items = [i for i in events if item_id(i) > self._last_event_id]
        new_damage_items = [i for i in damage if item_id(i) > self._last_damage_id]

        if events:
            self._last_event_id = max(
                self._last_event_id, max(item_id(i) for i in events)
            )
        if damage:
            self._last_damage_id = max(
                self._last_damage_id, max(item_id(i) for i in damage)
            )

        if not self._synced:
            self._synced = True
            self.diagnostic.emit("已同步当前 HUD 消息游标，后续新消息将参与判断。")
            self.gameReset.emit()
            return

        for item in sorted([*new_event_items, *new_damage_items], key=item_id):
            message = str(item.get("msg", "")).strip()
            if not message:
                continue
            self.rawMessage.emit(message)
            if is_own_kill(message, settings.player_name, settings.kill_keywords):
                self.killDetected.emit(message)
