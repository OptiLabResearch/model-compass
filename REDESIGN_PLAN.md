# Model Compass — Redesign Plan

Target: apply the reference design's **layout, shape language, and component set** across
all three pages, and add an explicit **light/dark toggle**.

This document is written to be executed by an AI model with no prior context on the repo.
Read it top to bottom. Phases are ordered by dependency — do not reorder.

---

## 0. Context an executor needs

**Stack:** three hand-written static HTML pages, no build step, no framework, no npm.

| File | Role |
| --- | --- |
| `index.html` | "Picker" — textarea → model recommendation. ~900px centered column. |
| `shortlist.html` | "Shortlist" — sidebar filters + curated table. Closest to the reference design. |
| `models.html` | "All Models" — sidebar filters + wide 27-column benchmark table. |
| `assets/style.css` | Shared: CSS variables (theme), site nav, footer. 85 lines. |
| `assets/nav.js` | Injects nav + footer into `#site-nav` / `#site-footer`; owns staleness banner logic. |
| `data/models.json` | 166 models. Top-level `scraped_at`, `models[]`. |

Each page has its own `<style>` block for page-specific components. Fonts (Source Serif 4,
Inter, JetBrains Mono) are loaded from Google Fonts in each page's `<head>`.

**Serve locally with `python3 -m http.server`** and open `http://localhost:8000/`.
`file://` will not work — the pages `fetch()` `data/models.json`.

### The central finding

**The palette is already correct.** `assets/style.css` already defines the reference
design's exact warm scheme — `--bg: #F5F4EE`, `--surface: #FAF9F5`, `--accent: #D97757` —
and already has a full dark ramp. Do not "re-palette" the site; you will just move the
colors sideways.

What the site is actually missing, and what this plan delivers, is three things:

1. **Shape language.** The reference is built from soft rounded cards (12–16px radius) with
   hairline borders and a whisper of shadow, floating on the warm background, with generous
   internal padding. The current pages are flat, tight, and square (4–6px radius, 6px cell
   padding, no elevation).
2. **A shared component set.** Stat tiles, a segmented nav, dot-badges, a caption bar above
   the table, two-line table cells. These exist in the reference and nowhere in the codebase.
3. **A theme toggle.** Dark mode currently only responds to `prefers-color-scheme`. There is
   no button, and no way for a visitor to override the OS.

### Decisions already made (do not revisit)

- **Typography:** Inter for all UI. **Source Serif 4 is retained** for the page `<h1>`, the
  brand wordmark, and the big numbers inside stat tiles. JetBrains Mono for all numerics in
  tables and for `<code>`. No new webfonts.
- **Theme toggle:** **2-state, light ⇄ dark only.** The *initial* value is seeded from the
  OS preference, but once the user clicks, the choice is explicit and sticky. There is no
  "back to system" state.

---

## Phase 1 — Token layer (`assets/style.css`)

Everything downstream depends on these tokens. Do this first and do it exactly.

### 1a. Restructure the theme blocks for a manual toggle

The current file puts dark mode in a bare `@media (prefers-color-scheme: dark)`. That cannot
be overridden by a button. Replace the `:root` and `@media` blocks with this three-block
structure. The dark values are duplicated on purpose — it is the one bulletproof
CSS-only pattern, and both copies live in this single file, so they are maintained once.

