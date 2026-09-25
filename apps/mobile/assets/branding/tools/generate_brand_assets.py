#!/usr/bin/env python3
"""Generate the Jarumba Music brand assets from a single geometric definition.

The mark is an original composition:

  * a bold white geometric "J" built from a top bar, a right stem and a
    circular hook (all derived from one stroke width, so proportions never
    drift between sizes)
  * a restrained electric-green play triangle nested inside the hook

Nothing here imitates another music brand: no circle-with-three-bars, no
headphones, no microphone, no lettering.

Usage (from anywhere):

    python apps/mobile/assets/branding/tools/generate_brand_assets.py

Outputs (written to apps/mobile/assets/branding/):

    jarumba-icon.png                 1024x1024 opaque app / launcher icon
    jarumba-adaptive-foreground.png  1024x1024 transparent adaptive foreground
    jarumba-monochrome.png           1024x1024 transparent themed-icon glyph
    jarumba-splash.png               1024x1024 transparent splash mark
    jarumba-favicon.png              48x48     web favicon
    jarumba-logo.svg                 vector master of the mark

Requires: pillow, numpy.
"""

from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, os.pardir))

CANVAS = 1024
SS = 4  # supersampling factor, downsampled with LANCZOS for clean edges

# Brand palette. BG_INK matches the app theme background (#07100B) so the
# launcher icon, splash and in-app UI read as one product.
BG_NAVY = (10, 21, 33)
BG_INK = (6, 16, 11)
WHITE = (255, 255, 255)
GREEN = (34, 197, 94)  # #22C55E, theme accentPrimary ("Jarumba green")

# Mark proportions, all expressed in stroke widths.
HOOK_RADIUS = 2.0     # hook centreline radius
STEM_DROP = 2.6       # top bar centreline -> hook centreline
HOOK_START_DEG = -190.0  # sweep through the bottom (-90 deg) up to the left
HOOK_END_DEG = 0.0
TRI_APEX = 1.05       # play triangle: apex offset right of the hook centre
TRI_LEFT = 0.50       # play triangle: base offset left of the hook centre
TRI_HALF_H = 0.86     # play triangle: half height

MARK_W_UNITS = 2 * HOOK_RADIUS + 1
MARK_H_UNITS = STEM_DROP + 1 + HOOK_RADIUS
# Stroke width that makes the mark occupy `mark_height` px of the canvas.
# 1024px maps to 108dp on an adaptive icon layer and launchers mask the central
# 72dp with a circle, so the foreground mark is sized to stay inside that
# circle (verified by _validate). The flat app icon and the splash mark have no
# mask, so they carry more presence.
STROKE_APP_ICON = 620 / MARK_H_UNITS
STROKE_FOREGROUND = 560 / MARK_H_UNITS
STROKE_SPLASH = 700 / MARK_H_UNITS


def _mark(stroke: float) -> dict:
    """Geometry of the mark (y-up canvas coordinates, origin bottom-left)."""
    w = stroke
    r = HOOK_RADIUS * w
    drop = STEM_DROP * w
    cx = CANVAS / 2
    cy = CANVAS / 2  # mark is centred on the canvas
    mark_h = drop + w + r
    y_top = cy + mark_h / 2 - w / 2
    y_hook = y_top - drop
    x_right = cx + (MARK_W_UNITS / 2) * w
    stem_x = x_right - w / 2
    end = math.radians(HOOK_START_DEG)
    return {
        "stroke": w,
        "radius": r,
        "cx": cx,
        "cy": cy,
        "y_top": y_top,
        "y_hook": y_hook,
        "bar": (cx - (MARK_W_UNITS / 2) * w, y_top, x_right, y_top),
        "stem": (stem_x, y_hook, stroke),
        "hook_center": (cx, y_hook),
        "hook_end": (cx + r * math.cos(end), y_hook + r * math.sin(end)),
        "triangle": [
            (cx + TRI_APEX * w, y_hook),
            (cx - TRI_LEFT * w, y_hook + TRI_HALF_H * w),
            (cx - TRI_LEFT * w, y_hook - TRI_HALF_H * w),
        ],
    }


def _scaled(mark: dict, scale: float) -> dict:
    """Scale a y-up geometry description for supersampled drawing."""
    out = dict(mark)
    for key in ("stroke", "radius", "y_top", "y_hook"):
        out[key] = mark[key] * scale
    for key in ("cx", "cy"):
        out[key] = mark[key] * scale
    out["bar"] = tuple(v * scale for v in mark["bar"])
    out["stem"] = (mark["stem"][0] * scale, mark["stem"][1] * scale, mark["stroke"] * scale)
    out["hook_center"] = (mark["hook_center"][0] * scale, mark["hook_center"][1] * scale)
    out["hook_end"] = (mark["hook_end"][0] * scale, mark["hook_end"][1] * scale)
    out["triangle"] = [(x * scale, y * scale) for x, y in mark["triangle"]]
    return out


