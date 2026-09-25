# Jarumba Music branding

This directory contains the supplied, authoritative Jarumba Music artwork and
platform derivatives generated directly from it. The logo is not redrawn or
recolored by the build tooling.

## Files

| File | Size | Used by |
| --- | --- | --- |
| `jarumba-source.png` | 1024×1024 RGBA | immutable supplied source artwork |
| `jarumba-icon.png` | 1024×1024 RGBA | `expo.icon` launcher/store icon |
| `jarumba-adaptive-foreground.png` | 1024×1024 RGBA | `expo.android.adaptiveIcon.foregroundImage` |
| `jarumba-splash.png` | 1024×1024 RGBA | `expo-splash-screen` image |
| `jarumba-favicon.png` | 48×48 RGB | `expo.web.favicon` |

The supplied source is verified by SHA-256 before any derivative is written.
The adaptive foreground and splash image use a color-keyed alpha extraction from
that exact source; retained artwork RGB pixels are not changed. The adaptive
foreground is uniformly resized and padded inside Android's central 72/108
safe circle. `app.json` supplies the flat adaptive/splash background color.

## Regenerating

From `apps/mobile`:

```bash
python assets/branding/tools/generate_brand_assets.py
```

Requires Pillow. The utility writes the configured PNG derivatives and does
not modify application code or Expo runtime configuration.
