---
version: alpha
name: Greenhouse
description: >
  Mission control for a living thing. The ccoli dashboard is reframed as the
  sunlit glass house where a single owner tends one broccoli voice-robot. A
  dominant field of living greens (sampled from the ccoli mascot SVG) carries
  the whole UI; one warm carrot accent owns every "live / act / focus" signal;
  a blush pink is held in reserve strictly for the speaking/affection moment.
  Built with the frontend-design skill to be distinctive and atmospheric rather
  than a generic Apple/SaaS clone. Type pairs a characterful display serif
  (Fraunces) with a tight grotesque body (Inter Tight) and a console mono
  (Space Mono) for telemetry. Light = "day greenhouse"; dark = "greenhouse at
  dusk" (and dark is the default).

fonts:
  display: '"Fraunces", Georgia, serif (+ system CJK fallbacks)'
  text: '"Inter Tight", system-ui, sans-serif (+ system CJK fallbacks)'
  mono: '"Space Mono", "SF Mono", Consolas, monospace'
  loaded_from: Google Fonts (single <link>, display=swap, Latin subset)

colors:
  # greens (mascot-derived)
  sprout: "#5fb24a"        # bright leaf — live glow, decorative
  stem: "#3d8b2f"          # mid green — borders, stem rail, leaf nodes
  canopy: "#2f7d33"        # deep crown — strong brand fills
  forest: "#1c3320"        # near-black green — primary ink (light)
  primary: "#1f6b29"       # AA-safe green text/links/borders (light)
  primary-on-dark: "#7fc96a"
  # warm accent (the one sharp accent)
  carrot: "#ef7a2c"        # bright — rings, focus, glow, active bud
  carrot-deep: "#b3500f"   # AA button fill for white text
  apricot: "#fbbf6b"       # soft warm — gradient stops
  blush: "#f4a0a0"         # RESERVED — live/voice/affection only
  # surfaces (light)
  canvas: "#f2f6ea"        # warm greenhouse mist (page bg)
  canvas-parchment: "#e9efdd"
  surface-card: "#ffffff"
  surface-subtle: "#eef3e4"
  surface-black: "#0c130c" # instrument-strip housing
  hairline: "rgba(28,51,32,.14)"
  ink-muted-48: "#4f6047"  # AA muted on light
  # status
  green-status: "#2f9e44"
  danger: "#cf3b2a"
  bar-warn: "#f0a830"
  bar-error: "#ff6a5a"

dark:
  canvas: "#0e1510"        # near-black olive
  canvas-parchment: "#141d15"
  surface-card: "#19231a"
  surface-subtle: "#141d15"
  surface-black: "#0a100b"
  ink: "#eaf2e2"
  body: "#d4e0c6"
  ink-muted-48: "#9bb08f"
  primary: "#7fc96a"
  green-status: "#5fc46a"
  hairline: "rgba(180,220,150,.14)"

glows:
  green-glow: "rgba(95,178,74,.22)"
  carrot-glow: "rgba(239,122,44,.36)"
  blush-tint: "rgba(244,160,160,.5)"
  emotion-glow: "var(--green-glow) (→ carrot when emotion is happy/excited)"

radii:
  xs: 5px
  sm: 9px
  md: 13px
  lg: 18px
  floret: "20px 20px 20px 6px"   # organic asymmetric card silhouette
  pill: 9999px

spacing: { xxs: 4px, xs: 8px, sm: 12px, md: 17px, lg: 24px, xl: 32px, xxl: 48px, section: 80px }
---

## Overview

Greenhouse turns a dry STT→LLM→TTS runtime console into the habitat of a living
companion. The emotional posture is *checking on something alive*: a connected
robot is a thriving plant, a disconnected one goes dormant. The aesthetic is a
botanical skin stretched over an instrument-grade, legible diagnostics tool — it
must never tip into a whimsical toy that hides the data.

**Key characteristics**
- One dominant color world (greens) + exactly one sharp accent (carrot). No blue.
- Blush pink is reserved — it appears only on the assistant chat bubble and the
  "the robot just spoke" flash. Its scarcity is what makes it legible.
- Atmosphere over flat solids: a sun-through-glass radial glow, a faint
  leaf-vein "living paper" texture, and slow dappled light.
- A few high-impact motion moments, not scattered micro-interactions.
- Distinctive, non-generic type: Fraunces / Inter Tight / Space Mono.

## Colors

### Light = "day greenhouse"
Page sits on warm **mist** `#f2f6ea` (never pure white). Cards are white glass
with the floret radius. Primary ink is **forest** `#1c3320`. Green text/links use
the AA-safe **primary** `#1f6b29`; brighter greens (`sprout`, `stem`, `canopy`)
are for fills, the stem rail, leaf nodes, and glows — not small text.

