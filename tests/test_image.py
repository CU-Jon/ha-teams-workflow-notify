"""Tests for Adaptive Card image delivery."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import network
from PIL import Image
from yarl import URL

from custom_components.teams_workflow_notify.const import (
    IMAGE_DELIVERY_AUTO,
    IMAGE_DELIVERY_INLINE,
    IMAGE_DELIVERY_URL,
    MAX_IMAGE_INPUT_SIZE_BYTES,
)
from custom_components.teams_workflow_notify.exceptions import (
    TeamsWorkflowExternalUrlUnavailableError,
    TeamsWorkflowImageTooLargeError,
    TeamsWorkflowInvalidImageError,
)
from custom_components.teams_workflow_notify.image import (
    _candidate_edges,
    _data_uri,
    _encode_local_image,
    _encode_png,
    _flatten_for_jpeg,
    _has_alpha,
    _is_direct_url_compatible,
    _resolve_local_image,
    async_prepare_image,
)

PNG_DATA_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mP4z8AAAAMBAQ"
    "D3A0FDAAAAAElFTkSuQmCC"
)


def _image_path(hass, name: str) -> Path:
    """Return a path in the test instance's www directory."""
    path = Path(hass.config.path("www", name))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _ensure_www(hass) -> None:
    """Create the test instance's www directory."""
    Path(hass.config.path("www")).mkdir(parents=True, exist_ok=True)


def _decoded_image(uri: str) -> Image.Image:
    """Open an image from a Base64 data URI."""
    encoded = uri.partition(",")[2]
    image = Image.open(BytesIO(base64.b64decode(encoded)))
    image.load()
    return image


@pytest.mark.asyncio
async def test_public_https_image_remains_a_url(hass) -> None:
    """Automatic delivery should leave a public HTTPS image untouched."""
    result = await async_prepare_image(
        hass,
        " https://cdn.example.com/camera.png?token=public ",
        IMAGE_DELIVERY_AUTO,
        100,
    )

    assert result == "https://cdn.example.com/camera.png?token=public"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "delivery", "limit", "exception"),
    [
        (
            "https://cdn.example.com/image.png",
            "invalid",
            1000,
            TeamsWorkflowInvalidImageError,
        ),
        ("not an image", IMAGE_DELIVERY_AUTO, 1000, TeamsWorkflowInvalidImageError),
        (
            "http://cdn.example.com/image.png",
            IMAGE_DELIVERY_AUTO,
            1000,
            TeamsWorkflowInvalidImageError,
        ),
        (
            "https://cdn.example.com/image.png",
            IMAGE_DELIVERY_INLINE,
            1000,
            TeamsWorkflowInvalidImageError,
        ),
        (PNG_DATA_URI, IMAGE_DELIVERY_URL, 1000, TeamsWorkflowInvalidImageError),
        (PNG_DATA_URI, IMAGE_DELIVERY_AUTO, 10, TeamsWorkflowImageTooLargeError),
    ],
)
async def test_invalid_delivery_combinations_are_rejected(
    hass,
    source: str,
    delivery: str,
    limit: int,
    exception: type[Exception],
) -> None:
    """Unsafe or impossible delivery combinations should fail locally."""
    with pytest.raises(exception):
        await async_prepare_image(hass, source, delivery, limit)


@pytest.mark.asyncio
async def test_existing_data_uri_is_validated_and_normalized(hass) -> None:
    """A valid caller-supplied data URI should be fully decoded and normalized."""
    result = await async_prepare_image(
        hass,
        PNG_DATA_URI,
        IMAGE_DELIVERY_INLINE,
        1000,
    )

    assert result.startswith("data:image/png;base64,")
    assert _decoded_image(result).size == (1, 1)


@pytest.mark.asyncio
async def test_truncated_data_uri_is_rejected(hass) -> None:
    """A data URI with only a valid signature must not pass image decoding."""
    with pytest.raises(TeamsWorkflowInvalidImageError):
        await async_prepare_image(
            hass,
            "data:image/png;base64,iVBORw0KGgo=",
            IMAGE_DELIVERY_INLINE,
            1000,
        )