```css
:root {
  color-scheme: light;
  /* --- light (unchanged from today, plus new tokens) --- */
  --bg: #F5F4EE; --surface: #FAF9F5; --surface-2: #EFEDE4;
  --border: rgba(25,25,25,0.10); --border-strong: rgba(25,25,25,0.16);
  --border-focus: rgba(217,119,87,0.45);
  --text: #191919; --text-secondary: #5c5a53; --text-muted: #8a8778;
  --accent: #D97757; --accent-bg: rgba(217,119,87,0.10);
  --accent-fg: #ffffff;              /* text ON an accent fill */
  --accent-hover: #c96745;
  --row-hover: rgba(217,119,87,0.045);
  --shadow-sm: 0 1px 2px rgba(25,25,25,0.04);
  --shadow-md: 0 1px 3px rgba(25,25,25,0.06), 0 4px 12px rgba(25,25,25,0.04);
  --tooltip-bg: #191919; --tooltip-fg: #ffffff;
  --green-bg: #e3ecdd; --green-dark: #4c6b41;
  --red-bg: #f3ded8;   --red-dark: #a8492f;
  --yellow-bg: #f6ead2; --yellow-dark: #b5792c;
  --blue-bg: #e0e7ff;  --blue-dark: #3730a3;
  --pink-bg: #fce7f3;  --pink-dark: #9d174d;
  --heat-1: #e3ecdd; --heat-2: #f6ead2; --heat-3: #f3ded8;
  /* dot colors for creator/category badges */
  --dot-1: #D97757; --dot-2: #4c6b41; --dot-3: #3730a3;
  --dot-4: #9d174d; --dot-5: #b5792c; --dot-6: #5c5a53;
  /* shape + rhythm */
  --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-pill: 999px;
  --serif: 'Source Serif 4', Georgia, serif;
  --sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  --nav-h: 60px;   /* was 48px — the reference nav is taller */
}

/* Dark, when the OS says dark AND the user has not forced light. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* ...dark values, see 1b... */ }
}

/* Dark, forced by the toggle. Must come last so it beats the media query. */
:root[data-theme="dark"] { /* ...same dark values... */ }
```

### 1b. Dark values (paste into BOTH dark blocks above)

```css
  color-scheme: dark;
  --bg: #1b1a17; --surface: #221f1a; --surface-2: #2a2621;
  --border: rgba(255,255,255,0.12); --border-strong: rgba(255,255,255,0.20);
  --border-focus: rgba(224,138,103,0.55);
  --text: #ECEAE2; --text-secondary: #b8b5a9; --text-muted: #8d8a7e;
  --accent: #E08A67; --accent-bg: rgba(224,138,103,0.16);
  --accent-fg: #1b1a17;              /* dark text on the lighter dark-mode accent */
  --accent-hover: #eb9a79;
  --row-hover: rgba(224,138,103,0.07);
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.30);
  --shadow-md: 0 1px 3px rgba(0,0,0,0.35), 0 4px 12px rgba(0,0,0,0.25);
  --tooltip-bg: #3a3630; --tooltip-fg: #ECEAE2;
  --green-bg: #24361f; --green-dark: #8fbf7d;
  --red-bg: #3a2119;   --red-dark: #e08874;
  --yellow-bg: #3a2f16; --yellow-dark: #e0b45c;
  --blue-bg: #232a4d;  --blue-dark: #aab6f5;
  --pink-bg: #3d1c2c;  --pink-dark: #f0a0c0;
  --heat-1: #24361f; --heat-2: #3a2f16; --heat-3: #3a2119;
  --dot-1: #E08A67; --dot-2: #8fbf7d; --dot-3: #aab6f5;
  --dot-4: #f0a0c0; --dot-5: #e0b45c; --dot-6: #b8b5a9;
```

**Why `--accent-fg` matters:** the codebase currently hardcodes `color:#fff` on every accent
fill (`.preset-btn.active`, `.creator-pill.active`, `#cmp-go`, `.button`, `.filter-count`).
In dark mode the accent lightens to `#E08A67`, and white-on-#E08A67 is roughly 2.3:1 —
unreadable. Every one of those must become `color: var(--accent-fg)`.

### 1c. Add the no-flash script to all three `<head>`s

Without this, a dark-mode user sees a white flash on every navigation. It must be **inline**
(not `nav.js`, which is deferred by position) and it must run **before the first paint**, so
place it immediately after the `<meta charset>` line, above the stylesheet links, in
`index.html`, `shortlist.html`, and `models.html`:

```html
<script>
  (function () {
    try {
      var t = localStorage.getItem('mc-theme');
      if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
    } catch (e) {}
  })();
</script>
```

If `mc-theme` is unset, no attribute is stamped and the `prefers-color-scheme` media query
takes over — that is the "seeded from OS" initial state.

---

## Phase 2 — Shared components (`assets/style.css`)

Add these below the token blocks. They are the vocabulary every page then reuses; **the
per-page `<style>` blocks should shrink, not grow.** Any rule that ends up identical in two
pages belongs here instead.

### 2a. Top bar — brand tile, segmented tabs, actions

The reference nav is: `[orange rounded icon tile] [title + subtitle stack] ... [segmented
control] ... [actions + theme toggle]`.

