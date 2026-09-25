# Jarumba Music branding

Original logo and app-icon artwork for the Jarumba Music Android app. Nothing
in here is derived from another music brand: no three-bar/circle mark, no
headphones, no microphone, no lettering.

## The mark

A geometric "J" (top bar + right stem + circular hook) with a restrained
electric-green play triangle nested inside the hook. Every part is derived from
a single stroke width, so the proportions never drift between sizes.

## Palette

| Role | Value | Notes |
| --- | --- | --- |
| Plate gradient start | `#0A1521` | near-black navy |
| Plate gradient end | `#06100B` | matches `constants/theme.ts` `bgBase` (`#07100B`) |
| Glyph | `#FFFFFF` | the "J" |
| Accent | `#22C55E` | play triangle, matches theme `accentPrimary` |

## Files

| File | Size | Used by |
| --- | --- | --- |
| `jarumba-icon.png` | 1024×1024 opaque | `expo.icon` (launcher icon, store listing) |
| `jarumba-adaptive-foreground.png` | 1024×1024 transparent | `expo.android.adaptiveIcon.foregroundImage` |
| `jarumba-monochrome.png` | 1024×1024 transparent | `expo.android.adaptiveIcon.monochromeImage` (themed icons) |
| `jarumba-splash.png` | 1024×1024 transparent | `expo-splash-screen` `image` |
| `jarumba-favicon.png` | 48×48 | `expo.web.favicon` |
| `jarumba-logo.svg` | vector | master artwork for docs, web or print |

`expo.android.adaptiveIcon.backgroundColor` is `#06100B`, so no background
image is shipped: a flat brand colour cannot be cropped or misaligned by a
launcher.

## Safe areas

Android scales the adaptive-icon foreground over 108dp and masks the central
72dp with a circle, so the foreground mark is sized to stay inside that circle
(measured extreme radius must stay under 341px of the 1024px canvas). The
generator fails if that ever stops being true.

## Regenerating

```bash
python assets/branding/tools/generate_brand_assets.py
```

Requires `pillow` and `numpy`. The generator writes every PNG above plus the
SVG master, and prints the measured mark sizes and safe-area check.