@pytest.mark.asyncio
async def test_unexpected_invalid_data_uri_is_normalized(hass) -> None:
    """Defensive Base64 decoding should not leak implementation exceptions."""
    with (
        patch(
            "custom_components.teams_workflow_notify.image.validate_image_url",
            return_value="data:image/png;base64,%",
        ),
        pytest.raises(TeamsWorkflowInvalidImageError),
    ):
        await async_prepare_image(
            hass,
            "ignored",
            IMAGE_DELIVERY_INLINE,
            1000,
        )


@pytest.mark.asyncio
async def test_local_auto_uses_external_https_url(hass) -> None:
    """A local image should use secure external access when available."""
    path = _image_path(hass, "snapshots/front door.png")
    Image.new("RGB", (20, 10), "red").save(path)

    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        return_value="https://ha.example.com",
    ) as get_url:
        result = await async_prepare_image(
            hass,
            "/local/snapshots/front%20door.png?cache=1",
            IMAGE_DELIVERY_AUTO,
            100,
        )

    assert result == "https://ha.example.com/local/snapshots/front%20door.png?cache=1"
    get_url.assert_called_once_with(
        hass,
        allow_internal=False,
        require_ssl=True,
        prefer_external=True,
    )


@pytest.mark.asyncio
async def test_internal_absolute_url_is_rewritten_to_external(hass) -> None:
    """An absolute URL for this instance should still be treated as local."""
    path = _image_path(hass, "camera.png")
    Image.new("RGB", (20, 10), "red").save(path)

    def get_url(_hass, **options) -> str:
        if options.get("allow_external") is False:
            return "http://homeassistant.local:8123"
        if options.get("require_ssl"):
            return "https://ha.example.com"
        raise network.NoURLAvailableError

    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        side_effect=get_url,
    ):
        result = await async_prepare_image(
            hass,
            "http://homeassistant.local:8123/local/camera.png",
            IMAGE_DELIVERY_AUTO,
            100,
        )

    assert result == "https://ha.example.com/local/camera.png"


@pytest.mark.asyncio
async def test_unknown_https_local_path_is_treated_as_remote(hass) -> None:
    """A /local path on an unrelated origin must not enable local file access."""
    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        side_effect=network.NoURLAvailableError,
    ):
        result = await async_prepare_image(
            hass,
            "https://unrelated.example/local/camera.png",
            IMAGE_DELIVERY_AUTO,
            100,
        )

    assert result == "https://unrelated.example/local/camera.png"


@pytest.mark.asyncio
async def test_local_auto_falls_back_to_budgeted_inline_image(hass) -> None:
    """A private instance should resize and compress a local image inline."""
    path = _image_path(hass, "noisy.png")
    Image.effect_noise((1400, 900), 100).convert("RGB").save(path)

    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        side_effect=network.NoURLAvailableError,
    ):
        result = await async_prepare_image(
            hass, "/local/noisy.png", IMAGE_DELIVERY_AUTO, 8000
        )

    assert result.startswith("data:image/jpeg;base64,")
    assert len(result) <= 8000
    image = _decoded_image(result)
    assert max(image.size) <= 1024
    assert not image.getexif()


@pytest.mark.asyncio
async def test_local_auto_normalizes_image_that_exceeds_direct_limits(hass) -> None:
    """External access should not expose a local file Teams cannot render directly."""
    path = _image_path(hass, "wide.png")
    Image.new("RGB", (1200, 600), "red").save(path)

    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        return_value="https://ha.example.com",
    ):
        result = await async_prepare_image(
            hass,
            "/local/wide.png",
            IMAGE_DELIVERY_AUTO,
            10_000,
        )

    assert result.startswith("data:image/")
    assert max(_decoded_image(result).size) <= 1024


@pytest.mark.asyncio
async def test_url_delivery_rejects_image_that_exceeds_direct_limits(hass) -> None:
    """Explicit URL delivery should reject rather than silently transform a file."""
    path = _image_path(hass, "wide.png")
    Image.new("RGB", (1200, 600), "red").save(path)

    with (
        patch(
            "custom_components.teams_workflow_notify.image.network.get_url",
            return_value="https://ha.example.com",
        ),
        pytest.raises(TeamsWorkflowInvalidImageError),
    ):
        await async_prepare_image(
            hass,
            "/local/wide.png",
            IMAGE_DELIVERY_URL,
            10_000,
        )


