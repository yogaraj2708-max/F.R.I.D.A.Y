"""
F.R.I.D.A.Y. 3.0 — Vision Ingestion & Image Type Validation Test Battery
Validates format integrity, magic bytes detection, size limits, decompression bomb defense,
and bounded image preprocessing.
"""

import io
import os
import tempfile
import pytest
from PIL import Image

from friday_core.vision.vision_model import (
    VisionModelClient,
    detect_image_format,
    MAX_IMAGE_FILE_BYTES,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PROCESSING_DIMENSION,
)


@pytest.fixture
def vision_client():
    return VisionModelClient()


@pytest.fixture
def sample_png_file():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (200, 100), color=(10, 20, 30))
        img.save(tf, format="PNG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def sample_jpeg_file():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        img = Image.new("RGB", (200, 100), color=(50, 60, 70))
        img.save(tf, format="JPEG")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def sample_webp_file():
    with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tf:
        img = Image.new("RGB", (200, 100), color=(80, 90, 100))
        img.save(tf, format="WEBP")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


@pytest.fixture
def sample_bmp_file():
    with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tf:
        img = Image.new("RGB", (200, 100), color=(110, 120, 130))
        img.save(tf, format="BMP")
        tf_path = tf.name
    yield tf_path
    if os.path.exists(tf_path):
        os.remove(tf_path)


def test_magic_byte_format_detection():
    # PNG
    assert detect_image_format(b"\x89PNG\r\n\x1a\n\x00\x00") == "PNG"
    # JPEG
    assert detect_image_format(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "JPEG"
    # WEBP
    assert detect_image_format(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "WEBP"
    # BMP
    assert detect_image_format(b"BM\x00\x00\x00\x00\x00\x00") == "BMP"
    # Plain text / EXE / Corrupt
    assert detect_image_format(b"This is a text file") is None
    assert detect_image_format(b"MZ\x90\x00\x03\x00\x00\x00") is None
    assert detect_image_format(b"") is None


def test_valid_image_formats_ingestion(vision_client, sample_png_file, sample_jpeg_file, sample_webp_file, sample_bmp_file):
    for fpath in [sample_png_file, sample_jpeg_file, sample_webp_file, sample_bmp_file]:
        b64, meta, err = vision_client.validate_and_preprocess_image(fpath)
        assert err is None, f"Failed for {fpath}: {err}"
        assert b64 is not None
        assert meta is not None
        assert meta["original_dimensions"] == (200, 100)
        assert meta["format"] in ["PNG", "JPEG", "WEBP", "BMP"]


def test_zero_byte_image_rejection(vision_client):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert b64 is None
        assert "empty (0 bytes)" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_renamed_non_image_rejection(vision_client):
    # A text or script file renamed with a .png extension
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf.write(b"import os\nos.system('calc.exe')\n")
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert b64 is None
        assert "Invalid or malformed image data" in err or "unrecognized format" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_corrupted_image_stream_rejection(vision_client):
    # Valid PNG header followed by garbage
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tf.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRGARBAGE_BYTES_CORRUPTED")
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert b64 is None
        assert "Invalid or malformed image data" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_unsupported_file_extension(vision_client):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        tf.write(b"%PDF-1.4\n1 0 obj\n")
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert b64 is None
        assert "Unsupported image format" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_oversized_file_bytes_rejection(vision_client):
    # Mock or construct an oversized buffer
    huge_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * (MAX_IMAGE_FILE_BYTES + 1024)
    b64, meta, err = vision_client.validate_and_preprocess_image(huge_bytes)
    assert b64 is None
    assert "exceeds limit" in err


def test_oversized_dimensions_rejection(vision_client):
    # Image exceeding MAX_IMAGE_DIMENSION (4096px)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img = Image.new("RGB", (MAX_IMAGE_DIMENSION + 100, 50), color="white")
        img.save(tf, format="PNG")
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert b64 is None
        assert "exceed maximum allowed dimension" in err
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_bounded_preprocessing_downscaling(vision_client):
    # Image with dimension 2500x1250 (within 4096 limit, but above MAX_PROCESSING_DIMENSION 1920)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        img = Image.new("RGB", (2500, 1250), color=(100, 150, 200))
        img.save(tf, format="JPEG")
        tf_path = tf.name
    try:
        b64, meta, err = vision_client.validate_and_preprocess_image(tf_path)
        assert err is None
        assert b64 is not None
        assert meta["resized"] is True
        assert meta["original_dimensions"] == (2500, 1250)
        assert meta["processed_dimensions"][0] == MAX_PROCESSING_DIMENSION
        # Check aspect ratio preserved (2500:1250 = 2:1 -> 1920:960)
        assert meta["processed_dimensions"][1] == 960
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)
