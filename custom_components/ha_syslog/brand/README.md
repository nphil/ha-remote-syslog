# Brand assets

Home Assistant serves these directly for **custom** integrations: the core
`brands` component checks `Integration.has_branding` (true when a top-level
`brand/` directory exists) and reads the image out of
`<integration>/brand/<image>.png`, falling back to the CDN only when there is
no local file. So no submission to home-assistant/brands is needed for the
icon to appear.

Filenames and the fallback chain are core's, from
`homeassistant/components/brands/const.py`:

| file | falls back to |
|---|---|
| `icon.png` | (required, 256x256) |
| `icon@2x.png` | `icon.png` |
| `logo.png` | `icon.png` |
| `logo@2x.png` | `logo.png`, `icon.png` |
| `dark_icon.png` | `icon.png` |
| `dark_logo.png` | `dark_icon.png`, `logo.png`, `icon.png` |
| `dark_icon@2x.png` | `icon@2x.png`, `icon.png` |
| `dark_logo@2x.png` | `dark_icon@2x.png`, `logo@2x.png`, `logo.png`, `icon.png` |

All eight are provided rather than relying on the chain, so the dark-theme
variants get a light plate instead of a dark mark on a dark header.

`icon.svg` in the repo root is the authored source; `tools/render_brand.py`
regenerates every PNG from the same geometry.