@pytest.mark.asyncio
async def test_absolute_www_path_is_oriented_and_metadata_free(hass) -> None:
    """Inline conversion should apply EXIF orientation and remove EXIF data."""
    path = _image_path(hass, "oriented.jpg")
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (40, 20), "green").save(path, exif=exif)

    result = await async_prepare_image(hass, str(path), IMAGE_DELIVERY_INLINE, 20_000)

    image = _decoded_image(result)
    assert image.size == (20, 40)
    assert not image.getexif()


@pytest.mark.asyncio
async def test_animated_gif_uses_only_first_frame(hass) -> None:
    """Local animated GIFs should be made static for Teams compatibility."""
    path = _image_path(hass, "animated.gif")
    first = Image.new("RGB", (10, 10), "red")
    second = Image.new("RGB", (10, 10), "blue")
    first.save(path, save_all=True, append_images=[second], duration=100, loop=0)

    with patch(
        "custom_components.teams_workflow_notify.image.network.get_url",
        return_value="https://ha.example.com",
    ):
        result = await async_prepare_image(
            hass, "/local/animated.gif", IMAGE_DELIVERY_AUTO, 10_000
        )

    image = _decoded_image(result).convert("RGB")
    red, green, blue = image.getpixel((0, 0))
    assert red > 200
    assert green < 20
    assert blue < 20


@pytest.mark.asyncio
async def test_url_delivery_requires_external_https_url(hass) -> None:
    """Explicit URL delivery should not silently fall back to inline data."""
    path = _image_path(hass, "camera.png")
    Image.new("RGB", (10, 10), "red").save(path)

    with (
        patch(
            "custom_components.teams_workflow_notify.image.network.get_url",
            side_effect=network.NoURLAvailableError,
        ),
        pytest.raises(TeamsWorkflowExternalUrlUnavailableError),
    ):
        await async_prepare_image(hass, "/local/camera.png", IMAGE_DELIVERY_URL, 10_000)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["/local/", "/local/missing.png"])
async def test_missing_local_image_is_rejected(hass, source: str) -> None:
    """Missing files and the www directory itself are not valid images."""
    _ensure_www(hass)
    with pytest.raises(TeamsWorkflowInvalidImageError):
        await async_prepare_image(hass, source, IMAGE_DELIVERY_INLINE, 10_000)


@pytest.mark.asyncio
async def test_local_path_cannot_escape_www(hass) -> None:
    """Traversal and absolute paths outside www must be rejected."""
    outside = Path(hass.config.path("outside.png"))
    Image.new("RGB", (10, 10), "red").save(outside)
    _ensure_www(hass)

    for source in ("/local/../outside.png", str(outside)):
        with pytest.raises(TeamsWorkflowInvalidImageError):
            await async_prepare_image(hass, source, IMAGE_DELIVERY_INLINE, 10_000)


@pytest.mark.asyncio
async def test_directory_source_is_rejected(hass) -> None:
    """A directory below www must not be treated as an image file."""
    _image_path(hass, "directory/placeholder").parent.mkdir(exist_ok=True)

    with pytest.raises(TeamsWorkflowInvalidImageError):
        await async_prepare_image(
            hass, "/local/directory", IMAGE_DELIVERY_INLINE, 10_000
        )


@pytest.mark.asyncio
async def test_invalid_unsupported_and_large_local_files_are_rejected(hass) -> None:
    """Unreadable, unsupported, and excessively large inputs should fail safely."""
    invalid = _image_path(hass, "invalid.png")
    invalid.write_bytes(b"not an image")
    bitmap = _image_path(hass, "unsupported.bmp")
    Image.new("RGB", (10, 10), "red").save(bitmap)
    large = _image_path(hass, "large.png")
    with large.open("wb") as stream:
        stream.seek(MAX_IMAGE_INPUT_SIZE_BYTES)
        stream.write(b"x")

    for source in (invalid, bitmap, large):
        with pytest.raises(TeamsWorkflowInvalidImageError):
            await async_prepare_image(hass, str(source), IMAGE_DELIVERY_INLINE, 10_000)

    pixel_limited = _image_path(hass, "pixel-limited.png")
    Image.new("RGB", (10, 10), "red").save(pixel_limited)
    with (
        patch("custom_components.teams_workflow_notify.image.MAX_IMAGE_PIXELS", 50),
        pytest.raises(TeamsWorkflowInvalidImageError),
    ):
        await async_prepare_image(
            hass, str(pixel_limited), IMAGE_DELIVERY_INLINE, 10_000
        )


