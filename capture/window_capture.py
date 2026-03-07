import ctypes
import re
import unicodedata
from importlib import import_module
from collections.abc import Callable
from typing import Any

from PIL import Image


_TITLE_NORMALIZATION_TABLE = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\uff0d": "-",
        "\ufffd": "-",
    }
)


def normalize_window_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return normalized.translate(_TITLE_NORMALIZATION_TABLE)


def compute_client_capture_region(
    window_rect: dict[str, int],
    client_rect: dict[str, int],
) -> dict[str, int]:
    _ = window_rect
    return {
        "left": client_rect["left"],
        "top": client_rect["top"],
        "width": client_rect["right"] - client_rect["left"],
        "height": client_rect["bottom"] - client_rect["top"],
    }


class WindowCapture:
    def __init__(
        self,
        window_provider: Callable[[], list[Any]] | None = None,
        win32gui_module: Any | None = None,
        mss_factory: Callable[[], Any] | None = None,
        print_window_capturer: Callable[[int, int, int], Image.Image | None] | None = None,
    ) -> None:
        self._window_provider = window_provider or self._default_window_provider
        self._win32gui = win32gui_module
        self._mss_factory = mss_factory
        self._print_window_capturer = print_window_capturer

    def _default_window_provider(self) -> list[Any]:
        gw = import_module("pygetwindow")
        return list(gw.getAllWindows())

    def _load_win32gui(self) -> Any:
        return import_module("win32gui")

    def _load_mss_factory(self) -> Callable[[], Any]:
        return import_module("mss").mss

    def _load_win32ui(self) -> Any:
        return import_module("win32ui")

    def list_windows(self) -> list[str]:
        return [item["title"] for item in self.list_window_infos()]

    def list_window_infos(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for window in self._window_provider():
            title = getattr(window, "title", "")
            visible = getattr(window, "visible", True)
            if title and visible:
                items.append(
                    {
                        "title": title,
                        "hwnd": getattr(window, "_hWnd", None),
                    }
                )
        return items

    def find_window(self, title_regex: str) -> Any:
        normalized_pattern_text = normalize_window_text(title_regex)
        windows = self._window_provider()

        for window in windows:
            title = getattr(window, "title", "")
            if title and normalize_window_text(title).casefold() == normalized_pattern_text.casefold():
                return window

        pattern = None
        try:
            pattern = re.compile(normalized_pattern_text, re.IGNORECASE)
        except re.error:
            pattern = None
        literal_pattern = re.compile(re.escape(normalized_pattern_text), re.IGNORECASE)
        for window in windows:
            title = getattr(window, "title", "")
            normalized_title = normalize_window_text(title)
            regex_match = pattern.search(normalized_title) if pattern is not None else False
            if title and (regex_match or literal_pattern.search(normalized_title)):
                return window
        raise ValueError(f"No window matched regex: {title_regex}")

    def find_window_by_hwnd(self, hwnd: int) -> Any | None:
        for window in self._window_provider():
            if getattr(window, "_hWnd", None) == hwnd:
                return window
        return None

    def capture(self, title_regex: str, preferred_hwnd: int | None = None) -> tuple[Image.Image, dict[str, Any]]:
        window = self.find_window_by_hwnd(preferred_hwnd) if preferred_hwnd is not None else None
        if window is None:
            window = self.find_window(title_regex)
        hwnd = getattr(window, "_hWnd", None)
        if hwnd is None:
            raise ValueError("Window handle is unavailable")

        win32gui = self._win32gui or self._load_win32gui()
        mss_factory = self._mss_factory or self._load_mss_factory()
        self._ensure_window_ready(hwnd, win32gui)

        client_rect = win32gui.GetClientRect(hwnd)
        top_left = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
        bottom_right = win32gui.ClientToScreen(hwnd, (client_rect[2], client_rect[3]))
        region = compute_client_capture_region(
            window_rect={
                "left": top_left[0],
                "top": top_left[1],
                "right": bottom_right[0],
                "bottom": bottom_right[1],
            },
            client_rect={
                "left": top_left[0],
                "top": top_left[1],
                "right": bottom_right[0],
                "bottom": bottom_right[1],
            },
        )

        image = self._capture_with_printwindow(hwnd, region["width"], region["height"], win32gui)
        if image is not None and self._is_black_frame(image):
            image = None
        if image is None:
            with mss_factory() as sct:
                shot = sct.grab(region)
            image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        metadata = {**region, "title": getattr(window, "title", ""), "hwnd": hwnd}
        return image, metadata

    def _ensure_window_ready(self, hwnd: int, win32gui: Any) -> None:
        if not hasattr(win32gui, "IsIconic"):
            return
        if not win32gui.IsIconic(hwnd):
            return

        if hasattr(win32gui, "ShowWindow"):
            try:
                win32gui.ShowWindow(hwnd, 9)
            except Exception:
                pass

        try:
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

        if win32gui.IsIconic(hwnd):
            raise RuntimeError("Target window is minimized; restore it before running automation")

    def _is_black_frame(self, image: Image.Image) -> bool:
        grayscale = image.convert("L")
        return grayscale.getbbox() is None

    def _capture_with_printwindow(
        self,
        hwnd: int,
        width: int,
        height: int,
        win32gui: Any,
    ) -> Image.Image | None:
        capturer = self._print_window_capturer
        if capturer is not None:
            return capturer(hwnd, width, height)

        if width <= 0 or height <= 0:
            return None

        win32ui = None
        hwnd_dc = 0
        mfc_dc = None
        save_dc = None
        save_bitmap = None
        try:
            win32ui = self._load_win32ui()
            hwnd_dc = win32gui.GetDC(hwnd)
            if not hwnd_dc:
                return None

            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            save_dc.SelectObject(save_bitmap)

            flags = 0x00000001 | 0x00000002
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flags)
            if result != 1:
                return None

            bitmap_info = save_bitmap.GetInfo()
            bitmap_bytes = save_bitmap.GetBitmapBits(True)
            image = Image.frombuffer(
                "RGB",
                (bitmap_info["bmWidth"], bitmap_info["bmHeight"]),
                bitmap_bytes,
                "raw",
                "BGRX",
                0,
                1,
            )
            return image.copy()
        except Exception:
            return None
        finally:
            if save_bitmap is not None:
                win32gui.DeleteObject(save_bitmap.GetHandle())
            if save_dc is not None:
                save_dc.DeleteDC()
            if mfc_dc is not None:
                mfc_dc.DeleteDC()
            if hwnd_dc:
                win32gui.ReleaseDC(hwnd, hwnd_dc)
