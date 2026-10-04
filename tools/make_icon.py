"""Generate assets/icon.ico and assets/icon.png: a drawn icon (no network needed)."""
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ICO = os.path.join(ROOT, "assets", "icon.ico")
OUT_PNG = os.path.join(ROOT, "assets", "icon.png")
SIZES = [16, 24, 32, 48, 64, 128, 256]


def draw(size: int) -> Image.Image:
    s = size * 4  # draw big, downsample for smooth edges
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(s * 0.22)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=(13, 13, 26, 255), outline=(42, 42, 68, 255), width=s // 40)
    # a "w" of three launch chevrons
    w = s // 14
    col = (136, 204, 255, 255)
    pts = [(s * 0.16, s * 0.30), (s * 0.30, s * 0.72), (s * 0.42, s * 0.42), (s * 0.54, s * 0.72), (s * 0.68, s * 0.30)]
    d.line(pts, fill=col, width=w, joint="curve")
    d.ellipse((s * 0.74, s * 0.24, s * 0.86, s * 0.36), fill=(136, 255, 136, 255))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    os.makedirs(os.path.dirname(OUT_ICO), exist_ok=True)
    base = draw(256)
    base.save(OUT_PNG, format="PNG")
    base.save(OUT_ICO, format="ICO", sizes=[(n, n) for n in SIZES])
    print("icon written:", OUT_ICO)


if __name__ == "__main__":
    main()