@pytest.mark.asyncio
async def test_local_image_that_cannot_fit_is_rejected(hass) -> None:
    """An impossible inline budget should return a specific size error."""
    path = _image_path(hass, "small.png")
    Image.new("RGBA", (10, 10), (255, 0, 0, 128)).save(path)

    with pytest.raises(TeamsWorkflowImageTooLargeError):
        await async_prepare_image(hass, str(path), IMAGE_DELIVERY_INLINE, 1)


@pytest.mark.asyncio
async def test_executor_failure_is_normalized(hass) -> None:
    """Unexpected local filesystem failures should not leak implementation errors."""
    _ensure_www(hass)
    with (
        patch.object(
            hass,
            "async_add_executor_job",
            AsyncMock(side_effect=RuntimeError("private path detail")),
        ),
        pytest.raises(TeamsWorkflowInvalidImageError),
    ):
        await async_prepare_image(
            hass, "/local/camera.png", IMAGE_DELIVERY_INLINE, 10_000
        )


def test_internal_helpers_cover_image_modes_and_boundaries(tmp_path) -> None:
    """Encoding helpers should handle alpha, uncommon modes, and size boundaries."""
    assert _candidate_edges(100) == (100,)
    assert _candidate_edges(200)[-1] == 160
    assert _candidate_edges(2000)[0] == 1024

    rgba = Image.new("RGBA", (2, 2), (255, 0, 0, 0))
    assert _has_alpha(rgba)
    assert _flatten_for_jpeg(rgba).mode == "RGB"
    assert not _has_alpha(Image.new("RGB", (2, 2), "red"))
    assert _flatten_for_jpeg(Image.new("L", (2, 2))).mode == "RGB"

    palette = Image.new("P", (2, 2))
    palette.info["transparency"] = 0
    assert _has_alpha(palette)

    integer_image = Image.new("I", (2, 2), 1)
    assert _encode_png(integer_image).startswith(b"\x89PNG")
    assert _data_uri("png", b"test", 100) == "data:image/png;base64,dGVzdA=="
    assert _data_uri("png", b"test", 1) is None

    www = tmp_path / "www"
    www.mkdir()
    with pytest.raises(TeamsWorkflowInvalidImageError):
        _resolve_local_image(str(www), None, None)
    with pytest.raises(TeamsWorkflowInvalidImageError):
        _encode_local_image(tmp_path / "missing.png", 1000)

    assert URL("https://example.com").port == 443


def test_direct_url_compatibility_checks_file_size_and_format(tmp_path) -> None:
    """Direct delivery should reject or convert files outside Teams' limits."""
    image_path = tmp_path / "image.png"
    Image.new("RGB", (10, 10), "red").save(image_path)
    assert _is_direct_url_compatible(image_path)

    with patch(
        "custom_components.teams_workflow_notify.image.MAX_EXTERNAL_IMAGE_SIZE_BYTES",
        1,
    ):
        assert not _is_direct_url_compatible(image_path)

    unsupported = tmp_path / "image.bmp"
    Image.new("RGB", (10, 10), "red").save(unsupported)
    with pytest.raises(TeamsWorkflowInvalidImageError):
        _is_direct_url_compatible(unsupported)

    with (
        patch("custom_components.teams_workflow_notify.image.MAX_IMAGE_PIXELS", 50),
        pytest.raises(TeamsWorkflowInvalidImageError),
    ):
        _is_direct_url_compatible(image_path)

    missing = tmp_path / "missing.png"
    with pytest.raises(TeamsWorkflowInvalidImageError):
        _is_direct_url_compatible(missing)

    too_large = tmp_path / "too-large.png"
    with too_large.open("wb") as stream:
        stream.seek(MAX_IMAGE_INPUT_SIZE_BYTES)
        stream.write(b"x")
    with pytest.raises(TeamsWorkflowInvalidImageError):
        _is_direct_url_compatible(too_large)
