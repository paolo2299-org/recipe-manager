"""Tests for app.extraction.image — image preparation logic."""

import base64
import io

import pytest
from PIL import Image

from app.extraction.image import MAX_DIMENSION, SUPPORTED_MEDIA_TYPES, prepare_image


def _make_image(width=100, height=100, format="JPEG") -> bytes:
    """Create a small test image and return its bytes."""
    img = Image.new("RGB", (width, height), color="red")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


class TestPrepareImage:
    def test_valid_jpeg(self):
        data, media_type = prepare_image(_make_image(), "photo.jpg")
        assert media_type == "image/jpeg"
        # Verify it's valid base64
        decoded = base64.standard_b64decode(data)
        assert len(decoded) > 0

    def test_valid_png(self):
        data, media_type = prepare_image(_make_image(format="PNG"), "photo.png")
        assert media_type == "image/jpeg"  # always re-encoded as JPEG
        decoded = base64.standard_b64decode(data)
        assert len(decoded) > 0

    def test_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported image format"):
            prepare_image(b"fake", "photo.bmp")

    def test_case_insensitive_extension(self):
        data, media_type = prepare_image(_make_image(), "photo.JPG")
        assert media_type == "image/jpeg"

    def test_large_image_resized(self):
        large_bytes = _make_image(width=9000, height=9000)
        data, media_type = prepare_image(large_bytes, "big.jpg")
        # Should succeed (resized internally)
        decoded = base64.standard_b64decode(data)
        img = Image.open(io.BytesIO(decoded))
        assert max(img.size) <= MAX_DIMENSION

    def test_supported_media_types_keys(self):
        assert ".jpg" in SUPPORTED_MEDIA_TYPES
        assert ".jpeg" in SUPPORTED_MEDIA_TYPES
        assert ".png" in SUPPORTED_MEDIA_TYPES
        assert ".webp" in SUPPORTED_MEDIA_TYPES
        assert ".gif" in SUPPORTED_MEDIA_TYPES
