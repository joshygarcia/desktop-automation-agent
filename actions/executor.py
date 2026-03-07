import ctypes
from importlib import import_module
import time
from typing import Any, cast

from interaction.mouse_dynamics import build_mouse_path
from interaction.timing_engine import bounded_delay
from utils.helpers import percent_to_absolute


def translate_click(
    bounds: dict[str, int],
    parameters: dict[str, float],
) -> tuple[int, int]:
    return percent_to_absolute(bounds, parameters["x_loc"] / 10.0, parameters["y_loc"] / 10.0)


class ActionExecutor:
    def __init__(
        self,
        input_backend: Any | None = None,
        path_builder=None,
        sleep_fn=None,
        timing_fn=None,
        window_activator: Any | None = None,
    ) -> None:
        self.input_backend = input_backend
        self.path_builder = path_builder or build_mouse_path
        self.sleep_fn = sleep_fn or time.sleep
        self.timing_fn = timing_fn or (lambda: bounded_delay(0.02, 0.01, 0.0, 0.05))
        self.window_activator = window_activator or Win32WindowActivator()
        self._last_coordinate_signature: tuple[Any, ...] | None = None
        self._repeat_coordinate_count = 0

    def _backend(self) -> Any:
        if self.input_backend is None:
            self.input_backend = DirectInputBackend()
        return self.input_backend

    def execute(
        self,
        decision: Any,
        metadata: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        action = getattr(decision, "action", None)
        parameters = decision.parameters.model_dump()

        if action == "wait":
            return {"executed": False, "action": action}

        if action in {"click", "double_click"}:
            resolution = self._resolve_click_point(parameters, metadata, action)
            if resolution is None:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "invalid_coordinates",
                }
            coordinates, coordinate_mode, raw_coordinates = resolution
            if not self._point_within_bounds(coordinates, metadata):
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "coordinates_out_of_bounds",
                    "coordinates": coordinates,
                    "coordinate_mode": coordinate_mode,
                    "raw_coordinates": raw_coordinates,
                }
            if dry_run:
                return {
                    "executed": False,
                    "action": action,
                    "coordinates": coordinates,
                    "coordinate_mode": coordinate_mode,
                    "raw_coordinates": raw_coordinates,
                }
            activated = self._activate_target(metadata)
            if not activated:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "target_activation_failed",
                    "coordinates": coordinates,
                    "coordinate_mode": coordinate_mode,
                    "raw_coordinates": raw_coordinates,
                }
            backend = self._backend()
            self._move_humanized(backend, coordinates)
            if action == "double_click":
                backend.double_click()
            else:
                backend.click()
            return {
                "executed": True,
                "action": action,
                "coordinates": coordinates,
                "coordinate_mode": coordinate_mode,
                "raw_coordinates": raw_coordinates,
            }

        if action == "drag":
            start_resolution = self._resolve_point_from_parameters(parameters, metadata, "x_loc", "y_loc")
            end_resolution = self._resolve_point_from_parameters(parameters, metadata, "end_x_loc", "end_y_loc")
            if start_resolution is None or end_resolution is None:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "invalid_coordinates",
                }
            start_point, _start_mode, start_raw = start_resolution
            end_point, _end_mode, end_raw = end_resolution
            start, start_mode, start_raw = self._select_click_candidate(
                f"{action}:start", metadata, start_raw, [(start_point, _start_mode)]
            )
            end, end_mode, end_raw = self._select_click_candidate(
                f"{action}:end", metadata, end_raw, [(end_point, _end_mode)]
            )
            if not self._point_within_bounds(start, metadata) or not self._point_within_bounds(end, metadata):
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "coordinates_out_of_bounds",
                    "start": start,
                    "end": end,
                    "start_mode": start_mode,
                    "end_mode": end_mode,
                    "start_raw": start_raw,
                    "end_raw": end_raw,
                }
            if dry_run:
                return {
                    "executed": False,
                    "action": action,
                    "start": start,
                    "end": end,
                    "start_mode": start_mode,
                    "end_mode": end_mode,
                    "start_raw": start_raw,
                    "end_raw": end_raw,
                }
            activated = self._activate_target(metadata)
            if not activated:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "target_activation_failed",
                    "start": start,
                    "end": end,
                    "start_mode": start_mode,
                    "end_mode": end_mode,
                    "start_raw": start_raw,
                    "end_raw": end_raw,
                }
            backend = self._backend()
            self._move_humanized(backend, start)
            backend.mouse_down()
            self._move_humanized(backend, end, include_current=True)
            backend.mouse_up()
            return {
                "executed": True,
                "action": action,
                "start": start,
                "end": end,
                "start_mode": start_mode,
                "end_mode": end_mode,
                "start_raw": start_raw,
                "end_raw": end_raw,
            }

        if action == "type_text":
            text = parameters.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "invalid_text_payload",
                }
            if dry_run:
                return {"executed": False, "action": action, "text": text}
            activated = self._activate_target(metadata)
            if not activated:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "target_activation_failed",
                    "text": text,
                }
            self._backend().type_text(text)
            return {"executed": True, "action": action, "text": text}

        if action == "press_hotkey":
            keys = parameters.get("keys") or []
            if not isinstance(keys, list) or len(keys) == 0:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "invalid_hotkey_payload",
                }
            if dry_run:
                return {"executed": False, "action": action, "keys": keys}
            activated = self._activate_target(metadata)
            if not activated:
                return {
                    "executed": False,
                    "action": action,
                    "blocked_reason": "target_activation_failed",
                    "keys": keys,
                }
            self._backend().hotkey(*keys)
            return {"executed": True, "action": action, "keys": keys}

        return {"executed": False, "action": action}

    def _move_humanized(
        self,
        backend: Any,
        target: tuple[int, int],
        include_current: bool = False,
    ) -> None:
        start = target
        if hasattr(backend, "get_position"):
            start = backend.get_position()
        path = self.path_builder(start, target)
        for index, point in enumerate(path):
            backend.move_to(point[0], point[1])
            if index < len(path) - 1:
                self.sleep_fn(self.timing_fn())

    def _activate_target(self, metadata: dict[str, Any]) -> bool:
        hwnd = metadata.get("hwnd")
        if hwnd is None:
            return True
        try:
            result = self.window_activator.activate(int(hwnd))
            if isinstance(result, bool):
                return result
            return True
        except Exception:
            return False

    def _resolve_click_point(
        self,
        parameters: dict[str, Any],
        metadata: dict[str, Any],
        action: str,
    ) -> tuple[tuple[int, int], str, tuple[float, float]] | None:
        resolution = self._resolve_point_from_parameters(parameters, metadata, "x_loc", "y_loc")
        if resolution is None:
            return None
        point, mode, raw_coordinates = resolution
        return self._select_click_candidate(action, metadata, raw_coordinates, [(point, mode)])

    def _select_click_candidate(
        self,
        action: str,
        metadata: dict[str, Any],
        raw_coordinates: tuple[float, float],
        fallback: list[tuple[tuple[int, int], str]],
    ) -> tuple[tuple[int, int], str, tuple[float, float]]:
        candidates = self._build_point_candidates(metadata, raw_coordinates)
        if not candidates:
            candidates = fallback

        signature = (
            action,
            metadata.get("hwnd"),
            round(raw_coordinates[0] / 40.0),
            round(raw_coordinates[1] / 40.0),
            tuple(mode for _, mode in candidates),
        )

        if signature == self._last_coordinate_signature:
            self._repeat_coordinate_count += 1
        else:
            self._last_coordinate_signature = signature
            self._repeat_coordinate_count = 1

        point, mode = candidates[0]
        return point, mode, raw_coordinates

    def _resolve_point_from_parameters(
        self,
        parameters: dict[str, Any],
        metadata: dict[str, Any],
        x_key: str,
        y_key: str,
    ) -> tuple[tuple[int, int], str, tuple[float, float]] | None:
        x_value = parameters.get(x_key)
        y_value = parameters.get(y_key)
        if isinstance(x_value, bool) or not isinstance(x_value, (int, float)):
            return None
        if isinstance(y_value, bool) or not isinstance(y_value, (int, float)):
            return None
        raw_coordinates = (float(cast(float, x_value)), float(cast(float, y_value)))

        candidates = self._build_point_candidates(metadata, raw_coordinates)
        if not candidates:
            return None

        point, mode = candidates[0]
        return point, mode, raw_coordinates

    def _build_point_candidates(
        self,
        metadata: dict[str, Any],
        raw_coordinates: tuple[float, float],
    ) -> list[tuple[tuple[int, int], str]]:
        x_number, y_number = raw_coordinates
        bounds = self._extract_bounds(metadata)
        if bounds is None:
            return []
        left_i, top_i, width_i, height_i = bounds
        right_i = left_i + width_i - 1
        bottom_i = top_i + height_i - 1

        candidates: list[tuple[tuple[int, int], str]] = []
        seen_points: set[tuple[int, int]] = set()

        def add_candidate(point: tuple[int, int], mode: str) -> None:
            if point in seen_points:
                return
            if not self._point_within_bounds(point, metadata):
                return
            seen_points.add(point)
            candidates.append((point, mode))

        x_is_1000_scale = 0.0 <= x_number <= 1000.0
        y_is_1000_scale = 0.0 <= y_number <= 1000.0

        if x_is_1000_scale and y_is_1000_scale:
            add_candidate(percent_to_absolute(metadata, x_number / 10.0, y_number / 10.0), "1000_scale")

        x_is_percent_like = 0.0 <= x_number <= 100.0
        y_is_percent_like = 0.0 <= y_number <= 100.0

        if x_is_percent_like and y_is_percent_like:
            add_candidate(percent_to_absolute(metadata, x_number, y_number), "percent")

        return candidates

    def _extract_bounds(self, metadata: dict[str, Any]) -> tuple[int, int, int, int] | None:
        left = metadata.get("left")
        top = metadata.get("top")
        width = metadata.get("width")
        height = metadata.get("height")
        if not isinstance(left, int) or not isinstance(top, int) or not isinstance(width, int) or not isinstance(height, int):
            return None
        return int(left), int(top), int(width), int(height)

    def _point_within_bounds(self, point: tuple[int, int], metadata: dict[str, Any]) -> bool:
        bounds = self._extract_bounds(metadata)
        if bounds is None:
            return False
        left_i, top_i, width_i, height_i = bounds
        if width_i <= 0 or height_i <= 0:
            return False
        right = left_i + width_i - 1
        bottom = top_i + height_i - 1
        return left_i <= point[0] <= right and top_i <= point[1] <= bottom


