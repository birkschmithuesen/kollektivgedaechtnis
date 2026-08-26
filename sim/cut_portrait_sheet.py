"""Cut a generated 4x4 contact sheet into 16 individual portraits.

Why a contact sheet at all: person nodes need faces to judge the wall's real
look, and generating 16 portraits means 16 image-model calls. One 4x4 grid is
one call — Birk's idea, 2026-08-26 — so the whole set costs a single
generation.

The grid lines are VERIFIED, not assumed: run the check below before trusting
a new sheet, because a model that drifts by twenty pixels produces sixteen
portraits with slivers of the neighbouring face at the edge.

    uv run python sim/cut_portrait_sheet.py --check <sheet.png>

Output matches what the Core writes for a real Telegram photo: square,
`portrait_size` px (512 by default), so the renderer treats seeded faces and
real ones identically.
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from PIL import Image


def grid_lines(image: Image.Image, count: int = 4) -> tuple[list[int], list[int]]:
    """Locate the sheet's separator lines by scanning for bright rows/columns.

    The generated sheets separate cells with a light gutter, which shows up as
    a narrow band of unusually bright columns (and rows). Returning the
    measured positions rather than dividing the width by four is the point:
    it is what turns "assume a clean grid" into "check the grid".
    """
    grey = image.convert("L")
    width, height = grey.size

    def bands(values: list[float]) -> list[int]:
        low, high = min(values), max(values)
        threshold = low + 0.92 * (high - low)
        hits = [i for i, v in enumerate(values) if v >= threshold]
        groups: list[list[int]] = []
        for index in hits:
            if groups and index - groups[-1][-1] <= 3:
                groups[-1].append(index)
            else:
                groups.append([index])
        return [round(sum(g) / len(g)) for g in groups]

    # `list(img.getdata())` is the obvious spelling but Pillow deprecates it
    # (removal in 14) and its type stub does not describe the return as
    # iterable. Reading the band through `tobytes()` is exact, faster, and
    # types cleanly: an 'L' image is one byte per pixel.
    columns = [statistics.mean(grey.crop((x, 0, x + 1, height)).tobytes()) for x in range(width)]
    rows = [statistics.mean(grey.crop((0, y, width, y + 1)).tobytes()) for y in range(height)]
    return bands(columns), bands(rows)


def check(path: Path, count: int = 4, tolerance: int = 12) -> bool:
    """True when the sheet's gutters sit where an even grid would put them."""
    image = Image.open(path)
    width, height = image.size
    cols, rows = grid_lines(image)
    expected_x = [round(width * i / count) for i in range(1, count)]
    expected_y = [round(height * i / count) for i in range(1, count)]

    def matched(found: list[int], expected: list[int]) -> bool:
        return all(any(abs(f - e) <= tolerance for f in found) for e in expected)

    ok_x, ok_y = matched(cols, expected_x), matched(rows, expected_y)
    print(f"columns found: {cols}\n  expected near: {expected_x}  -> {'OK' if ok_x else 'MISMATCH'}")
    print(f"rows    found: {rows}\n  expected near: {expected_y}  -> {'OK' if ok_y else 'MISMATCH'}")
    return ok_x and ok_y


def cut(sheet: Path, out_dir: Path, count: int = 4, size: int = 512, inset: int = 6) -> list[Path]:
    """Slice the sheet into `count`x`count` square portraits.

    `inset` trims a few pixels off every edge: the gutter itself is a couple of
    pixels wide, and leaving it in puts a bright hairline around a face that is
    then drawn inside a circular node — where it reads as a rendering fault
    rather than as part of the picture.
    """
    image = Image.open(sheet).convert("RGB")
    width, height = image.size
    cell_w, cell_h = width / count, height / count
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for row in range(count):
        for col in range(count):
            left = round(col * cell_w) + inset
            top = round(row * cell_h) + inset
            right = round((col + 1) * cell_w) - inset
            bottom = round((row + 1) * cell_h) - inset
            crop = image.crop((left, top, right, bottom))
            # Square it before scaling so no face is stretched.
            side = min(crop.size)
            cx, cy = crop.size[0] / 2, crop.size[1] / 2
            crop = crop.crop(
                (round(cx - side / 2), round(cy - side / 2),
                 round(cx + side / 2), round(cy + side / 2))
            ).resize((size, size), Image.Resampling.LANCZOS)
            target = out_dir / f"portrait-{row * count + col + 1:02d}.jpg"
            crop.save(target, "JPEG", quality=88)
            written.append(target)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(prog="cut_portrait_sheet")
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--out", type=Path, default=Path("sim/data/portraits"))
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--grid", type=int, default=4)
    parser.add_argument("--check", action="store_true", help="verify the grid and exit")
    args = parser.parse_args()

    if args.check:
        raise SystemExit(0 if check(args.sheet, args.grid) else 1)

    if not check(args.sheet, args.grid):
        raise SystemExit("grid does not line up — refusing to cut faces in half")
    written = cut(args.sheet, args.out, args.grid, args.size)
    print(f"{len(written)} portraits -> {args.out}")


if __name__ == "__main__":
    main()
