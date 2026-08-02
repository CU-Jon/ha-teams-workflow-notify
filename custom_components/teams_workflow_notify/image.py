"""Image delivery helpers for Microsoft Teams Adaptive Cards."""

from __future__ import annotations

import base64
import binascii
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from homeassistant.core import HomeAssistant
from homeassistant.helpers import network
from PIL import Image, ImageOps
from yarl import URL

from .client import validate_image_url
from .const import (
    IMAGE_DELIVERY_AUTO,
    IMAGE_DELIVERY_INLINE,
    IMAGE_DELIVERY_MODES,
    IMAGE_DELIVERY_URL,
    MAX_EXTERNAL_IMAGE_SIZE_BYTES,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_INPUT_SIZE_BYTES,
    MAX_IMAGE_PIXELS,
    MIN_IMAGE_LONG_EDGE,
)
from .exceptions import (
    TeamsWorkflowExternalUrlUnavailableError,
    TeamsWorkflowImageTooLargeError,
    TeamsWorkflowInvalidImageError,
)

_SUPPORTED_FORMATS = {"GIF", "JPEG", "PNG"}
_JPEG_QUALITIES = (88, 78, 68, 58, 48, 38, 30)


@dataclass(frozen=True, slots=True)
class _LocalImage:
    """A verified image in Home Assistant's public www directory."""

    path: Path
    url: URL


async def async_prepare_image(
    hass: HomeAssistant,
    source: str,
    delivery: str,
    max_data_uri_length: int,
) -> str:
    """Prepare an image URL or inline data URI for a card."""
    if delivery not in IMAGE_DELIVERY_MODES:
        raise TeamsWorkflowInvalidImageError

    try:
        normalized = validate_image_url(source)
    except ValueError as err:
        raise TeamsWorkflowInvalidImageError from err

    if normalized.startswith("data:"):
        if delivery == IMAGE_DELIVERY_URL:
            raise TeamsWorkflowInvalidImageError
        try:
            image_data = base64.b64decode(normalized.partition(",")[2], validate=True)
        except (ValueError, binascii.Error) as err:
            raise TeamsWorkflowInvalidImageError from err
        return await hass.async_add_executor_job(
            _encode_image_data,
            image_data,
            max_data_uri_length,
        )

    parsed = URL(normalized)
    local_url: URL | None = None
    local_path: Path | None = None

    if normalized.startswith("/local/"):
        local_url = parsed
    elif Path(normalized).is_absolute() and not parsed.scheme:
        local_path = Path(normalized)
    elif parsed.path.startswith("/local/") and _is_home_assistant_url(hass, parsed):
        local_url = parsed

    if local_url is None and local_path is None:
        if parsed.scheme != "https" or delivery == IMAGE_DELIVERY_INLINE:
            raise TeamsWorkflowInvalidImageError
        return normalized

    try:
        local_image = await hass.async_add_executor_job(
            _resolve_local_image,
            hass.config.path("www"),
            local_url,
            local_path,
        )
    except TeamsWorkflowInvalidImageError:
        raise
    except Exception as err:
        raise TeamsWorkflowInvalidImageError from err

    if delivery in {IMAGE_DELIVERY_AUTO, IMAGE_DELIVERY_URL}:
        external_url = _get_external_https_url(hass)
        if external_url is not None:
            is_compatible = await hass.async_add_executor_job(
                _is_direct_url_compatible,
                local_image.path,
            )
            if is_compatible:
                return _external_image_url(external_url, local_image.url)
            if delivery == IMAGE_DELIVERY_URL:
                raise TeamsWorkflowInvalidImageError
        if delivery == IMAGE_DELIVERY_URL:
            raise TeamsWorkflowExternalUrlUnavailableError

    return await hass.async_add_executor_job(
        _encode_local_image,
        local_image.path,
        max_data_uri_length,
    )


def _is_home_assistant_url(hass: HomeAssistant, image_url: URL) -> bool:
    """Return whether an absolute local image URL belongs to this instance."""
    candidates: set[str] = set()
    for options in (
        {"allow_external": False, "allow_cloud": False},
        {"allow_internal": False},
    ):
        try:
            candidates.add(network.get_url(hass, **options))
        except network.NoURLAvailableError:
            pass

    image_origin = _url_origin(image_url)
    return any(_url_origin(URL(candidate)) == image_origin for candidate in candidates)


def _url_origin(url: URL) -> tuple[str, str | None, int | None]:
    """Return normalized origin components for comparison."""
    return url.scheme, url.host, url.port


def _get_external_https_url(hass: HomeAssistant) -> str | None:
    """Return Home Assistant's configured secure external or cloud URL."""
    try:
        return network.get_url(
            hass,
            allow_internal=False,
            require_ssl=True,
            prefer_external=True,
        )
    except network.NoURLAvailableError:
        return None


def _external_image_url(external_url: str, local_url: URL) -> str:
    """Place a local image path on the selected external origin."""
    external = URL(external_url)
    return str(external.with_path(local_url.path).with_query(local_url.query))