def _arc_band_points(g: dict, steps: int = 240) -> list[tuple[float, float]]:
    """Outer arc + inner arc of the hook stroke, as a closed polygon."""
    cx, cy = g["hook_center"]
    r, half = g["radius"], g["stroke"] / 2
    angles = [
        math.radians(HOOK_START_DEG + (HOOK_END_DEG - HOOK_START_DEG) * i / steps)
        for i in range(steps + 1)
    ]
    outer = [(cx + (r + half) * math.cos(a), cy + (r + half) * math.sin(a)) for a in angles]
    inner = [(cx + (r - half) * math.cos(a), cy + (r - half) * math.sin(a)) for a in reversed(angles)]
    return outer + inner


def _mask(g: dict, size: int, part: str) -> Image.Image:
    """Rasterise one part of the mark ("mark" = the J, "triangle" = the play)."""
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    w = g["stroke"]
    half = w / 2

    def p(x: float, y: float) -> tuple[float, float]:
        """y-up geometry -> image coordinates."""
        return (x, size - y)

    if part == "triangle":
        draw.polygon([p(x, y) for x, y in g["triangle"]], fill=255)
        return img

    x0, y_top, x1, _ = g["bar"]
    ax, ay = p(x0 + half, y_top + half)
    bx, by = p(x1 - half, y_top - half)
    draw.rounded_rectangle([ax, ay, bx, by], radius=half, fill=255)

    stem_x, y_hook, _ = g["stem"]
    ax, ay = p(stem_x - half, y_top)
    bx, by = p(stem_x + half, y_hook)
    draw.rounded_rectangle([ax, ay, bx, by], radius=half, fill=255)

    draw.polygon([p(x, y) for x, y in _arc_band_points(g)], fill=255)
    cx, cy = g["hook_center"]
    r = g["radius"]
    caps = [
        (cx + r * math.cos(math.radians(HOOK_END_DEG)), cy + r * math.sin(math.radians(HOOK_END_DEG))),
        g["hook_end"],
    ]
    for cap_x, cap_y in caps:
        ex, ey = p(cap_x, cap_y)
        draw.ellipse([ex - half, ey - half, ex + half, ey + half], fill=255)
    return img


def _plate() -> Image.Image:
    """Near-black navy -> near-black green gradient with a soft green glow."""
    size = CANVAS
    yy, xx = np.mgrid[0:size, 0:size]
    t = ((xx + yy) / (2.0 * (size - 1))).astype(np.float32)
    navy = np.array(BG_NAVY, dtype=np.float32)
    ink = np.array(BG_INK, dtype=np.float32)
    arr = navy[None, None, :] * (1.0 - t)[..., None] + ink[None, None, :] * t[..., None]
    plate = Image.fromarray(arr.astype("uint8"), "RGB")
    glow = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(glow)
    r = 0.40 * size
    d.ellipse([size / 2 - r, size / 2 - 1.06 * r, size / 2 + r, size / 2 + 1.06 * r], fill=255)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.16)).point(lambda v: int(v * 0.34))
    return Image.composite(Image.new("RGB", (size, size), GREEN), plate, glow)


def _render(stroke: float, plated: bool, mono: bool = False) -> Image.Image:
    """Compose the mark at `stroke` width, supersampled then downscaled."""
    big = CANVAS * SS
    g = _scaled(_mark(stroke), SS)
    j = _mask(g, big, "mark").resize((CANVAS, CANVAS), Image.LANCZOS)
    tri = _mask(g, big, "triangle").resize((CANVAS, CANVAS), Image.LANCZOS)
    if plated:
        canvas: Image.Image = _plate()
    else:
        canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    if mono:
        canvas.paste(WHITE, mask=ImageChops.lighter(j, tri))
    else:
        canvas.paste(WHITE, mask=j)
        canvas.paste(GREEN, mask=tri)
    return canvas


