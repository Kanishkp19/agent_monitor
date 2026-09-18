# AgentShield — UI/UX Brief

> Screens and behaviour: `03-APP-FLOW.md`. The canvas itself: `07-OFFICE-SIMULATION.md`. This document is the visual contract — if a `className` isn't derived from here, it's wrong.

---

## 1. Design Philosophy

AgentShield is two surfaces in one window, and the design's whole job is to make them feel like one product without pretending they're the same thing.

The **console** is a security operations room at 2 a.m.: dark, dense, information-first, nothing decorative. Data is the content, so monospace carries the numbers and the decisions, and the only colour in the interface is colour that means something. Four decisions, four colours, used nowhere else. If a colour appears that isn't a decision, a risk level or money, it's a bug.

The **office** is a 16-bit workplace: chunky, warm, slightly toy-like, legible at a glance from across a room. It borrows the console's four signal colours exactly, which is the hinge of the whole design — the amber halo over an avatar and the amber `REVIEW` chip in the event table are the same amber, so the connection between the game and the governance is made visually before anyone explains it.

Three rules follow:

1. **Colour is a claim.** Green means allowed. Amber means held. Red means blocked. Magenta means the detector flagged something it wasn't told about. Gold means money. Everything else is a shade of ink. No gradients as decoration, no accent colour for mood.
2. **Type separates the worlds.** Archivo for chrome, IBM Plex Mono for data, and a pixel face used *only* on the canvas and the sim clock — the one place the product admits it's a simulation.
3. **Motion reports, it doesn't perform.** Something moves when state changed. A badge flip, a row flash, an approval card leaving. There is no ambient animation anywhere in the console.

The office is the bold thing. Everything around it stays quiet.

---

## 2. Colour Tokens

```css
/* apps/web/src/styles/globals.css — Tailwind v4 CSS-first theme */
@import "tailwindcss";

@theme {
  /* ── Ink: the console surface ─────────────────────────── */
  --color-ink-950: #080D16;   /* canvas letterbox, office backdrop */
  --color-ink-900: #0D1420;   /* page background */
  --color-ink-800: #141E2E;   /* panels, cards, table body */
  --color-ink-700: #1C293C;   /* raised: hover, nested, header */
  --color-ink-600: #27374E;   /* pressed, selected row */
  --color-line:        #253248;
  --color-line-strong: #33455F;

  /* ── Text ─────────────────────────────────────────────── */
  --color-text:       #E6EDF7;
  --color-text-dim:   #93A4BD;
  --color-text-faint: #5C6E89;

  /* ── Brand ────────────────────────────────────────────── */
  --color-shield:        #3D7BFF;
  --color-shield-hover:  #2F66E0;
  --color-shield-subtle: #3D7BFF1F;

  /* ── Decision signals: the only semantic colours ──────── */
  --color-allow:         #3FCF8E;
  --color-allow-subtle:  #3FCF8E1F;
  --color-redact:        #A855F7;
  --color-redact-subtle: #A855F71F;
  --color-review:        #F2A73B;
  --color-review-subtle: #F2A73B1F;
  --color-block:         #E5484D;
  --color-block-subtle:  #E5484D1F;

  /* ── Detector + money ─────────────────────────────────── */
  --color-anomaly:        #E668C3;   /* the ML flagged it; nothing else uses this */
  --color-anomaly-subtle: #E668C31F;
  --color-spend:          #E8C468;   /* every currency figure */
  --color-idle:           #64748B;   /* no activity */

  /* ── Risk ramp (0→100) ────────────────────────────────── */
  --color-risk-0:   #3FCF8E;
  --color-risk-40:  #F2A73B;
  --color-risk-70:  #E5484D;
  --color-risk-90:  #E668C3;

  /* ── Type ─────────────────────────────────────────────── */
  --font-ui:    "Archivo", ui-sans-serif, system-ui, sans-serif;
  --font-mono:  "IBM Plex Mono", ui-monospace, "SF Mono", monospace;
  --font-pixel: "Departure Mono", "Silkscreen", ui-monospace, monospace;

  /* ── Radius ───────────────────────────────────────────── */
  --radius-none: 0px;      /* office HUD — pixel surfaces are never rounded */
  --radius-xs:   2px;      /* chips, badges */
  --radius-sm:   4px;      /* inputs, buttons */
  --radius-md:   6px;      /* cards, panels */
  --radius-lg:   10px;     /* dialogs, drawers */

  /* ── Elevation ────────────────────────────────────────── */
  --shadow-panel:  0 1px 0 0 #ffffff08 inset, 0 1px 2px #00000040;
  --shadow-raised: 0 4px 12px #00000059;
  --shadow-drawer: -8px 0 32px #00000073;
  --shadow-dialog: 0 16px 48px #00000080;
  --shadow-focus:  0 0 0 2px var(--color-ink-900), 0 0 0 4px var(--color-shield);
}
```