```css
#site-nav {
  position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; gap: 14px;
  height: var(--nav-h); padding: 0 20px;
  background: var(--surface); border-bottom: 1px solid var(--border);
  font-family: var(--sans);
}
#site-nav .brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
#site-nav .brand-tile {           /* the orange rounded square */
  width: 34px; height: 34px; border-radius: 10px;
  background: var(--accent); color: var(--accent-fg);
  display: grid; place-items: center; font-size: 17px; flex: none;
}
#site-nav .brand-text { display: flex; flex-direction: column; line-height: 1.25; }
#site-nav .brand-name { font-family: var(--serif); font-weight: 600; font-size: 16px; color: var(--text); }
#site-nav .brand-sub  { font-size: 11px; color: var(--text-muted); white-space: nowrap; }

/* Segmented control (replaces the loose tab links) */
#site-nav .tabs {
  display: flex; gap: 2px; margin: 0 auto;          /* centered, per the reference */
  background: var(--surface-2); border-radius: var(--r-pill); padding: 3px;
}
#site-nav a.tab {
  font-size: 13px; font-weight: 500; padding: 6px 16px; border-radius: var(--r-pill);
  color: var(--text-secondary); text-decoration: none; white-space: nowrap;
  transition: background .15s, color .15s;
}
#site-nav a.tab:hover { color: var(--text); }
#site-nav a.tab.active {
  background: var(--surface); color: var(--text); font-weight: 600;
  box-shadow: var(--shadow-sm);
}
#site-nav .nav-actions { display: flex; align-items: center; gap: 8px; }
```

### 2b. Theme toggle button

```css
.theme-toggle {
  width: 36px; height: 36px; border-radius: 50%; flex: none;
  display: grid; place-items: center; cursor: pointer;
  background: transparent; border: 1px solid var(--border);
  color: var(--text-secondary); font-size: 15px; line-height: 1;
  transition: background .15s, color .15s, border-color .15s;
}
.theme-toggle:hover { background: var(--surface-2); color: var(--text); border-color: var(--border-strong); }
.theme-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

### 2c. Buttons

```css
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; font-family: var(--sans); font-size: 13px; font-weight: 600;
  border-radius: var(--r-pill); border: 1px solid transparent; cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
}
.btn-primary { background: var(--accent); color: var(--accent-fg); }
.btn-primary:hover { background: var(--accent-hover); }
.btn-ghost { background: var(--surface); color: var(--text-secondary); border-color: var(--border); }
.btn-ghost:hover { border-color: var(--border-strong); color: var(--text); }
.btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
```

Keep the legacy `.button` / `.button.secondary` class names working by aliasing them to these
rules (`.button, .btn { ... }`) — `index.html` uses `.button` in three places and in JS-built
markup. Do not rename classes in the JS.

### 2d. Card + stat tiles

The stat strip is the signature element of the reference design and the thing that will make
all three pages read as one product.

```css
.card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--r-lg); box-shadow: var(--shadow-md);
}
.stat-strip {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 16px; margin-bottom: 20px;
}
.stat-tile { padding: 18px 22px; }                    /* compose with .card */
.stat-tile .label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.7px; text-transform: uppercase;
  color: var(--text-muted); margin-bottom: 10px;
}
.stat-tile .value {
  font-family: var(--serif); font-size: 34px; font-weight: 600; line-height: 1;
  letter-spacing: -0.5px; color: var(--text);
}
.stat-tile .unit {
  font-family: var(--sans); font-size: 13px; font-weight: 500;
  color: var(--text-muted); margin-left: 6px;
}
```

### 2e. Dot badges (for creator / category)

```css
.dot-badge {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: var(--r-pill);
  background: var(--surface-2); color: var(--text-secondary);
  font-size: 12px; font-weight: 500; white-space: nowrap;
}
.dot-badge::before {
  content: ''; width: 6px; height: 6px; border-radius: 50%;
  background: var(--dot-color, var(--dot-6)); flex: none;
}
```

Assign a dot color per creator with a small stable hash (see Phase 3b) and set it inline as
`style="--dot-color: var(--dot-3)"`.

### 2f. Inputs, table card, caption bar

```css
.input, .top-filters input, .filter-row input, aside.filters select {
  background: var(--surface); color: var(--text);
  border: 1px solid var(--border); border-radius: var(--r-sm);
  padding: 8px 10px; font-family: var(--sans); font-size: 13px;
}
.input:focus, .top-filters input:focus, .filter-row input:focus {
  outline: 0; border-color: var(--accent); box-shadow: 0 0 0 3px var(--border-focus);
}
.search-wrap { position: relative; }                   /* leading magnifier icon */
.search-wrap .icon {
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  color: var(--text-muted); font-size: 13px; pointer-events: none;
}
.search-wrap input { padding-left: 30px; width: 100%; }

