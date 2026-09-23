"""Render a post image from sticker PNGs.

Usage (CLI test):
  python scripts/render.py "tsuna_kurea/05,tsuna_kurea/12" dialog "月曜の朝のぼくたち" out.png
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STICKERS = ROOT / "assets" / "stickers"
SIZE = 1080

# 作品ごとの背景色（パステル）
BG = {
    "tsuna_kurea": (255, 241, 224),
    "marin": (255, 248, 235),
    "default": (246, 244, 240),
}
TEXT_COLOR = (80, 60, 50)

FONT_CANDIDATES = [
    os.environ.get("RENDER_FONT", ""),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
]


def _font(size):
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            # index 0 = JP in NotoSansCJK .ttc
            return ImageFont.truetype(p, size, index=0)
    return ImageFont.load_default()


def _load(ref):
    ref = ref.strip()
    work, num = ref.split("/")
    path = STICKERS / work / f"{int(num):02d}.png"
    if not path.exists():
        raise FileNotFoundError(f"sticker not found: {path}")
    return work, Image.open(path).convert("RGBA")


def _fit(img, box):
    # LINEスタンプは最大370x320pxなので拡大も行う（最大2.2倍まで）
    scale = min(box / img.width, box / img.height, 2.2)
    return img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        if draw.textlength(cur + ch, font=font) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render(stickers: str, layout: str = "single", caption: str = "", out: str = "out.png"):
    refs = [s for s in stickers.split(",") if s.strip()]
    loaded = [_load(r) for r in refs]
    works = {w for w, _ in loaded}
    bg = BG.get(works.pop() if len(works) == 1 else "default", BG["default"])
    canvas = Image.new("RGBA", (SIZE, SIZE), bg + (255,))
    draw = ImageDraw.Draw(canvas)

    cap_h = 0
    if caption:
        font = _font(64)
        lines = _wrap(draw, caption, font, SIZE - 160)[:3]
        cap_h = 90 * len(lines) + 60
        y = 60
        for line in lines:
            w = draw.textlength(line, font=font)
            draw.text(((SIZE - w) / 2, y), line, font=font, fill=TEXT_COLOR)
            y += 90

    area_top = cap_h
    area_h = SIZE - cap_h - 40
    imgs = [im for _, im in loaded]

    if layout == "single" or len(imgs) == 1:
        im = _fit(imgs[0], min(area_h, SIZE - 160))
        canvas.alpha_composite(im, ((SIZE - im.width) // 2, area_top + (area_h - im.height) // 2))
    elif layout == "dialog":
        # 左右交互に斜めに並べる（会話風）
        n = len(imgs)
        box = min(int(area_h / n * 1.25), 520)
        step = (area_h - box) // max(n - 1, 1)
        for i, im in enumerate(imgs):
            im = _fit(im, box)
            x = 70 if i % 2 == 0 else SIZE - 70 - im.width
            canvas.alpha_composite(im, (x, area_top + i * step))
    else:  # grid
        n = len(imgs)
        cols = 2 if n <= 4 else 3
        rows = (n + cols - 1) // cols
        cell = min((SIZE - 80) // cols, area_h // rows)
        ox = (SIZE - cell * cols) // 2
        for i, im in enumerate(imgs):
            im = _fit(im, cell - 20)
            r, c = divmod(i, cols)
            canvas.alpha_composite(
                im, (ox + c * cell + (cell - im.width) // 2, area_top + r * cell + (cell - im.height) // 2)
            )

    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out


if __name__ == "__main__":
    a = sys.argv[1:] + [""] * 4
    print(render(a[0], a[1] or "single", a[2], a[3] or "out.png"))
