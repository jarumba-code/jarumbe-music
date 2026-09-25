#!/usr/bin/env python3
"""Derive Expo assets from the supplied Jarumba Music artwork.

The source is authoritative. This utility never redraws the logo, changes its
palette, adds text, or removes artwork. It preserves the source bytes and only
resizes, pads, or derives alpha for the platform-specific PNGs.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent
SOURCE_NAME = "jarumba-source.png"
SOURCE_SHA256 = "eb0827deee26a70f16ab185856af7556f50ed60cbc8fbcc411de68b73d18975b"


def source_path() -> Path:
    return OUT_DIR / SOURCE_NAME


def require_official_source(source: Path) -> Image.Image:
    if not source.exists():
        raise SystemExit(f"missing official source: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(
            f"official source hash mismatch: expected {SOURCE_SHA256}, got {digest}"
        )
    with Image.open(source) as image:
        if image.size != (1024, 1024):
            raise SystemExit(f"expected a 1024x1024 source, got {image.size}")
        return image.convert("RGBA")


def make_foreground(source: Image.Image) -> Image.Image:
    """Remove the supplied dark canvas while retaining the original artwork RGB.

    The supplied artwork has a textured navy canvas rather than transparency.
    A blurred copy estimates that canvas locally; the white/green mark is much
    brighter, so the distance gives a soft alpha edge without recoloring pixels.
    """
    background = source.convert("RGB").filter(ImageFilter.GaussianBlur(28))
    result = Image.new("RGBA", source.size)
    source_pixels = source.load()
    background_pixels = background.load()
    output_pixels = result.load()
    for y in range(source.height):
        for x in range(source.width):
            r, g, b, alpha = source_pixels[x, y]
            br, bg, bb = background_pixels[x, y]
            distance = max(abs(r - br), abs(g - bg), abs(b - bb))
            derived_alpha = max(0, min(255, round((distance - 7) * 255 / 34)))
            output_pixels[x, y] = (r, g, b, derived_alpha)
    return result


def fit_adaptive(foreground: Image.Image) -> Image.Image:
    """Fit the extracted artwork inside Android's central 72/108 safe circle."""
    alpha = foreground.getchannel("A")
    bbox = alpha.point(lambda value: 255 if value > 24 else 0).getbbox()
    if bbox is None:
        raise SystemExit("could not identify the supplied artwork")
    artwork = foreground.crop(bbox)
    safe_diameter = foreground.width * (72 / 108) * 0.94
    scale = min(1.0, safe_diameter / max(artwork.size))
    resized = artwork.resize(
        (max(1, round(artwork.width * scale)), max(1, round(artwork.height * scale))),
        Image.Resampling.LANCZOS,
    )
    output = Image.new("RGBA", foreground.size, (0, 0, 0, 0))
    output.alpha_composite(
        resized,
        ((foreground.width - resized.width) // 2, (foreground.height - resized.height) // 2),
    )
    return output


def write_png(image: Image.Image, name: str) -> None:
    destination = OUT_DIR / name
    image.save(destination, "PNG", optimize=True)
    print(f"wrote {destination} {image.size} {image.mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    source = require_official_source(source_path())
    print(f"verified source sha256={SOURCE_SHA256}")
    write_png(source, "jarumba-icon.png")
    extracted = make_foreground(source)
    write_png(extracted, "jarumba-splash.png")
    write_png(fit_adaptive(extracted), "jarumba-adaptive-foreground.png")
    write_png(source.convert("RGB").resize((48, 48), Image.Resampling.LANCZOS), "jarumba-favicon.png")


if __name__ == "__main__":
    main()
