# Theme And Branding

Use this when defining reusable branding tokens and visual defaults for any PBIR report.

## Theme Source

- Keep theme JSON in `StaticResources/SharedResources/BaseThemes/<theme-name>.json`.
- Reference it in `report.json -> themeCollection.baseTheme`.
- Keep report-level overrides minimal; prefer theme-driven defaults.

## Recommended Token System

- `primary`, `secondary`, `accent`
- `positive`, `warning`, `negative`
- `textPrimary`, `textSecondary`, `surface`, `surfaceAlt`, `border`
- Define all tokens once, then consume in visual styles.

## Common Visual Styling Pattern

- Border on most analytic visuals:
  - `show: true`
  - `radius: 5D` or `6D`
  - `width: 1D` or `2D`
  - `color`: token-driven (`border`).
- Background:
  - analytics: `show: true`, low transparency
  - decorative/navigation layers: often `show: false`
- Drop shadow:
  - disabled by default
  - enabled only on selected emphasis surfaces.

## Typography Pattern

- Define theme `textClasses` (`callout`, `title`, `header`, `label`) with explicit size and fontFace.
- Keep one primary UI font family and one optional accent font.
- Override at visual level only when a specific UX requirement exists.

## UX Asset Pattern

- Store logos/icons/backgrounds in `RegisteredResources`.
- Bind assets through `ResourcePackageItem` in `page.json` or `visual.json`.
- Avoid external URLs for deterministic packaging and portability.