class DirectInputBackend:
    def __init__(self, module: Any | None = None) -> None:
        self._module = module or import_module("pydirectinput")

    def move_to(self, x: int, y: int) -> None:
        self._module.moveTo(x, y)

    def click(self) -> None:
        self._module.click()

    def double_click(self) -> None:
        if hasattr(self._module, "doubleClick"):
            self._module.doubleClick()
            return
        self._module.click(clicks=2)

    def type_text(self, text: str) -> None:
        try:
            win32clipboard = import_module("win32clipboard")
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            
            # Paste the clipboard content
            time.sleep(0.1)
            self.hotkey("ctrl", "v")
            time.sleep(0.1)
            return
        except ImportError:
            pass
        except Exception as e:
            print(f"Warning: Clipboard paste failed: {e}")

        # Fallback to typing char by char
        if hasattr(self._module, "typewrite"):
            self._module.typewrite(text)
            return
        self._module.write(text)

    def hotkey(self, *keys: str) -> None:
        normalized_keys = tuple(self._normalize_key(key) for key in keys)

        if hasattr(self._module, "hotkey"):
            self._module.hotkey(*normalized_keys)
            return

        if len(normalized_keys) == 1 and hasattr(self._module, "press"):
            self._module.press(normalized_keys[0])
            return

        for key in normalized_keys:
            self._module.keyDown(key)
        for key in reversed(normalized_keys):
            self._module.keyUp(key)

    def mouse_down(self) -> None:
        self._module.mouseDown()

    def mouse_up(self) -> None:
        self._module.mouseUp()

    def get_position(self) -> tuple[int, int]:
        point = import_module("win32api").GetCursorPos()
        return int(point[0]), int(point[1])

    def _normalize_key(self, key: str) -> str:
        aliases = {
            "pgdn": "pagedown",
            "pgup": "pageup",
            "return": "enter",
            "esc": "escape",
            "control": "ctrl",
        }
        lowered = key.lower()
        return aliases.get(lowered, lowered)


