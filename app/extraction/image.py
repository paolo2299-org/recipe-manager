"""Image preparation for recipe extraction via Claude vision."""

import base64
import io
import logging
from pathlib import PurePosixPath

from PIL import Image

logger = logging.getLogger(__name__)

SUPPORTED_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

MAX_RAW_BYTES = 3_932_160  # 5 MB base64 limit / 1.333 overhead
MAX_DIMENSION = 8000


def prepare_image(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Prepare an uploaded image for the Claude vision API.

    Accepts raw file bytes and the original filename (for extension detection).
    Resizes and compresses if needed to fit API limits.

    Returns (base64_data, media_type).
    """
    suffix = PurePosixPath(filename).suffix.lower()
    media_type = SUPPORTED_MEDIA_TYPES.get(suffix)
    if not media_type:
        raise ValueError(
            f"Unsupported image format '{suffix}'. "
            f"Supported: {sorted(SUPPORTED_MEDIA_TYPES)}"
        )

    img = Image.open(io.BytesIO(file_bytes)).convert("RGB")

    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
        logger.info("Resized to %dx%d", img.size[0], img.size[1])

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    raw = buf.getvalue()
    media_type = "image/jpeg"

    if len(raw) > MAX_RAW_BYTES:
        logger.info("Image is %d bytes — compressing to fit API limit...", len(raw))
        for quality in range(75, 9, -10):
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            raw = buf.getvalue()
            if len(raw) <= MAX_RAW_BYTES:
                logger.info("Compressed to %d bytes (quality=%d)", len(raw), quality)
                break
        else:
            raise RuntimeError("Could not compress image below 5 MB limit")

    data = base64.standard_b64encode(raw).decode("utf-8")
    return data, media_type
