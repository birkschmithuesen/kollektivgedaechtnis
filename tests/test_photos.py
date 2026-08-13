from PIL import Image

from kg.photos import make_portrait


def _write_source(path, width, height, colour=(200, 30, 30)):
    Image.new("RGB", (width, height), colour).save(path)
    return path


def test_output_is_a_square_rgba_png_of_the_requested_size(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 4032, 3024)
    dest = tmp_path / "out.png"

    result = make_portrait(src, dest, size=256)

    assert result == dest
    with Image.open(dest) as img:
        assert img.size == (256, 256)
        assert img.mode == "RGBA"
        assert img.format == "PNG"


def test_the_mask_is_circular(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 1000, 1000)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=256)

    with Image.open(dest) as img:
        assert img.getpixel((128, 128))[3] == 255  # centre opaque
        assert img.getpixel((0, 0))[3] == 0  # corner transparent
        assert img.getpixel((255, 255))[3] == 0


def test_portrait_orientation_crops_from_the_upper_part(tmp_path):
    # Top half red, bottom half blue: an upward-biased square crop keeps mostly red.
    src = tmp_path / "in.jpg"
    img = Image.new("RGB", (600, 1200), (255, 0, 0))
    img.paste(Image.new("RGB", (600, 600), (0, 0, 255)), (0, 600))
    img.save(src)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=256)

    with Image.open(dest) as out:
        r, g, b, _ = out.getpixel((128, 128))
        assert r > b


def test_landscape_input_is_centre_cropped(tmp_path):
    src = _write_source(tmp_path / "in.jpg", 1600, 900)
    dest = tmp_path / "out.png"

    make_portrait(src, dest, size=128)

    with Image.open(dest) as out:
        assert out.size == (128, 128)