class Win32WindowActivator:
    def __init__(self, user32: Any | None = None, win32gui_module: Any | None = None) -> None:
        self._user32 = user32 or ctypes.windll.user32
        self._win32gui = win32gui_module or import_module("win32gui")

    def _same_foreground_context(self, target_hwnd: int, foreground_hwnd: int) -> bool:
        if int(foreground_hwnd) == int(target_hwnd):
            return True

        try:
            if hasattr(self._user32, "GetAncestor"):
                ga_root = 2
                target_root = int(self._user32.GetAncestor(int(target_hwnd), ga_root))
                foreground_root = int(self._user32.GetAncestor(int(foreground_hwnd), ga_root))
                if target_root != 0 and target_root == foreground_root:
                    return True
        except Exception:
            pass

        try:
            if hasattr(self._user32, "GetWindowThreadProcessId"):
                target_pid = ctypes.c_ulong(0)
                foreground_pid = ctypes.c_ulong(0)
                self._user32.GetWindowThreadProcessId(int(target_hwnd), ctypes.byref(target_pid))
                self._user32.GetWindowThreadProcessId(int(foreground_hwnd), ctypes.byref(foreground_pid))
                if target_pid.value != 0 and target_pid.value == foreground_pid.value:
                    return True
        except Exception:
            pass

        return False

    def activate(self, hwnd: int) -> bool:
        try:
            if hasattr(self._win32gui, "IsIconic") and self._win32gui.IsIconic(hwnd):
                self._win32gui.ShowWindow(hwnd, 9)
            self._user32.SetForegroundWindow(hwnd)
            if hasattr(self._user32, "GetForegroundWindow"):
                foreground = int(self._user32.GetForegroundWindow())
                if self._same_foreground_context(hwnd, foreground):
                    return True

                if hasattr(self._user32, "keybd_event"):
                    vk_menu = 0x12
                    keyeventf_keyup = 0x0002
                    self._user32.keybd_event(vk_menu, 0, 0, 0)
                    self._user32.keybd_event(vk_menu, 0, keyeventf_keyup, 0)
                    self._user32.SetForegroundWindow(hwnd)
                    foreground = int(self._user32.GetForegroundWindow())
                    return self._same_foreground_context(hwnd, foreground)

                return False
            return True
        except Exception:
            return False