/* Caption bar sitting above the table card: "166 models" ... "Sorted: Intelligence ↓" */
.table-caption {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 13px; color: var(--text-muted);
}
.table-caption .count strong { color: var(--text); font-weight: 600; }
.table-caption .sort-state { color: var(--text-muted); }
.table-caption .sort-state b { color: var(--text); font-weight: 600; }

/* The table lives inside a rounded card that clips its corners. */
.table-card { overflow: hidden; }                      /* compose with .card */
.table-card > .scroll { overflow-x: auto; }
```

---

## Phase 3 — Apply per page

### 3a. `assets/nav.js` — rebuild `renderNav()`, add the toggle

Keep the existing module shape (IIFE, `window.ModelCompassNav`, the `checkStaleness` /
`applyStaleness` logic — **do not touch the staleness code**, it is correct and the comments
explain why it is where it is).

Change `PAGES` to carry a subtitle per page, and rewrite `renderNav()` to emit:

```html
<a class="brand" href="index.html">
  <span class="brand-tile" aria-hidden="true">🧭</span>
  <span class="brand-text">
    <span class="brand-name">Model Compass</span>
    <span class="brand-sub">LLM benchmarks · Artificial Analysis</span>
  </span>
</a>
<nav class="tabs">…one <a class="tab"> per PAGES entry, .active on current…</nav>
<div class="nav-actions">
  <a class="btn btn-ghost" href="https://github.com/…" target="_blank" rel="noopener">GitHub ↗</a>
  <button class="theme-toggle" id="theme-toggle" type="button"
          aria-label="Switch theme" title="Switch theme"></button>
</div>
```

Then add the theme module to the same IIFE:

```js
const THEME_KEY = 'mc-theme';

function systemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
// The stored value wins; absent one, we are following the OS.
function currentTheme() {
  try { return localStorage.getItem(THEME_KEY) || systemTheme(); }
  catch (e) { return systemTheme(); }
}
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀' : '☾';   // show the destination
}
function toggleTheme() {
  const next = currentTheme() === 'dark' ? 'light' : 'dark';
  try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  applyTheme(next);
}
```

Call `applyTheme(currentTheme())` right after `renderNav()`, and wire
`document.getElementById('theme-toggle').addEventListener('click', toggleTheme)`.

Two things to get right:

- The **icon shows the destination, not the state** (moon while light, sun while dark) —
  that is the convention users expect from a 2-state toggle.
- `applyTheme` stamps `data-theme` unconditionally, including on first load when the value
  came from the OS. That is intentional and harmless: it just makes the OS-derived choice
  explicit in the DOM. It does **not** write to `localStorage` — only a click does — so a
  user who never touches the button keeps following their OS across visits.

### 3b. `shortlist.html` — the flagship (do this page first)

This is the page the reference design maps onto most directly. Get it right here, then copy
the patterns to the other two.

1. **Stat strip** — insert a `.stat-strip` of four `.card.stat-tile`s between the header and
   the `.layout` div, populated from the loaded data (all four are one pass over the filtered
   rows, so recompute them inside the existing render function so they track the filters):

   | Label | Value | Source |
   | --- | --- | --- |
   | `MODELS` | count | filtered row count |
   | `MEDIAN BLENDED` | `$0.00` + unit `/M` | median of `blend_3to1_$/M` |
   | `TOP INTELLIGENCE` | max score | max of `intelligence` |
   | `CREATORS` | distinct count | distinct `creator` |

2. **Sidebar** (`aside.filters`) → `.card`: `border-radius: var(--r-lg)`, `padding: 20px`,
   `box-shadow: var(--shadow-md)`. Header line becomes `Filters` + a right-aligned accent
   text button `Reset` (restyle the existing `#reset` button — do not add a second one; move
   it into the `<h2>` row as `.btn-text` styled `color: var(--accent); background: none;
   border: 0`).
