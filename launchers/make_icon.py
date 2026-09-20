"""Generate the TradeX launcher icon in both .icns (macOS) and .ico (Windows).

Run once after the launcher tree exists:
    .venv/bin/python launchers/make_icon.py

Re-run only when the icon design changes.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
MAC_RESOURCES = ROOT / "macos" / "TradeX.app" / "Contents" / "Resources"
WIN_DIR = ROOT / "windows"

# Source render — 1024 is the largest size macOS expects in an .icns.
SIZE = 1024


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Discover a suitable bold font across Windows, macOS, and Linux."""
    font_size = int(size * 0.22)
    candidates = [
        "arialbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "arial.ttf",
    ]
    for font_path in candidates:
        try:
            return ImageFont.truetype(font_path, font_size)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int, motif: str = "start") -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded-square background — dark slate.
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        [(0, 0), (size, size)],
        radius=radius,
        fill=(17, 24, 39, 255),  # slate-900
    )

    pad = int(size * 0.18)
    base_y = size - pad

    if motif == "start":
        # Green upward candle / bar motif.
        bar_w = int(size * 0.12)
        gap = int(size * 0.06)
        heights = [0.30, 0.50, 0.72]
        total_w = 3 * bar_w + 2 * gap
        start_x = (size - total_w) // 2
        for i, h in enumerate(heights):
            x0 = start_x + i * (bar_w + gap)
            y0 = base_y - int(size * h)
            draw.rounded_rectangle(
                [(x0, y0), (x0 + bar_w, base_y)],
                radius=int(bar_w * 0.25),
                fill=(34, 197, 94, 255),  # green-500
            )
    elif motif == "stop":
        # Red stop-themed motif — rounded stop block in the lower motif area.
        stop_w = int(size * 0.38)
        x0 = (size - stop_w) // 2
        y0 = int(size * 0.44)
        x1 = x0 + stop_w
        y1 = y0 + stop_w
        draw.rounded_rectangle(
            [(x0, y0), (x1, y1)],
            radius=int(stop_w * 0.22),
            fill=(239, 68, 68, 255),  # red-500
        )
    else:
        raise ValueError(f"Unknown motif: {motif}")

    # "TX" wordmark across the top.
    font = get_font(size)
    text = "TX"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((size - tw) / 2 - bbox[0], int(size * 0.14) - bbox[1]),
        text,
        font=font,
        fill=(229, 231, 235, 255),  # slate-200
    )

    return img


def build_icns(base: Image.Image, out_path: Path) -> None:
    """Use macOS `iconutil` if available; otherwise fall back to .ico-only output."""
    iconutil = shutil.which("iconutil")
    if not iconutil:
        print("iconutil not found — skipping .icns generation", file=sys.stderr)
        return

    iconset = out_path.with_suffix(".iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for px, name in sizes:
        base.resize((px, px), Image.LANCZOS).save(iconset / name, format="PNG")

    subprocess.run(
        [iconutil, "-c", "icns", str(iconset), "-o", str(out_path)],
        check=True,
    )
    shutil.rmtree(iconset)
    print(f"wrote {out_path}")


def build_ico(base: Image.Image, out_path: Path) -> None:
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(out_path, format="ICO", sizes=sizes)
    print(f"wrote {out_path}")


def main() -> None:
    MAC_RESOURCES.mkdir(parents=True, exist_ok=True)
    WIN_DIR.mkdir(parents=True, exist_ok=True)

    # Start icon assets
    start_base = render(SIZE, motif="start")
    start_base.save(ROOT / "tradex_icon.png", format="PNG")
    build_icns(start_base, MAC_RESOURCES / "TradeX.icns")
    build_ico(start_base, WIN_DIR / "TradeX.ico")

    # Stop icon assets
    stop_base = render(SIZE, motif="stop")
    stop_base.save(ROOT / "tradex_stop_icon.png", format="PNG")
    build_ico(stop_base, WIN_DIR / "TradeX-Stop.ico")


if __name__ == "__main__":
    main()