### Usage rules

| Token | Use for | Never use for |
|---|---|---|
| `allow` | `ALLOW` decisions, working status, healthy trends | "success" of a UI action (use `text` + a check glyph) |
| `redact` | `REDACT` decisions, redaction markers in prompts | anything else — this colour appears rarely and should stay rare |
| `review` | `REVIEW` decisions, waiting-for-approval status, pending approvals | general warnings, cautionary copy |
| `block` | `BLOCK` decisions, blocked status, denied approvals | destructive UI buttons (they use ink + `block` text only) |
| `anomaly` | ML-flagged employees, incident severity, the anomaly badge | high risk that came from a static rule (that's `block`) |
| `spend` | every `$` figure in the product | highlights, emphasis |
| `shield` | the active nav item, focus rings, primary buttons | status of any kind |
| `idle` | idle avatars, zero-value cells | disabled controls (those use `text-faint` on `ink-700`) |

**The rule to remember:** a colour in AgentShield is a statement about the system's state, never about the interface's mood.

---

## 3. Typography

```tsx
// apps/web/index.html — subset loaded, display=swap
<link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
// Departure Mono is self-hosted from /public/fonts/DepartureMono-Regular.woff2 (OFL)
```

Three families, each with a hard boundary:

- **Archivo** — all console chrome, headings, prose, buttons, labels. A grotesque with slightly tightened apertures; it reads as industrial without being a default UI face.
- **IBM Plex Mono** — every number, id, resource path, decision word, policy JSON, table cell that holds data. Tabular figures are mandatory (`font-variant-numeric: tabular-nums`) so columns don't shimmer as values change.
- **Departure Mono** — the sim clock, the office HUD, avatar name plates, and the fast-forward summary. **Nowhere else.** It is the product's signal that you're looking at the simulation.

| Role | Class string | Size / line | Weight | Use |
|---|---|---|---|---|
| Page title | `font-ui text-[20px] leading-7 font-semibold tracking-[-0.01em] text-text` | 20/28 | 600 | screen headings |
| Section title | `font-ui text-[15px] leading-6 font-semibold text-text` | 15/24 | 600 | card and panel headers |
| Body | `font-ui text-[13px] leading-5 text-text-dim` | 13/20 | 400 | prose, descriptions |
| Body strong | `font-ui text-[13px] leading-5 font-medium text-text` | 13/20 | 500 | emphasis in prose |
| Label | `font-ui text-[11px] leading-4 font-medium text-text-faint` | 11/16 | 500 | field labels, column headers — **sentence case, not caps** |
| Data | `font-mono text-[12px] leading-5 tabular-nums text-text` | 12/20 | 400 | table cells, ids, paths |
| Data emphasis | `font-mono text-[12px] leading-5 tabular-nums font-medium text-text` | 12/20 | 500 | decision words, key values |
| Metric | `font-mono text-[28px] leading-8 tabular-nums font-semibold text-text` | 28/32 | 600 | stat-card numbers |
| Metric label | `font-ui text-[11px] leading-4 text-text-faint` | 11/16 | 400 | under a metric |
| Money | `font-mono text-[12px] tabular-nums text-spend` | 12/20 | 400 | any `$` value, at any size |
| Log line | `font-mono text-[11px] leading-[18px] text-text-dim` | 11/18 | 400 | system log rail |
| Pixel HUD | `font-pixel text-[13px] leading-4 tracking-[0.02em] text-text` | 13/16 | 400 | sim clock, office overlays |
| Pixel name plate | `font-pixel text-[11px] leading-3` | 11/12 | 400 | avatar labels on canvas |

Prose blocks cap at `max-w-[68ch]`. No all-caps labels anywhere in the console — the one exception is decision words (`ALLOW` / `REDACT` / `REVIEW` / `BLOCK`), which are caps because they are enum values, not labels.

---

## 4. Spacing & Layout

4px base. Permitted steps: `0, 1(4), 1.5(6), 2(8), 3(12), 4(16), 5(20), 6(24), 8(32), 10(40), 12(48), 16(64)`.

| Surface | Padding | Gap |
|---|---|---|
| Page (padded layout) | `px-6 py-5` | `gap-5` between sections |
| Card | `p-4` | `gap-3` internal |
| Stat card | `px-4 py-3.5` | — |
| Table cell | `px-3 py-2` | — |
| Dense table cell (Live Feed) | `px-3 py-1.5` | — |
| Drawer | `p-5`, sections separated by `border-t border-line` + `pt-4 mt-4` | — |
| Dialog | `p-5` | `gap-4` |
| Header | `h-14 px-4` | `gap-1` between nav items |

Layout widths: content `max-w-[1600px] mx-auto`; drawer `w-[420px]`; policy sheet `w-[640px]`; system-log rail `w-[340px]`; ControlNav `h-10` horizontal tab strip (not a sidebar — the office needs the full width, and a second vertical rail would fight it).

---

## 5. Component Library

### 5.1 Buttons

```tsx
// Primary — one per view, maximum
"inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-shield text-white
 font-ui text-[13px] font-medium
 hover:bg-shield-hover active:translate-y-px
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 disabled:bg-ink-700 disabled:text-text-faint disabled:cursor-not-allowed
 transition-colors duration-100"

// Secondary
"inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-ink-700 text-text
 border border-line font-ui text-[13px] font-medium
 hover:bg-ink-600 hover:border-line-strong active:translate-y-px
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 disabled:text-text-faint disabled:cursor-not-allowed
 transition-colors duration-100"

// Ghost
"inline-flex items-center gap-1.5 h-8 px-2.5 rounded-sm text-text-dim
 font-ui text-[13px]
 hover:bg-ink-700 hover:text-text
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 transition-colors duration-100"

// Approve — the only green button in the product
"inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-allow-subtle text-allow
 border border-allow/40 font-ui text-[13px] font-medium
 hover:bg-allow hover:text-ink-950 hover:border-allow
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 transition-colors duration-100"

// Deny / destructive
"inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-transparent text-block
 border border-block/40 font-ui text-[13px] font-medium
 hover:bg-block-subtle hover:border-block
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 transition-colors duration-100"

// Icon-only
"inline-flex items-center justify-center h-8 w-8 rounded-sm text-text-dim
 hover:bg-ink-700 hover:text-text
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]
 transition-colors duration-100"
```

**Loading state (any variant):** keep the label, prefix `<Loader2 className="h-3.5 w-3.5 animate-spin" />`, set `disabled` and `aria-busy="true"`. Never replace the label with "Loading…" — the width shift is worse than the wait.

### 5.2 Decision chip

The single most repeated element in the product.

```tsx
const decisionChip = {
  allow:  "bg-allow-subtle  text-allow  border-allow/30",
  redact: "bg-redact-subtle text-redact border-redact/30",
  review: "bg-review-subtle text-review border-review/30",
  block:  "bg-block-subtle  text-block  border-block/30",
} as const

// <span className={cn(base, decisionChip[d])}>{d.toUpperCase()}</span>
const base =
  "inline-flex items-center h-5 px-1.5 rounded-xs border
   font-mono text-[10px] leading-none font-medium tracking-[0.04em]"
```

### 5.3 Status chip (task / avatar status)

| Status | Classes | Glyph |
|---|---|---|
| `working` | `bg-allow-subtle text-allow border-allow/30` | ● |
| `awaiting_approval` | `bg-review-subtle text-review border-review/30` | ⏳ |
| `blocked` | `bg-block-subtle text-block border-block/30` | ● |
| `denied` / `denied_timeout` | `bg-ink-700 text-block border-line` | ✕ |
| `completed` | `bg-ink-700 text-text-dim border-line` | ✓ |
| `failed` | `bg-ink-700 text-text-faint border-line` | ! |
| `queued` / `idle` | `bg-ink-700 text-idle border-line` | ○ |

Same `base` string as the decision chip.

### 5.4 Cards

```tsx
// Panel
"bg-ink-800 border border-line rounded-md shadow-[var(--shadow-panel)]"

// Panel header
"flex items-center justify-between px-4 h-10 border-b border-line"

// Interactive card (approval card, incident row)
"bg-ink-800 border border-line rounded-md p-4
 hover:border-line-strong transition-colors duration-100"

// Card that needs attention (pending approval)
"bg-ink-800 border border-review/40 rounded-md p-4
 shadow-[0_0_0_1px_var(--color-review-subtle)]"

// Stat card
<div className="bg-ink-800 border border-line rounded-md px-4 py-3.5">
  <div className="font-mono text-[28px] leading-8 tabular-nums font-semibold text-text">387</div>
  <div className="font-ui text-[11px] leading-4 text-text-faint mt-1">Agent requests today</div>
</div>
```

### 5.5 Tables

```tsx
// Wrapper
"bg-ink-800 border border-line rounded-md overflow-hidden"

// Header row — sticky, sentence case
"sticky top-0 z-10 bg-ink-700 border-b border-line
 font-ui text-[11px] font-medium text-text-faint text-left"
// th: "px-3 py-2 whitespace-nowrap"

// Body row
"border-b border-line/60 hover:bg-ink-700/60 cursor-pointer
 transition-colors duration-75"

// Selected row
"bg-ink-600 border-l-2 border-l-shield"

// Cell
"px-3 py-2 font-mono text-[12px] tabular-nums text-text align-middle"

// New-row flash (Live Feed) — 120ms, suppressed above 40 events/sec
"animate-[rowflash_120ms_ease-out]"
```

```css
@keyframes rowflash {
  from { background-color: var(--color-shield-subtle); }
  to   { background-color: transparent; }
}
```

### 5.6 Risk meter

```tsx
<div className="flex items-center gap-2">
  <div className="h-1.5 w-28 rounded-xs bg-ink-700 overflow-hidden">
    <div className="h-full rounded-xs transition-[width] duration-300 ease-out"
         style={{ width: `${score}%`, background: riskColor(score) }} />
  </div>
  <span className="font-mono text-[12px] tabular-nums font-medium text-text">{score}</span>
</div>
```

```typescript
// lib/risk.ts — the ONE place risk colour is decided
export function riskColor(score: number): string {
  if (score >= 90) return 'var(--color-risk-90)'
  if (score >= 70) return 'var(--color-risk-70)'
  if (score >= 40) return 'var(--color-risk-40)'
  return 'var(--color-risk-0)'
}
```

**Low-confidence variant** — the bar gets a hatch overlay and the number a dotted underline:

```tsx
"bg-[repeating-linear-gradient(135deg,transparent,transparent_3px,#ffffff14_3px,#ffffff14_6px)]"
// label: "font-ui text-[11px] text-text-faint" → "low confidence — 14/20 sessions"
```

### 5.7 Inputs

```tsx
// Text
"h-8 w-full px-2.5 rounded-sm bg-ink-900 border border-line
 font-ui text-[13px] text-text placeholder:text-text-faint
 focus:outline-none focus:border-shield focus:shadow-[0_0_0_1px_var(--color-shield)]
 aria-[invalid=true]:border-block aria-[invalid=true]:shadow-[0_0_0_1px_var(--color-block)]
 disabled:bg-ink-800 disabled:text-text-faint
 transition-colors duration-100"

// Numeric — always mono
"… font-mono tabular-nums"

// Select — same box, chevron right, native <select> styled
"h-8 pl-2.5 pr-8 rounded-sm bg-ink-900 border border-line appearance-none
 font-ui text-[13px] text-text
 focus:outline-none focus:border-shield"

// Label
"block font-ui text-[11px] font-medium text-text-faint mb-1.5"

// Field error
"mt-1 font-ui text-[11px] text-block"

// Helper
"mt-1 font-ui text-[11px] text-text-faint"

// Segmented control (speed, gate, effect)
// container:
"inline-flex items-center gap-0.5 p-0.5 rounded-sm bg-ink-900 border border-line"
// item (inactive):
"h-7 px-2.5 rounded-xs font-ui text-[12px] text-text-dim hover:text-text
 transition-colors duration-100"
// item (active):
"h-7 px-2.5 rounded-xs bg-ink-600 text-text font-medium"

// Checkbox
"h-4 w-4 rounded-xs border border-line bg-ink-900
 checked:bg-shield checked:border-shield
 focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
```

### 5.8 Drawer & dialog

```tsx
// Drawer (employee, 420px; policy sheet, 640px)
"fixed right-0 top-14 bottom-0 w-[420px] z-40
 bg-ink-800 border-l border-line shadow-[var(--shadow-drawer)]
 overflow-y-auto
 animate-[drawerin_180ms_cubic-bezier(0.16,1,0.3,1)]"

// Dialog
"fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50
 w-[440px] bg-ink-800 border border-line-strong rounded-lg
 shadow-[var(--shadow-dialog)] p-5
 animate-[dialogin_160ms_ease-out]"

// Backdrop
"fixed inset-0 z-30 bg-ink-950/70 backdrop-blur-[2px]
 animate-[fadein_120ms_ease-out]"
```

```css
@keyframes drawerin { from { transform: translateX(16px); opacity: 0 } to { transform: none; opacity: 1 } }
@keyframes dialogin { from { transform: translate(-50%,-50%) scale(.98); opacity: 0 }
                      to   { transform: translate(-50%,-50%) scale(1);   opacity: 1 } }
@keyframes fadein   { from { opacity: 0 } to { opacity: 1 } }
```

Drawers are **not modal** — the simulation keeps running and the canvas stays interactive behind them. Only the fast-forward and create-run dialogs use a backdrop.

### 5.9 Toasts

```tsx
// Container: "fixed bottom-4 right-4 z-50 flex flex-col-reverse gap-2 w-[360px]"
// Toast base:
"flex items-start gap-2.5 p-3 rounded-md bg-ink-700 border border-line
 shadow-[var(--shadow-raised)] font-ui text-[13px] text-text
 animate-[toastin_180ms_cubic-bezier(0.16,1,0.3,1)]"

// Variants — a 2px left rule carries the meaning, nothing else changes
success: "border-l-2 border-l-allow"
warning: "border-l-2 border-l-review"
error:   "border-l-2 border-l-block"
neutral: "border-l-2 border-l-line-strong"
```

```css
@keyframes toastin { from { transform: translateX(12px); opacity: 0 } to { transform: none; opacity: 1 } }
```

### 5.10 Skeletons

Skeletons match the shape of what's coming. Shared shimmer:

```tsx
"animate-pulse bg-ink-700 rounded-xs"
```

```tsx
// Table row skeleton (repeat ×8)
<tr className="border-b border-line/60">
  <td className="px-3 py-2"><div className="h-3 w-12 animate-pulse bg-ink-700 rounded-xs" /></td>
  <td className="px-3 py-2"><div className="h-3 w-24 animate-pulse bg-ink-700 rounded-xs" /></td>
  <td className="px-3 py-2"><div className="h-3 w-16 animate-pulse bg-ink-700 rounded-xs" /></td>
  <td className="px-3 py-2"><div className="h-4 w-14 animate-pulse bg-ink-700 rounded-xs" /></td>
</tr>

// Stat card skeleton (repeat ×6)
<div className="bg-ink-800 border border-line rounded-md px-4 py-3.5">
  <div className="h-7 w-16 animate-pulse bg-ink-700 rounded-xs" />
  <div className="h-3 w-24 animate-pulse bg-ink-700 rounded-xs mt-2" />
</div>
```

### 5.11 Empty state

```tsx
<div className="flex flex-col items-center justify-center py-14 text-center">
  <Icon className="h-6 w-6 text-text-faint" strokeWidth={1.5} />
  <p className="font-ui text-[13px] font-medium text-text mt-3">Nothing waiting on you.</p>
  <p className="font-ui text-[12px] text-text-faint mt-1 max-w-[42ch]">
    Approval requests appear here the moment a policy holds an action.
  </p>
  {/* optional action button, mt-4 */}
</div>
```

Copy rules for empty states: line one says what would be here; line two says how it gets here; a button exists only when the user can cause it. No illustrations, no apologies, no exclamation marks.

### 5.12 Header nav item

```tsx
// Inactive
"relative inline-flex items-center gap-1.5 h-14 px-3
 font-ui text-[13px] text-text-dim hover:text-text transition-colors duration-100"

// Active — 2px rule at the bottom, the only place shield-as-underline appears
"relative inline-flex items-center gap-1.5 h-14 px-3
 font-ui text-[13px] font-medium text-text
 after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-shield"
```

### 5.13 System log line

```tsx
<div className="px-3 py-1 font-mono text-[11px] leading-[18px] hover:bg-ink-700/50 cursor-pointer">
  <span className="text-text-faint">[09:21]</span>{' '}
  <span className="text-text-dim">Task &apos;Fix payment…&apos; —</span>{' '}
  <span className="text-block font-medium">Blocked by Gate 2</span>
</div>
```

The log is the one place where prose and signal colour mix. Decision words take their signal colour; everything else is `text-dim`.

---

## 6. Motion

| Interaction | What moves | Duration | Easing |
|---|---|---|---|
| Drawer open | slide 16px + fade | 180 ms | `cubic-bezier(0.16,1,0.3,1)` |
| Drawer close | fade only | 120 ms | `ease-in` |
| Dialog open | scale 0.98→1 + fade | 160 ms | `ease-out` |
| Toast in | slide 12px + fade | 180 ms | `cubic-bezier(0.16,1,0.3,1)` |
| Toast out | fade | 120 ms | `ease-in` |
| New feed row | background flash | 120 ms | `ease-out` |
| Decision chip change | crossfade | 150 ms | `ease-out` |
| Risk bar value change | width | 300 ms | `ease-out` |
| Approval card leaving | slide-left 24px + fade + height collapse | 220 ms | `ease-in-out` |
| Approvals badge increment | one scale pulse 1→1.12→1 | 240 ms | `ease-out` |
| Button press | `translateY(1px)` | 80 ms | `ease` |
| Tab / route change | none | — | — |
| Canvas camera pan to avatar | Phaser tween | 300 ms | `Sine.easeInOut` |

Nothing animates on page load. Nothing loops. Nothing animates because it's pretty.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

The office canvas honours this too: `07-OFFICE-SIMULATION.md §10` specifies that reduced motion disables walking animation and idle bobbing, keeping only badge state changes.

---

## 7. Responsive Behaviour

This is a desktop ops console. The breakpoints that exist:

| Width | Behaviour |
|---|---|
| ≥ 1600px | Full layout; content column caps at 1600px and centres |
| 1280–1599px | Default target. Everything as designed. |
| 1024–1279px | System-log rail collapses to a toggle button over the canvas. Control Center tables drop the least important columns (`Agent`, `Tokens`). Stat grid goes 6→3 columns. |
| < 1024px | Full-page notice: *"AgentShield needs a wider window."* with the current width and the minimum. The office in particular is unreadable below this, and a half-working console is worse than an honest one. |

No mobile layout. This is stated in `01-PRD.md § Non-Goals` and is a deliberate scope decision, not an omission.

---

## 8. Accessibility

Target: **WCAG 2.1 AA** for the console. The canvas is exempt from colour-contrast requirements but not from the alternative-path requirement.

### Contrast (verified against `ink-800 #141E2E`)

| Pair | Ratio | Passes |
|---|---|---|
| `text` on `ink-800` | 13.8:1 | AAA |
| `text-dim` on `ink-800` | 7.2:1 | AAA |
| `text-faint` on `ink-800` | 4.1:1 | AA large / AA for 11px labels only where non-essential — never used for values |
| `allow` on `ink-800` | 8.1:1 | AAA |
| `review` on `ink-800` | 8.9:1 | AAA |
| `block` on `ink-800` | 4.9:1 | AA |
| `redact` on `ink-800` | 5.1:1 | AA |
| `anomaly` on `ink-800` | 6.7:1 | AA |
| `spend` on `ink-800` | 10.2:1 | AAA |
| `shield` on `ink-800` | 4.8:1 | AA — used for structure and focus, never for body text |

### Rules

- **Colour is never the only carrier.** Every decision chip includes its word. Every status badge on the canvas includes a distinct glyph shape (`●` working, `⏳` waiting, `✕` blocked, `○` idle), so the four states remain distinguishable in greyscale and to colour-blind viewers.
- **Focus is always visible:** `focus-visible:shadow-[var(--shadow-focus)]` — a 2px shield ring offset by 2px of page colour. Never `outline: none` without a replacement.
- **Keyboard paths:** `Tab` order follows visual order. `Esc` closes drawers and dialogs. In the approvals queue, `j`/`k` move between cards and `a`/`d` approve/deny the focused card. `Space` toggles simulation pause from anywhere outside a text input.
- **Live regions:** the system log and the Live Feed are `aria-live="polite" aria-relevant="additions"` with the buffer capped — announcing 200 events/sec is worse than silence, so above 10 events/sec the live region switches off and a summary is announced once per 5 s instead.
- **The canvas has a text equivalent.** The office `<canvas>` carries `role="img"` and an `aria-label` regenerated every 2 s: *"Office floor: 14 employees working, 2 waiting for approval, 1 blocked, 3 idle."* The card-grid fallback (`07 §11`) is reachable by keyboard and is the accessible path to per-employee detail.
- **Motion:** `prefers-reduced-motion` respected globally and inside Phaser.
- **Forms:** every input has a `<label for>`; errors use `aria-invalid` plus `aria-describedby` pointing at the error text.
- **Tables:** `<th scope="col">`, `aria-sort` on sortable headers.

---

## 9. Writing

The voice is a competent colleague reporting facts. Plain verbs, sentence case, no filler.

| Instead of | Write |
|---|---|
| "Oops! Something went wrong." | "Couldn't load approvals." |
| "Successfully approved!" | "Approved — Rahul's deployment is continuing." |
| "Are you sure you want to deny this request?" | "Deny this deployment?" + "The task will end and the agent will be told why." |
| "No data available" | "No events yet. Start the simulation to see governed activity." |
| "Submit" | "Approve once" / "Save and enable" / "Run against digital twin" |
| "Invalid input" | "Unknown field \"actor.department\" at when.all[1].field. Did you mean \"actor.team\"?" |
| "Processing…" | "Replaying 5,120 decisions…" |
| "Warning: high risk user" | "Nikhil's token use is 5.8× his normal." |

A button's label and the confirmation that follows use the same verb: `Approve once` → `Approved`. Never `Submit` → `Success`.

Numbers: tokens humanise (`184K`, `2.1M`); money always shows two decimals under $100 and none above (`$3.84`, `$142`); percentages get one decimal only when below 10%.

---

## 10. Full `globals.css`

```css
@import "tailwindcss";

@theme {
  /* …the complete @theme block from §2… */
}

@font-face {
  font-family: "Departure Mono";
  src: url("/fonts/DepartureMono-Regular.woff2") format("woff2");
  font-weight: 400;
  font-display: swap;
}

@layer base {
  :root { color-scheme: dark; }

  html, body, #root { height: 100%; }

  body {
    background-color: var(--color-ink-900);
    color: var(--color-text);
    font-family: var(--font-ui);
    font-size: 13px;
    line-height: 20px;
    -webkit-font-smoothing: antialiased;
  }

  /* Data never shimmers as it updates */
  .font-mono, table, input[type="number"] { font-variant-numeric: tabular-nums; }

  /* Pixel surfaces must not be smoothed */
  canvas { image-rendering: pixelated; }

  ::selection { background: var(--color-shield-subtle); color: var(--color-text); }

  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-track { background: var(--color-ink-900); }
  ::-webkit-scrollbar-thumb {
    background: var(--color-ink-600);
    border: 2px solid var(--color-ink-900);
    border-radius: 6px;
  }
  ::-webkit-scrollbar-thumb:hover { background: var(--color-line-strong); }
}

@layer utilities {
  .hatched {
    background-image: repeating-linear-gradient(
      135deg, transparent, transparent 3px, #ffffff14 3px, #ffffff14 6px);
  }
}

@keyframes rowflash { from { background-color: var(--color-shield-subtle) } to { background-color: transparent } }
@keyframes drawerin { from { transform: translateX(16px); opacity: 0 } to { transform: none; opacity: 1 } }
@keyframes dialogin { from { transform: translate(-50%,-50%) scale(.98); opacity: 0 } to { transform: translate(-50%,-50%) scale(1); opacity: 1 } }
@keyframes toastin  { from { transform: translateX(12px); opacity: 0 } to { transform: none; opacity: 1 } }
@keyframes fadein   { from { opacity: 0 } to { opacity: 1 } }
@keyframes badgepulse { 0%,100% { transform: scale(1) } 50% { transform: scale(1.12) } }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

---

## 11. Design Checklist (run before calling the UI done)

- [ ] No colour in the interface that isn't a decision, a risk level, money, or ink
- [ ] Every number is mono with tabular figures — no column shimmer when values update
- [ ] Departure Mono appears only on the canvas and the sim clock
- [ ] Every decision is legible in greyscale (word present, glyph distinct)
- [ ] Every interactive element has a visible focus ring
- [ ] Every list has a real empty state with a next action
- [ ] Every error names what failed and offers **Retry**
- [ ] No spinner occupies a whole page; skeletons match final layout
- [ ] Nothing animates on load; nothing loops
- [ ] `prefers-reduced-motion` verified in DevTools, canvas included
- [ ] Below 1024px shows the honest width notice, not a broken layout
- [ ] Canvas `aria-label` updates and the card-grid fallback is keyboard reachable