3. **Search input** → wrap in `.search-wrap` with a `🔍` `.icon` span.
4. **Table** → wrap `<table id="t">` in `<div class="card table-card"><div class="scroll">…`.
   Then, in the page's `<style>`:
   - `th`: `font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; font-weight: 600;
     color: var(--text-muted); background: var(--surface); padding: 14px 12px;` with
     `border-bottom: 1px solid var(--border)` (drop the 2px).
   - `td`: `padding: 14px 12px;` — the reference's tall, airy rows are most of its character.
   - Row hover: replace the blue `rgba(74,144,226,0.04)` with `var(--row-hover)`, and add the
     3px accent left-bar the reference shows on the active row:
     `tr:hover td:first-child { box-shadow: inset 3px 0 0 var(--accent); }`
   - **Two-line name cell:** the reference stacks a bold primary over a muted secondary. Change
     the name cell renderer to emit
     `<div class="cell-title">{name}</div><div class="cell-sub">{slug}</div>`, with
     `.cell-title { font-family: var(--sans); font-weight: 600; color: var(--text); }` and
     `.cell-sub { font-family: var(--mono); font-size: 11px; color: var(--text-muted); margin-top: 2px; }`.
     Remove `white-space: nowrap` from that cell only.
   - **Creator cell** → `.dot-badge`. Pick the dot with a stable index so a creator keeps its
     color across renders:
     ```js
     const DOTS = ['--dot-1','--dot-2','--dot-3','--dot-4','--dot-5','--dot-6'];
     const dotFor = (s) => DOTS[[...s].reduce((h,c) => (h*31 + c.charCodeAt(0)) | 0, 7).toString().split('').reduce((a,b)=>a+ +b,0) % DOTS.length];
     ```
     (Any stable hash is fine; the only requirement is determinism.)
5. **Caption bar** — add `.table-caption` above the table card: left `<span class="count">
   <strong>N</strong> models</span>` (retire the old `#count` span, or reuse its id inside
   the new markup so the existing JS keeps writing to it), right
   `<span class="sort-state">Sorted: <b>{column}</b> ↓</span>` updated by the existing sort
   handler.
6. Sticky columns (`.cb-col`, `.rnk`, `.name-col`) — these use `background: var(--surface)`
   on the cell to mask the scrolling content beneath. That still works; just verify after the
   padding change that the `left:` offsets (`0`, `30px`, `66px`) still line up. **They will
   not** — the wider padding widens the checkbox and rank columns. Recompute: measure the
   rendered widths in the browser and update the three `left:` values, or better, drop the
   hardcoded offsets in favor of the widths you set explicitly on `th.cb-col`/`th.rnk`.
7. Sticky `th { top: 0 }` must become `top: var(--nav-h)` — the nav is sticky too, and at
   60px tall it will otherwise overlap the header row.

### 3c. `models.html`

Same table treatment as 3b (steps 4, 6, 7), same sidebar card treatment (step 2), same search
wrap (step 3). No stat strip — this page is a dense 27-column reference table and the tiles
would just push the data below the fold. Two page-specific fixes:

- `th, td { border: 1px solid var(--border) }` gives this table a full grid. Reduce to
  `border-bottom` only, to match the reference's horizontal-rules-only look.
- `.free td { background: var(--green-bg) }` (the OpenRouter-availability highlight) survives
  as-is; it already uses a token.

### 3d. `index.html`

The centered-column picker keeps its shape. Apply the card language:

- `.container { max-width: 1100px }` and add a **stat strip** below the header, mirroring
  shortlist's (Models tracked / Creators / Median blended / Last scrape date). This is what
  ties the landing page to the rest of the site visually.
- `.input-panel` and `.results` → `.card` (radius `var(--r-lg)`, `box-shadow: var(--shadow-md)`,
  padding 24px).
- `.button` → the Phase 2c pill styles. `.example-chip` → `.dot-badge`-adjacent pill (keep it
  a chip, but move to `--r-pill` and the surface-2 fill).
- `.badge.privacy` and `.badge.frontier` currently hardcode `#e0e7ff/#3730a3` and
  `#fce7f3/#9d174d`. Swap to `var(--blue-bg)/var(--blue-dark)` and `var(--pink-bg)/var(--pink-dark)`
  (added in Phase 1).

---

## Phase 4 — Hardcoded-color eradication (blocks dark mode)