### Dark = "greenhouse at dusk" (default theme)
Canvas drops to near-black olive `#0e1510`; cards become warm olive glass
`#19231a`. Text is warm off-white `#eaf2e2`; greens brighten for contrast.
**The default theme is dark** (`localStorage "ccoli.theme"` defaults to `dark`).

> **Theme contract (load-bearing):** dark tokens live under `[data-theme="dark"]`
> and light is the bare `:root`. `applyTheme()` sets `data-theme="dark"` for dark
> and *removes* the attribute for light. (A prior mismatch made dark mode a no-op;
> keep these in sync.)

### The one accent
**Carrot** owns live status, primary CTAs, focus rings, the sprouting voice
rings, and the active nav bud. Primary buttons use **carrot-deep** `#b3500f`
with white text to clear WCAG-AA; bright **carrot** `#ef7a2c` is used only where
it does not carry small text (rings, glow, focus outline, the active bud).

## Typography

- **Display — Fraunces:** hero headline, card titles (`.title-clamp`, `.hero-title`,
  `.bar-brand`). Warm, organic, hand-grown — the brand voice. Weight ~560.
- **Body — Inter Tight:** all UI copy, labels, nav, forms. Crisp and tight at
  13–16px so the data layer stays legible under the warmth. Base 16px / 1.5.
- **Mono — Space Mono:** every machine readout — metric values, kickers,
  detail-list terms, the config JSON and live logs (rendered in dark "terminal"
  wells), and the top instrument strip. Reads as telemetry off a device.
- **Kicker:** Space Mono, uppercase, `.14em` tracking, primary green, with a
  small leaf-bullet `::before`.
- **CJK:** Fraunces / Inter Tight / Space Mono cover no Korean/Japanese/Chinese,
  so every `--font-*` token falls through to system + Noto CJK fonts. Never let a
  Latin display face apply to CJK text.

## Layout

- **Shell:** 280px sidebar + fluid main, max 1440px, on the mist canvas.
- **Sidebar = growing stem:** a vertical green gradient rail (`.nav::before`);
  each nav item hangs a leaf node off the rail (`.nav button::before`). The
  **active** tab becomes a sprouted carrot **bud** with a glow.
- **Hero = terrarium:** a soft-domed figure (`44px 44px md md` radius) with a
  radial sun-glow behind the mascot and a soil-band gradient at the base; the
  note is a mono "grower's tag".
- **Surfaces:** glass cards at `--radius-floret` with a 1px inner top highlight.
- **Top bar = instrument strip:** dark housing in both themes, mono readouts,
  the WS dot as a glowing signal node, an apricot top sheen.
- Responsive breakpoints unchanged: 1280 / 1068 / 734 / 640.

## Motion (signatures)

All gated by `@media (prefers-reduced-motion:reduce)`.
- **Sprouting voice rings:** `.dot.live` emits concentric leaf-vein rings; they
  flash carrot while `.ccoli-speaking` is set (the robot just spoke).
- **Lightly-alive mascot:** `#hero-mascot` breathes (4s). `body.is-live` →
  thriving; otherwise grayscaled/slower (dormant). On `data-emotion` happy/excited
  the sun glow warms to carrot.
- **Germination:** cards rise + fade in with a small nth-child stagger on load
  and tab switch. Tabs "unfurl" via `tabIn`.
- **Dappled light:** two low-opacity blurred blobs drift behind the page.

## Accessibility

- Visible **`:focus-visible`** carrot ring on every interactive element
  (replaces the old `outline:none`).
- **≥44px** touch targets for nav, buttons, locale select, theme toggle, and the
  top-bar controls at the 734px breakpoint.
- Status is never color-only: the live node animates + pairs with `#ws-label`;
  warn/error keep textual values.
- Skip-link to `#main`; `aria-label` (localized) on the memory editor.
- Contrast: forest/off-white body text and the AA greens/carrot-deep fills target
  WCAG-AA; verify accent pairings with a checker when tuning hexes.

## Do's and Don'ts

**Do**
- Keep carrot as the only accent; reserve blush strictly for live/voice/affection.
- Use Fraunces for titles, Inter Tight for UI, Space Mono for all data/telemetry.
- Tokenize radii and glows (`--radius-floret`, `--green-glow`, `--carrot-glow`,
  `--blush-tint`) — never ad-hoc per element.
- Keep dark as the no-attribute… no: dark is `[data-theme="dark"]`, light is `:root`.

**Don't**
- Don't reintroduce blue/purple or a second accent.
- Don't put bright carrot or mid-green under small text (AA fails) — use
  carrot-deep / primary instead.
- Don't let the botanical metaphor get twee — keep copy professional; the
  greenery lives in the chrome, not the labels.
- Don't add motion outside the reduced-motion gate.