def _resolve_local_image(
    www_directory: str,
    local_url: URL | None,
    local_path: Path | None,
) -> _LocalImage:
    """Resolve and verify a local source without allowing www traversal."""
    try:
        www_root = Path(www_directory).resolve(strict=True)
        if local_url is not None:
            relative_source = local_url.path.removeprefix("/local/")
            if not relative_source:
                raise TeamsWorkflowInvalidImageError
            relative = Path(*PurePosixPath(relative_source).parts)
            resolved = (www_root / relative).resolve(strict=True)
        elif local_path is not None:
            resolved = local_path.resolve(strict=True)
            relative = resolved.relative_to(www_root)
            local_url = URL.build(path=f"/local/{relative.as_posix()}")
        else:
            raise TeamsWorkflowInvalidImageError

        resolved.relative_to(www_root)
        if not resolved.is_file():
            raise TeamsWorkflowInvalidImageError
    except (OSError, RuntimeError, ValueError) as err:
        raise TeamsWorkflowInvalidImageError from err

    return _LocalImage(resolved, local_url)


def _encode_local_image(path: Path, max_data_uri_length: int) -> str:
    """Load, normalize, and compress a local image into the available budget."""
    try:
        size = path.stat().st_size
    except Exception as err:
        raise TeamsWorkflowInvalidImageError from err
    if size > MAX_IMAGE_INPUT_SIZE_BYTES:
        raise TeamsWorkflowInvalidImageError

    return _encode_image_source(path, max_data_uri_length)


def _encode_image_data(data: bytes, max_data_uri_length: int) -> str:
    """Normalize caller-provided image data into the available budget."""
    return _encode_image_source(BytesIO(data), max_data_uri_length)


def _encode_image_source(source: Path | BytesIO, max_data_uri_length: int) -> str:
    """Load, normalize, and compress an image source into the available budget."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(source) as opened:
                if opened.format not in _SUPPORTED_FORMATS:
                    raise TeamsWorkflowInvalidImageError
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise TeamsWorkflowInvalidImageError
                if getattr(opened, "is_animated", False):
                    opened.seek(0)
                if opened.format == "JPEG":
                    opened.draft("RGB", (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
                normalized = ImageOps.exif_transpose(opened)
                normalized.load()
                image = normalized.copy()
                source_format = opened.format
    except TeamsWorkflowInvalidImageError:
        raise
    except Exception as err:
        raise TeamsWorkflowInvalidImageError from err

    candidate = image.copy()
    for edge in _candidate_edges(max(image.size)):
        candidate.thumbnail((edge, edge), Image.Resampling.LANCZOS)

        if source_format != "JPEG":
            encoded = _encode_png(candidate)
            if (uri := _data_uri("png", encoded, max_data_uri_length)) is not None:
                return uri

        jpeg_candidate = _flatten_for_jpeg(candidate)
        for quality in _JPEG_QUALITIES:
            encoded = _encode_jpeg(jpeg_candidate, quality)
            if (uri := _data_uri("jpeg", encoded, max_data_uri_length)) is not None:
                return uri

    raise TeamsWorkflowImageTooLargeError


def _is_direct_url_compatible(path: Path) -> bool:
    """Return whether Teams can safely fetch a local image without conversion."""
    try:
        size = path.stat().st_size
        if size > MAX_IMAGE_INPUT_SIZE_BYTES:
            raise TeamsWorkflowInvalidImageError
        if size > MAX_EXTERNAL_IMAGE_SIZE_BYTES:
            return False

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as opened:
                if opened.format not in _SUPPORTED_FORMATS:
                    raise TeamsWorkflowInvalidImageError
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise TeamsWorkflowInvalidImageError
                if (
                    opened.width > MAX_IMAGE_DIMENSION
                    or opened.height > MAX_IMAGE_DIMENSION
                ):
                    return False
                if getattr(opened, "is_animated", False):
                    return False
                opened.verify()
    except TeamsWorkflowInvalidImageError:
        raise
    except Exception as err:
        raise TeamsWorkflowInvalidImageError from err

    return True


def _candidate_edges(long_edge: int) -> tuple[int, ...]:
    """Return descending image-size targets, including the minimum target."""
    first = min(long_edge, MAX_IMAGE_DIMENSION)
    minimum = min(first, MIN_IMAGE_LONG_EDGE)
    edges: list[int] = []
    edge = first
    while edge > minimum:
        edges.append(edge)
        edge = max(minimum, int(edge * 0.8))
    edges.append(minimum)
    return tuple(edges)


def _encode_png(image: Image.Image) -> bytes:
    """Encode an image as a metadata-free PNG."""
    if image.mode not in {"1", "L", "LA", "P", "RGB", "RGBA"}:
        image = image.convert("RGBA" if _has_alpha(image) else "RGB")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True, compress_level=9)
    return output.getvalue()


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    """Convert an image to RGB, flattening transparency onto white."""
    if not _has_alpha(image):
        return image.convert("RGB")

    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _has_alpha(image: Image.Image) -> bool:
    """Return whether an image uses transparency."""
    return image.mode in {"LA", "RGBA"} or (
        image.mode == "P" and "transparency" in image.info
    )


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    """Encode an RGB image as a metadata-free JPEG."""
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
    )
    return output.getvalue()


def _data_uri(media_type: str, data: bytes, maximum_length: int) -> str | None:
    """Return a data URI when it fits within the available card budget."""
    encoded = base64.b64encode(data).decode("ascii")
    uri = f"data:image/{media_type};base64,{encoded}"
    return uri if len(uri) <= maximum_length else None
