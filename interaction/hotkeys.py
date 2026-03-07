from collections.abc import Callable
from importlib import import_module
from typing import Any


class GlobalHotkeyManager:
    def __init__(self, listener_factory: Callable[[dict[str, Callable[[], None]]], Any] | None = None) -> None:
        self._listener_factory = listener_factory or self._load_listener_factory()
        self._listener = None

    def _load_listener_factory(self) -> Callable[[dict[str, Callable[[], None]]], Any]:
        keyboard = import_module("pynput.keyboard")
        return keyboard.GlobalHotKeys

    def start(self, bindings: dict[str, Callable[[], None]]) -> None:
        normalized = {self._normalize_key(key): callback for key, callback in bindings.items()}
        self._listener = self._listener_factory(normalized)
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()

    def _normalize_key(self, key: str) -> str:
        return f"<{key.lower()}>"
