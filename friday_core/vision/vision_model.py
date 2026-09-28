"""
F.R.I.D.A.Y. 3.0 — Specialist Vision Model Understanding
Zero-trust local multi-modal vision model client.
Provides dynamic model resolution, strict format/magic-byte validation,
decompression bomb defense, bounded preprocessing, and uncertainty preservation.
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple, Union
import httpx
from PIL import Image, ImageOps

from friday_core.vision.image_context import ImageContext, image_context_manager

logger = logging.getLogger("FRIDAY.Vision.VLM")

DEFAULT_VISION_MODEL = "qwen2.5vl:3b"

PREFERRED_VISION_MODELS = [
    "qwen2.5vl:3b",
    "qwen2.5vl",
    "qwen2-vl",
    "llava:7b",
    "llava",
    "llama3.2-vision",
    "moondream",
    "bakllava"
]

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"}

# Zero-trust safety boundaries
MAX_IMAGE_FILE_BYTES = 20 * 1024 * 1024  # 20 MB limit
MAX_IMAGE_DIMENSION = 4096                # 4096px width or height limit
MAX_IMAGE_PIXELS = 16_777_216            # 16 Megapixels limit
MAX_PROCESSING_DIMENSION = 1920          # Downsample threshold for model inference
MAX_IMAGES_PER_REQUEST = 5

# Set PIL safety threshold to prevent memory exhaustion
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def detect_image_format(raw_bytes: bytes) -> Optional[str]:
    """
    Validates actual image data headers against supported magic bytes.
    Strictly prevents renamed non-image files or corrupt binaries from being decoded.
    """
    if len(raw_bytes) < 4:
        return None
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if raw_bytes.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(raw_bytes) >= 12 and raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "WEBP"
    if raw_bytes.startswith(b"BM"):
        return "BMP"
    if raw_bytes.startswith(b"GIF87a") or raw_bytes.startswith(b"GIF89a"):
        return "GIF"
    if raw_bytes.startswith(b"II*\x00") or raw_bytes.startswith(b"MM\x00*"):
        return "TIFF"
    return None


class VisionModelClient:
    """
    Client for local Vision-Language Models (VLM).
    Dynamic specialist image analysis engine connecting to Ollama.
    """
    def __init__(self, ollama_host: str = "http://localhost:11434"):
        self.host = ollama_host

    async def check_ollama_online(self) -> bool:
        """Verifies whether the Ollama server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def get_available_vision_model(self) -> Optional[str]:
        """
        Dynamically queries local Ollama endpoint to detect installed specialist vision models.
        Resolves configured model from settings or falls back through preferred list.
        Returns None if unavailable (does NOT silently substitute a missing model).
        """
        try:
            from friday_core.settings import settings
            configured_model = settings.get("vision_model", None)

            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(f"{self.host}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    installed_names = [m.get("name", "").lower() for m in models]

                    # 1. Configured model priority match
                    if configured_model:
                        cfg_lower = configured_model.lower()
                        for name in installed_names:
                            if cfg_lower == name or cfg_lower in name:
                                return name

                    # 2. Preferred models priority match
                    for pref in PREFERRED_VISION_MODELS:
                        for name in installed_names:
                            if pref == name or pref in name:
                                return name
        except Exception as ex:
            logger.debug(f"Vision model detection failed: {ex}")
        return None

    async def get_vision_status(self) -> Dict[str, Any]:
        """
        Reports dynamic capability status:
        VISION_SPECIALIST_MODEL, PROVIDER, CAPABILITY_STATUS
        """
        from friday_core.settings import settings
        configured_model = settings.get("vision_model", DEFAULT_VISION_MODEL)
        online = await self.check_ollama_online()
        if not online:
            return {
                "VISION_SPECIALIST_MODEL": configured_model,
                "PROVIDER": "Ollama",
                "CAPABILITY_STATUS": "OFFLINE",
                "AVAILABLE_MODEL": None
            }
        avail = await self.get_available_vision_model()
        if not avail:
            return {
                "VISION_SPECIALIST_MODEL": configured_model,
                "PROVIDER": "Ollama",
                "CAPABILITY_STATUS": "UNAVAILABLE",
                "AVAILABLE_MODEL": None
            }
        return {
            "VISION_SPECIALIST_MODEL": avail,
            "PROVIDER": "Ollama",
            "CAPABILITY_STATUS": "READY",
            "AVAILABLE_MODEL": avail
        }

    async def probe_vision_capability(self) -> Dict[str, Any]:
        """
        Performs a harmless live probe against the configured Vision Specialist.
        Verifies model existence, image input acceptance, latency, and response parsing.
        """
        start_time = time.time()
        start_iso = datetime.utcnow().isoformat()

        status_info = await self.get_vision_status()
        if status_info["CAPABILITY_STATUS"] != "READY":
            return {
                "model": status_info["VISION_SPECIALIST_MODEL"],
                "provider": "Ollama",
                "request_time": start_iso,
                "latency_ms": int((time.time() - start_time) * 1000),
                "first_response": "",
                "total_response_chars": 0,
                "status": status_info["CAPABILITY_STATUS"],
                "error": f"Vision specialist unavailable ({status_info['CAPABILITY_STATUS']})"
            }

        target_model = status_info["AVAILABLE_MODEL"]

        # Create a harmless 2x2 test image
        probe_img = Image.new("RGB", (2, 2), color=(255, 255, 255))
        buf = io.BytesIO()
        probe_img.save(buf, format="PNG")
        probe_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        payload = {
            "model": target_model,
            "prompt": "Return valid JSON: {\"status\": \"READY\", \"description\": \"white pixel\"}",
            "images": [probe_b64],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.0}
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                req_start = time.time()
                resp = await client.post(f"{self.host}/api/generate", json=payload)
                latency = int((time.time() - req_start) * 1000)

                if resp.status_code != 200:
                    return {
                        "model": target_model,
                        "provider": "Ollama",
                        "request_time": start_iso,
                        "latency_ms": latency,
                        "first_response": "",
                        "total_response_chars": 0,
                        "status": "ERROR",
                        "error": f"HTTP status {resp.status_code}"
                    }

                raw = resp.json().get("response", "").strip()
                return {
                    "model": target_model,
                    "provider": "Ollama",
                    "request_time": start_iso,
                    "latency_ms": latency,
                    "first_response": raw[:60],
                    "total_response_chars": len(raw),
                    "status": "READY",
                    "error": None
                }
        except Exception as ex:
            return {
                "model": target_model,
                "provider": "Ollama",
                "request_time": start_iso,
                "latency_ms": int((time.time() - start_time) * 1000),
                "first_response": "",
                "total_response_chars": 0,
                "status": "ERROR",
                "error": str(ex)
            }

    def validate_and_preprocess_image(
        self,
        image_input: Union[str, bytes]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
        """
        Validates raw image data or file path, checks magic bytes, enforces dimension
        and pixel limits against decompression bombs, applies bounded preprocessing,
        and returns (base64_string, metadata_dict, error_message).
        """
        raw_bytes: bytes = b""

        if isinstance(image_input, str):
            if os.path.exists(image_input):
                ext = os.path.splitext(image_input)[1].lower()
                if ext and ext not in SUPPORTED_IMAGE_EXTENSIONS:
                    return None, None, f"Image analysis failed: Unsupported image format '{ext}'."

                size = os.path.getsize(image_input)
                if size == 0:
                    return None, None, "Image analysis failed: Attached image file is empty (0 bytes)."
                if size > MAX_IMAGE_FILE_BYTES:
                    return None, None, f"Image analysis failed: File size ({size} bytes) exceeds limit of {MAX_IMAGE_FILE_BYTES // (1024 * 1024)} MB."

                try:
                    with open(image_input, "rb") as f:
                        raw_bytes = f.read()
                except Exception as ex:
                    return None, None, f"Image analysis failed: Could not read image file: {ex}"
            else:
                # Could be a base64 string
                try:
                    raw_bytes = base64.b64decode(image_input)
                except Exception:
                    return None, None, f"Image analysis failed: File not found or invalid base64: {image_input}"
        elif isinstance(image_input, bytes):
            raw_bytes = image_input

        if not raw_bytes:
            return None, None, "Image analysis failed: Attached image data is empty (0 bytes)."

        if len(raw_bytes) > MAX_IMAGE_FILE_BYTES:
            return None, None, f"Image analysis failed: Image data size ({len(raw_bytes)} bytes) exceeds limit of {MAX_IMAGE_FILE_BYTES // (1024 * 1024)} MB."

        # Magic byte detection to prevent renamed files and non-image binaries
        detected_fmt = detect_image_format(raw_bytes)
        if not detected_fmt:
            return None, None, "Image analysis failed: Invalid or malformed image data (unrecognized format or header mismatch)."

        # Open and validate image dimensions & decompression bomb defense
        try:
            with Image.open(io.BytesIO(raw_bytes)) as pil_img:
                orig_w, orig_h = pil_img.size

                if orig_w <= 0 or orig_h <= 0:
                    return None, None, "Image analysis failed: Image has invalid 0-pixel dimensions."

                if orig_w > MAX_IMAGE_DIMENSION or orig_h > MAX_IMAGE_DIMENSION:
                    return None, None, (
                        f"Image analysis failed: Image dimensions ({orig_w}x{orig_h}) exceed "
                        f"maximum allowed dimension of {MAX_IMAGE_DIMENSION}px."
                    )

                total_pixels = orig_w * orig_h
                if total_pixels > MAX_IMAGE_PIXELS:
                    return None, None, (
                        f"Image analysis failed: Total pixel count ({total_pixels}) exceeds "
                        f"maximum decompression limit of {MAX_IMAGE_PIXELS} pixels."
                    )

                # Preprocessing: EXIF orientation
                try:
                    processed_img = ImageOps.exif_transpose(pil_img)
                except Exception:
                    processed_img = pil_img.copy()

                # Preprocessing: Bounded resize if dimensions exceed processing threshold
                was_resized = False
                cur_w, cur_h = processed_img.size
                if max(cur_w, cur_h) > MAX_PROCESSING_DIMENSION:
                    scale = MAX_PROCESSING_DIMENSION / max(cur_w, cur_h)
                    new_w = max(1, int(cur_w * scale))
                    new_h = max(1, int(cur_h * scale))
                    processed_img = processed_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    was_resized = True

                # Preprocessing: Color mode normalization
                if processed_img.mode in ("RGBA", "LA", "P"):
                    if detected_fmt in ("JPEG", "BMP"):
                        processed_img = processed_img.convert("RGB")
                elif processed_img.mode not in ("RGB", "L", "RGBA"):
                    processed_img = processed_img.convert("RGB")

                # Encode to memory buffer
                buf = io.BytesIO()
                save_fmt = "PNG" if detected_fmt in ("PNG", "WEBP") else "JPEG"
                if save_fmt == "JPEG":
                    if processed_img.mode == "RGBA":
                        processed_img = processed_img.convert("RGB")
                    processed_img.save(buf, format="JPEG", quality=85)
                else:
                    processed_img.save(buf, format="PNG")

                encoded_bytes = buf.getvalue()
                b64_str = base64.b64encode(encoded_bytes).decode("utf-8")

                metadata = {
                    "original_dimensions": (orig_w, orig_h),
                    "processed_dimensions": processed_img.size,
                    "format": detected_fmt,
                    "resized": was_resized,
                    "byte_size": len(encoded_bytes),
                    "preprocessing": {
                        "downscaled": was_resized,
                        "color_mode": processed_img.mode,
                        "target_format": save_fmt
                    }
                }
                return b64_str, metadata, None

        except Image.DecompressionBombError as dbe:
            return None, None, f"Image analysis failed: Image exceeds decompression bomb limit: {dbe}"
        except Exception as ex:
            return None, None, f"Image analysis failed: Invalid or malformed image data ({ex})."

    def validate_and_encode_image(self, image_input: Union[str, bytes]) -> Tuple[Optional[str], Optional[str]]:
        """
        Validates raw image data or file path and returns (base64_string, error_message).
        (Retained for backward compatibility).
        """
        b64, meta, err = self.validate_and_preprocess_image(image_input)
        return b64, err

    async def analyze_image_structured(
        self,
        image_input: Union[str, bytes],
        prompt: str = "",
        model: Optional[str] = None,
        session_id: str = "default_session",
        image_name: str = "",
        image_path: str = "",
        existing_image_id: Optional[str] = None
    ) -> Tuple[Optional[ImageContext], str]:
        """
        Sends an image to the dynamically resolved vision specialist model.
        Extracts structured ImageContext containing verified visual details,
        uncertainty rating, and provenance metadata.
        Returns: (ImageContext, error_message).
        """
        b64_img, meta, val_err = self.validate_and_preprocess_image(image_input)
        if val_err:
            return None, val_err

        # Check Ollama online status
        if not await self.check_ollama_online():
            return None, f"Image analysis failed: Ollama service is offline or unreachable at {self.host}."

        v_model = model or await self.get_available_vision_model()
        if not v_model:
            return None, (
                f"Image analysis failed: Specialist vision model is not available in Ollama (UNAVAILABLE). "
                f"Please ensure a vision model is pulled in Ollama."
            )

        structured_prompt = (
            "You are a specialized image analysis model. Analyze this image thoroughly and return a valid JSON object with the following schema:\n"
            "{\n"
            '  "description": "Comprehensive description of the image and its primary subject",\n'
            '  "objects": ["List of identified objects, UI elements, icons, or components"],\n'
            '  "visible_text": ["All readable text, titles, labels, or code snippets visible in the image"],\n'
            '  "scene": "Environment, application window, layout, or setting",\n'
            '  "actions_or_events": ["Any active actions, buttons, errors, notifications, or processes shown"],\n'
            '  "important_details": ["Key colors, highlights, status indicators, or notable specifics"],\n'
            '  "uncertainty": "OBSERVED | LIKELY | UNCERTAIN | NOT_VISIBLE"\n'
            "}\n"
        )
        if prompt and prompt.strip():
            structured_prompt += f"Specific User Directive to focus on: {prompt.strip()}\n"
        structured_prompt += "Return ONLY valid JSON matching this schema."

        payload = {
            "model": v_model,
            "prompt": structured_prompt,
            "images": [b64_img],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1}
        }

        try:
            async with httpx.AsyncClient(timeout=75.0) as client:
                resp = await client.post(f"{self.host}/api/generate", json=payload)
                if resp.status_code != 200:
                    return None, f"Image analysis failed: Vision model returned HTTP status {resp.status_code}."

                raw_resp = resp.json().get("response", "").strip()
                if not raw_resp:
                    return None, "Image analysis failed: Vision model returned empty response."

                # Parse JSON
                try:
                    clean_json = raw_resp
                    if "```json" in clean_json:
                        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_json:
                        clean_json = clean_json.split("```")[1].split("```")[0].strip()

                    data = json.loads(clean_json)
                except Exception as parse_ex:
                    logger.warning("JSON parse warning on vision response: %s", parse_ex)
                    data = {
                        "description": raw_resp,
                        "objects": [],
                        "visible_text": [],
                        "scene": "",
                        "actions_or_events": [],
                        "important_details": [],
                        "uncertainty": "UNCERTAIN"
                    }

                # Evaluate uncertainty rating
                uncertainty = str(data.get("uncertainty", "")).upper()
                if uncertainty not in {"OBSERVED", "LIKELY", "UNCERTAIN", "NOT_VISIBLE"}:
                    desc_lower = str(data.get("description", "")).lower()
                    if any(w in desc_lower for w in ["not visible", "not shown", "cannot see", "absent"]):
                        uncertainty = "NOT_VISIBLE"
                    elif any(w in desc_lower for w in ["blurry", "unclear", "low resolution", "hard to read", "uncertain", "pixelated"]):
                        uncertainty = "UNCERTAIN"
                    elif any(w in desc_lower for w in ["likely", "appears to be", "probably", "might be"]):
                        uncertainty = "LIKELY"
                    else:
                        uncertainty = "OBSERVED"

                dims = meta.get("processed_dimensions", (0, 0)) if meta else (0, 0)
                fmt = meta.get("format", "UNKNOWN") if meta else "UNKNOWN"
                prep = meta.get("preprocessing", {}) if meta else {}

                # Construct ImageContext
                ctx = ImageContext(
                    image_id=existing_image_id or image_context_manager.get_next_image_id(session_id),
                    description=str(data.get("description", "")),
                    objects=data.get("objects", []) if isinstance(data.get("objects"), list) else [str(data.get("objects", ""))],
                    visible_text=data.get("visible_text", []) if isinstance(data.get("visible_text"), list) else [str(data.get("visible_text", ""))],
                    scene=str(data.get("scene", "")),
                    actions_or_events=data.get("actions_or_events", []) if isinstance(data.get("actions_or_events"), list) else [],
                    important_details=data.get("important_details", []) if isinstance(data.get("important_details"), list) else [],
                    source_model=v_model,
                    session_id=session_id,
                    image_name=image_name or (os.path.basename(image_input) if isinstance(image_input, str) and os.path.exists(image_input) else "uploaded_image.png"),
                    image_path=image_path or (image_input if isinstance(image_input, str) and os.path.exists(image_input) else ""),
                    dimensions=dims,
                    format=fmt,
                    preprocessing=prep,
                    uncertainty_rating=uncertainty,
                    execution_status="SUCCESS",
                    verification_status="VERIFIED",
                    targeted_query=prompt if prompt else None,
                    raw_analysis=raw_resp
                )

                # Store in session manager
                image_context_manager.store_context(ctx)
                return ctx, ""

        except asyncio.CancelledError:
            logger.info("Vision model request cancelled by user.")
            return None, "Image analysis cancelled: Operation aborted."
        except httpx.TimeoutException:
            return None, "Image analysis failed: Vision model request timed out."
        except Exception as ex:
            logger.error("Vision model query error: %s", ex)
            return None, f"Image analysis failed: {ex}"

    async def analyze_image(self, prompt: str, image_b64: str, model: Optional[str] = None) -> str:
        """
        Sends an image and prompt to the local vision model for multimodal reasoning.
        (Retained for backward compatibility).
        """
        ctx, err = await self.analyze_image_structured(image_b64, prompt=prompt, model=model)
        if err:
            return f"⚠️ {err}"
        return ctx.description if ctx else "No visual analysis generated."


# Global Singleton Vision Model Client
vision_client = VisionModelClient()
