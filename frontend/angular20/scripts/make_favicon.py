"""Generate Banque El Amana favicon from brand logo."""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_HORIZONTAL = ROOT / "dist" / "angular20" / "browser" / "brand" / "logo-bea-horizontal.png"
SRC_VERTICAL = ROOT / "dist" / "angular20" / "browser" / "brand" / "logo-bea.png"
PUBLIC = ROOT / "public"
BRAND = PUBLIC / "brand"


def is_ink(px: tuple[int, int, int, int]) -> bool:
    r, g, b, a = px
    if a < 20:
        return False
    return not (r > 245 and g > 245 and b > 245)


def crop_emblem(img: Image.Image) -> Image.Image:
    pixels = img.load()
    w, h = img.size
    col_counts = [sum(1 for y in range(h) if is_ink(pixels[x, y])) for x in range(w)]

    left = next(i for i, c in enumerate(col_counts) if c > 5)
    started = False
    gap_start = None
    for x, c in enumerate(col_counts):
        if c > 5:
            started = True
        elif started and c <= 2:
            gap_len = 0
            xx = x
            while xx < w and col_counts[xx] <= 2:
                gap_len += 1
                xx += 1
            if gap_len >= 8:
                gap_start = x
                break
    right = gap_start if gap_start is not None else w // 3

    xs: list[int] = []
    ys: list[int] = []
    for y in range(h):
        for x in range(left, right):
            if is_ink(pixels[x, y]):
                xs.append(x)
                ys.append(y)
    l2, r2 = min(xs), max(xs)
    top, bottom = min(ys), max(ys)

    pad = 8
    cx = (l2 + r2) / 2
    cy = (top + bottom) / 2
    side = max(r2 - l2, bottom - top) + pad * 2
    x0 = max(0, int(cx - side / 2))
    y0 = max(0, int(cy - side / 2))
    x1 = min(w, int(cx + side / 2))
    y1 = min(h, int(cy + side / 2))

    emblem = img.crop((x0, y0, x1, y1))
    side_sq = max(emblem.size)
    canvas = Image.new("RGBA", (side_sq, side_sq), (255, 255, 255, 255))
    ox = (side_sq - emblem.size[0]) // 2
    oy = (side_sq - emblem.size[1]) // 2
    canvas.paste(emblem, (ox, oy), emblem)
    return canvas


def main() -> None:
    if not SRC_HORIZONTAL.exists():
        raise SystemExit(f"Missing source logo: {SRC_HORIZONTAL}")

    BRAND.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_HORIZONTAL, BRAND / "logo-bea-horizontal.png")
    if SRC_VERTICAL.exists():
        shutil.copy2(SRC_VERTICAL, BRAND / "logo-bea.png")

    img = Image.open(SRC_HORIZONTAL).convert("RGBA")
    emblem = crop_emblem(img)
    emblem.save(BRAND / "icon-bea.png")

    sizes = [(16, 16), (32, 32), (48, 48)]
    ico_frames = [emblem.resize(s, Image.Resampling.LANCZOS) for s in sizes]
    ico_frames[0].save(
        PUBLIC / "favicon.ico",
        format="ICO",
        sizes=sizes,
        append_images=ico_frames[1:],
    )
    emblem.resize((32, 32), Image.Resampling.LANCZOS).save(PUBLIC / "favicon-32.png")
    emblem.resize((180, 180), Image.Resampling.LANCZOS).save(PUBLIC / "apple-touch-icon.png")
    print("OK:", PUBLIC / "favicon.ico")


if __name__ == "__main__":
    main()
