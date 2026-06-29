from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any
import urllib.parse
import urllib.request

from PySide6.QtCore import QThread, Signal


@dataclass(frozen=True)
class ListenerSettings:
    player_name: str
    base_url: str
    poll_interval_ms: int
    kill_keywords: tuple[str, ...]


from .parser import extract_hud_items, item_id, is_own_kill


class WarThunderListener(QThread):
    connectionChanged = Signal(bool, str)
    rawMessage = Signal(str)
    killDetected = Signal(str)
    diagnostic = Signal(str)

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

            interval = max(settings.poll_interval_ms, 80) / 1000
            self._stop_event.wait(interval)

        self._set_connected(False, "监听已停止")

    def _request(self, settings: ListenerSettings) -> dict[str, Any]:
        base = settings.base_url.rstrip("/")
        query = urllib.parse.urlencode(
            {
                "lastEvt": self._last_event_id,
                "lastDmg": self._last_damage_id,
            }
        )
        request = urllib.request.Request(
            f"{base}/hudmsg?{query}",
            headers={"User-Agent": "WTKillOverlay/0.1"},
        )
        with urllib.request.urlopen(request, timeout=0.9) as response:
            raw = response.read().decode("utf-8", errors="replace")
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

        new_event_items = [
            item for item in events if item_id(item) > self._last_event_id
        ]
        new_damage_items = [
            item for item in damage if item_id(item) > self._last_damage_id
        ]

        if events:
            self._last_event_id = max(
                self._last_event_id,
                max(item_id(item) for item in events),
            )
        if damage:
            self._last_damage_id = max(
                self._last_damage_id,
                max(item_id(item) for item in damage),
            )

        if not self._synced:
            self._synced = True
            self.diagnostic.emit("已同步当前 HUD 消息游标，后续新消息将参与判断。")
            return

        for item in sorted(
            [*new_event_items, *new_damage_items],
            key=item_id,
        ):
            message = str(item.get("msg", "")).strip()
            if not message:
                continue

            self.rawMessage.emit(message)

            if is_own_kill(
                message,
                settings.player_name,
                settings.kill_keywords,
            ):
                self.killDetected.emit(message)