These are the values that will visibly break in dark mode. Hunt them down with
`grep -nE '#[0-9a-fA-F]{3,6}|rgba?\(' index.html shortlist.html models.html` and fix every
hit that is not already inside a `var()` fallback.

| File | What | Fix |
| --- | --- | --- |
| `shortlist.html` | `.creator-pill.outside` / `.quick-btn.outside-h` → `#a8492f` | `var(--red-dark)` |
| `shortlist.html` | `.creator-pill.inside` / `.quick-btn.inside-h` → `#4c6b41` | `var(--green-dark)` |
| `shortlist.html` | `color:#fff` on every `.active` / `#cmp-go` fill | `var(--accent-fg)` |
| `shortlist.html` | `#reset:hover { background:#e6e3d7 }` | `var(--surface-2)` |
| `shortlist.html` | `tr:hover td` → `rgba(74,144,226,0.04)` (a stray **blue**, off-palette even in light mode) | `var(--row-hover)` |
| `shortlist.html` | `#tip { background:#191919; color:#fff }` | `var(--tooltip-bg)` / `var(--tooltip-fg)` |
| `shortlist.html` | `aside.filters` shadow `rgba(0,0,0,0.04)` | `var(--shadow-md)` |
| `index.html` | `.badge.privacy`, `.badge.frontier` | blue/pink tokens |
| `index.html` | `.button { color:#fff }`, `.toast { color:#fff }` | `var(--accent-fg)`, `var(--bg)` |
| `index.html`, `shortlist.html` | inline `style="background:var(--yellow-bg);…"` on `#staleness-banner` | delete the inline style; use `class="staleness-banner"`, which already exists in `style.css` and is what `models.html` correctly does |

Also: any `<input>`/`<select>`/`<textarea>` without an explicit `background: var(--surface);
color: var(--text)` will render with the UA's default light chrome inside a dark page.
`shortlist.html`'s `.top-filters input` and `.filter-row input` are both missing the `color`.
The `color-scheme` declaration added in Phase 1 fixes the *native* widgets (scrollbars,
checkboxes, date pickers), but not elements you have already given a custom `background`.

---

## Phase 5 — Verify

No test suite exists, so verification is manual and visual. Run `python3 -m http.server`, then
for **each of the three pages**:

1. **Toggle works.** Click the toggle → theme flips; hard-reload → the choice persists;
   navigate to another page → the choice carries (this is what proves the Phase 1c inline
   script is placed correctly).
2. **No flash.** With dark forced, hard-reload with cache disabled. Any white flash means the
   inline script is below the stylesheet links or was put in `nav.js`.
3. **Nothing is invisible in dark mode.** Read every surface: filter pills (active *and*
   inactive), preset buttons, the compare bar, the tooltip, the staleness banner, the heat-map
   cells, the sticky columns' mask, disabled/empty table cells. This is where the Phase 4
   misses will show up.
4. **OS default still respected.** In a fresh profile (or after `localStorage.removeItem('mc-theme')`
   in the console + reload), the page follows the OS setting.
5. **Responsive.** At 480px and 800px: the sidebar collapses above the table (that behavior
   already exists — do not break it), the stat strip reflows to 2 columns then 1, the nav's
   segmented control stays reachable.
6. **Contrast.** Spot-check accent-on-surface and `--text-muted`-on-surface in *both* themes
   against WCAG AA (4.5:1 body, 3:1 for large text). `--text-muted` on `--surface` is the one
   most likely to fail — if it does, darken it in light / lighten it in dark rather than
   growing the font.

Suggested commit sequence, so a bad step is easy to bisect:

```
1. tokens: restructure theme vars for manual light/dark + add shape/shadow tokens
2. nav: taller bar, brand tile, segmented tabs, theme toggle
3. css: shared card / stat-tile / dot-badge / button / table-card components
4. shortlist: apply card + stat-strip + table redesign
5. models: apply card + table redesign
6. picker: apply card + stat-strip redesign
7. fix: replace hardcoded colors that break dark mode
```

---

## Out of scope

Do not change: the scraper (`scripts/`), `data/`, the refresh workflow, the picker's scoring
or classifier logic, the staleness-check logic in `nav.js`, or any DOM `id` that JS reads
(`#q`, `#t`, `#count`, `#reset`, `#cmp-go`, `#staleness-banner`, …). This is a presentation-layer
change only — if you find yourself editing a `fetch()` or a scoring function, stop.
