"""Build SHIBLI icons from the official logo. Never stretch the mark."""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGO_DIR = ROOT / "deployment" / "assets" / "logo"
STATIC_DIR = ROOT / "static" / "branding"
SOURCE_CANDIDATES = (
    LOGO_DIR / "shibli-official.jpg",
    LOGO_DIR / "shibli-official.png",
)


def find_source() -> Path:
    for path in SOURCE_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError("Place the official logo at deployment/assets/logo/shibli-official.jpg")


def _pt(cx: float, cy: float, radius: float, clock_deg: float) -> tuple[float, float]:
    rad = math.radians(clock_deg - 90)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def _donut(cx: float, cy: float, outer: float, inner: float, start: float, end: float) -> str:
    sweep = (end - start) % 360
    large = 1 if sweep > 180 else 0
    a = _pt(cx, cy, outer, start)
    b = _pt(cx, cy, outer, end)
    c = _pt(cx, cy, inner, end)
    d = _pt(cx, cy, inner, start)
    return (
        f"M {a[0]:.2f} {a[1]:.2f} "
        f"A {outer:.2f} {outer:.2f} 0 {large} 1 {b[0]:.2f} {b[1]:.2f} "
        f"L {c[0]:.2f} {c[1]:.2f} "
        f"A {inner:.2f} {inner:.2f} 0 {large} 0 {d[0]:.2f} {d[1]:.2f} Z"
    )


def write_svg(dest: Path) -> None:
    """Official SHIBLI C: blue body, grey wedge, open top-right. Square viewBox, no stretch."""
    cx = cy = 256.0
    outer, inner = 200.0, 92.0
    blue = _donut(cx, cy, outer, inner, 148.0, 358.0)
    grey = _donut(cx, cy, outer, inner, 92.0, 148.0)
    dest.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="SHIBLI">
  <title>SHIBLI</title>
  <path fill="#0055A4" d="{blue}"/>
  <path fill="#A0A0A0" d="{grey}"/>
</svg>
""",
        encoding="utf-8",
    )


def load_rgba(path: Path):
    from PIL import Image

    image = Image.open(path).convert("RGBA")
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if red > 245 and green > 245 and blue > 245:
                pixels[x, y] = (red, green, blue, 0)
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    return image


def fit_square(image, size: int, padding_ratio: float = 0.06):
    from PIL import Image

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = max(1, int(size * (1 - 2 * padding_ratio)))
    src = image.copy()
    src.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    x = (size - src.width) // 2
    y = (size - src.height) // 2
    canvas.paste(src, (x, y), src)
    return canvas


def main() -> int:
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        source = find_source()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    write_svg(LOGO_DIR / "shibli-mark.svg")
    write_svg(LOGO_DIR / "shibli-logo.svg")
    write_svg(STATIC_DIR / "logo.svg")

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed — SVG written; PNG/ICO not generated.")
        return 0

    master = load_rgba(source)
    png = LOGO_DIR / "shibli-256.png"
    fit_square(master, 256).save(png)
    ico_images = [fit_square(master, size) for size in (16, 32, 48, 256)]
    ico = LOGO_DIR / "shibli.ico"
    ico_images[0].save(
        ico,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
        append_images=ico_images[1:],
    )
    runtime = fit_square(master, 256)
    runtime.save(STATIC_DIR / "logo.png")
    print(f"Wrote icons from {source.name} (aspect ratio preserved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
