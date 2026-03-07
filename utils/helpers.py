import base64
import hashlib
from io import BytesIO

from PIL import Image


def noop() -> None:
    return None


def percent_to_absolute(
    bounds: dict[str, int],
    x_percent: float,
    y_percent: float,
) -> tuple[int, int]:
    x = bounds["left"] + round(bounds["width"] * (x_percent / 100.0))
    y = bounds["top"] + round(bounds["height"] * (y_percent / 100.0))
    return x, y


def resize_image_for_llm(
    image: Image.Image,
    max_width: int,
    max_height: int,
) -> Image.Image:
    if max_width <= 0 or max_height <= 0:
        return image
    if image.width <= max_width and image.height <= max_height:
        return image

    resized = image.copy()
    resized.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return resized


def encode_image_to_base64(image: Image.Image, quality: int = 85) -> str:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def image_fingerprint(image: Image.Image) -> str:
    normalized = image.convert("RGB")
    digest = hashlib.sha1(normalized.tobytes()).hexdigest()
    return digest[:16]