def _svg(stroke: float) -> str:
    """Vector master of the mark, built from the same geometry as the PNGs."""
    g = _mark(stroke)
    w = g["stroke"]
    half = w / 2
    x0, y_top, x1, _ = g["bar"]
    stem_x, y_hook, _ = g["stem"]
    cx, cy = g["hook_center"]
    r = g["radius"]

    def pt(x: float, y: float) -> str:
        return f"{x:.2f},{CANVAS - y:.2f}"

    poly = " ".join(pt(x, y) for x, y in _arc_band_points(g, steps=96))
    cap_svg = "\n".join(
        f'      <circle cx="{x:.2f}" cy="{CANVAS - y:.2f}" r="{half:.2f}"/>'
        for x, y in [(cx + r, cy), g["hook_end"]]
    )
    bar_svg = (
        f'      <rect x="{x0 + half:.2f}" y="{CANVAS - y_top - half:.2f}" '
        f'width="{x1 - x0 - w:.2f}" height="{w:.2f}" rx="{half:.2f}"/>'
    )
    stem_svg = (
        f'      <rect x="{stem_x - half:.2f}" y="{CANVAS - y_top:.2f}" '
        f'width="{w:.2f}" height="{y_top - y_hook:.2f}" rx="{half:.2f}"/>'
    )
    tri_svg = " ".join(pt(x, y) for x, y in g["triangle"])
    mid = CANVAS // 2
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CANVAS} {CANVAS}" width="{CANVAS}" height="{CANVAS}" role="img" aria-label="Jarumba Music">
  <title>Jarumba Music</title>
  <defs>
    <linearGradient id="plate" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{CANVAS}" y2="{CANVAS}">
      <stop offset="0" stop-color="#0A1521"/>
      <stop offset="1" stop-color="#06100B"/>
    </linearGradient>
    <radialGradient id="glow" gradientUnits="userSpaceOnUse" cx="{mid}" cy="{mid}" r="{int(0.55 * CANVAS)}">
      <stop offset="0.35" stop-color="#22C55E" stop-opacity="0.34"/>
      <stop offset="1" stop-color="#22C55E" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{CANVAS}" height="{CANVAS}" fill="url(#plate)"/>
  <rect width="{CANVAS}" height="{CANVAS}" fill="url(#glow)"/>
  <g fill="#FFFFFF">
{bar_svg}
{stem_svg}
      <polygon points="{poly}"/>
{cap_svg}
  </g>
  <polygon points="{tri_svg}" fill="#22C55E"/>
</svg>
"""


def _measure(image: Image.Image) -> tuple[tuple[int, int], float]:
    """Alpha bounding box and extreme radius from the canvas centre, in px."""
    alpha = np.array(image.convert("RGBA"))[..., 3]
    ys, xs = np.nonzero(alpha > 8)
    half = CANVAS / 2.0
    radius = float(np.sqrt((xs - half) ** 2 + (ys - half) ** 2).max())
    return (int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)), radius


def main() -> None:
    icon = _render(STROKE_APP_ICON, plated=True)
    foreground = _render(STROKE_FOREGROUND, plated=False)
    monochrome = _render(STROKE_FOREGROUND, plated=False, mono=True)
    splash = _render(STROKE_SPLASH, plated=False)

    outputs = {
        "jarumba-icon.png": icon,
        "jarumba-adaptive-foreground.png": foreground,
        "jarumba-monochrome.png": monochrome,
        "jarumba-splash.png": splash,
        "jarumba-favicon.png": icon.resize((48, 48), Image.LANCZOS),
    }
    for name, image in outputs.items():
        path = os.path.join(OUT_DIR, name)
        image.save(path, "PNG", optimize=True)
        print(f"wrote {path} {image.size}")

    # Android masks the central 72dp of the 108dp adaptive-icon layer: make sure
    # the foreground mark survives a circular mask with nothing cut off.
    mask_radius = CANVAS / 2.0 * 72.0 / 108.0
    (fw, fh), front_radius = _measure(foreground)
    print(
        f"adaptive foreground mark {fw}x{fh}px, extreme radius {front_radius:.1f}px, "
        f"72dp mask radius {mask_radius:.1f}px"
    )
    print(
        "app icon mark "
        f"{MARK_W_UNITS * STROKE_APP_ICON:.0f}x{MARK_H_UNITS * STROKE_APP_ICON:.0f}px, "
        "splash mark "
        f"{MARK_W_UNITS * STROKE_SPLASH:.0f}x{MARK_H_UNITS * STROKE_SPLASH:.0f}px"
    )
    if front_radius > mask_radius:
        raise SystemExit("foreground mark leaves the 72dp adaptive-icon safe circle")

    svg_path = os.path.join(OUT_DIR, "jarumba-logo.svg")
    with open(svg_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_svg(STROKE_APP_ICON))
    print(f"wrote {svg_path}")


if __name__ == "__main__":
    main()
