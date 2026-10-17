"""Le foto si salvano ottimizzate (core/storage.py::optimize_image)."""
import io

import pytest
from PIL import Image

from app.core.storage import AVATAR_MAX_SIDE, MEDIA_MAX_SIDE, UploadValidationError, optimize_image


def _jpeg(w: int, h: int, *, orientation: int | None = None, gps: bool = False) -> bytes:
    img = Image.effect_noise((w, h), 60).convert("RGB")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    if gps:
        exif[0x8825] = {1: "N", 2: (37.0, 6.0, 0.0)}
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=98, exif=exif.tobytes())
    return out.getvalue()


def test_a_big_phone_photo_is_shrunk_and_loses_its_metadata():
    raw = _jpeg(4000, 3000, gps=True)
    data, ctype = optimize_image(raw, "image/jpeg")
    assert ctype == "image/jpeg"
    assert len(data) < len(raw)
    with Image.open(io.BytesIO(data)) as img:
        assert max(img.size) == MEDIA_MAX_SIDE
        assert not img.getexif()


def test_a_profile_photo_is_smaller_and_turned_like_the_phone_shows_it():
    # Orientamento 6: il telefono l'ha scattata girata di 90°, larga 1200 e alta 900.
    data, _ = optimize_image(_jpeg(1200, 900, orientation=6), "image/jpeg", max_side=AVATAR_MAX_SIDE)
    with Image.open(io.BytesIO(data)) as img:
        assert img.size == (600, AVATAR_MAX_SIDE)


def test_a_logo_with_transparency_stays_a_png():
    img = Image.new("RGBA", (300, 200), (255, 0, 0, 0))
    out = io.BytesIO()
    img.save(out, format="PNG")
    data, ctype = optimize_image(out.getvalue(), "image/png")
    assert ctype == "image/png"
    with Image.open(io.BytesIO(data)) as back:
        assert back.mode == "RGBA" and back.size == (300, 200)


def test_an_opaque_webp_becomes_a_jpeg():
    out = io.BytesIO()
    Image.new("RGB", (50, 50), "blue").save(out, format="WEBP")
    assert optimize_image(out.getvalue(), "image/webp")[1] == "image/jpeg"


def test_a_gif_is_left_as_it_is():
    raw = b"GIF89a" + b"\x00" * 20
    assert optimize_image(raw, "image/gif") == (raw, "image/gif")


def test_a_file_that_only_looks_like_an_image_is_refused():
    with pytest.raises(UploadValidationError):
        optimize_image(b"\xff\xd8\xff" + b"not really a jpeg", "image/jpeg")
