# Lunar Tools Prototypes — Gallery Site Design

**Date:** 2026-03-26
**Status:** Rev 2 (post QA — Codex + Gemini)
**Author:** Adrian + Claude

---

## 1. Overview

A gallery-grade GitHub Pages site for the Lunar Tools Art Prototypes collection. The site presents 29 interactive art installation concepts as a curated portfolio — part artist's portfolio, part technical showcase, part invitation to collaborate.

Reuses the Afterwords design system (dark theme, Instrument Serif + Plus Jakarta Sans, canvas animations, scroll reveals) but adapted for a gallery/exhibition context rather than a developer tool. Quieter chrome, more negative space, fewer badges — the installations wake up when you look at them.

**URL:** `https://adrianwedd.github.io/lunar_tools_prototypes/`

---

## 2. Artistic Direction

The Afterwords site sells a tool. This site presents a body of work.

- **Gallery, not docs** — each prototype is a piece in a collection, not a feature in a product
- **Evocative, not explanatory** — lead with the experience, not the technology
- **Atmospheric** — dark, intimate, like walking through an exhibition at night
- **The technology serves the art** — MLX, voice cloning, emotion detection are capabilities, not selling points
- **The hover state is the key interaction** — cards "wake up" when you look at them: accent glow, text brightens from dim to vivid

The accent colour shifts from Afterwords' warm orange (`#e8976b`) to a muted violet/indigo (`#9b8ec4`) — otherworldly, introspective, uncanny.

### Artist's Statement

Near the hero, a brief manifesto in high-serif italic. Sets the tone before the collection:

> *We build tools that look back at us. These prototypes sit at the edge where AI stops being a tool and starts being a mirror — observing, reflecting, sometimes revealing things we didn't know we were showing. They are sketches of encounters, not products.*

---

## 3. Site Structure

Single-page site in `docs/index.html`, following the Afterwords pattern.

### Hero Section

Full-viewport hero with **mirror shatter** canvas animation — geometric fragments that slowly drift and reassemble based on scroll position. Creates a "broken reflection" metaphor that bridges directly to the Mirror of Truth / Audio Mirror concepts. Distinct from Afterwords' waveform identity.

**Content:**
- Eyebrow: `LUNAR TOOLS ART PROTOTYPES`
- H1: *"Installations that look back"* (serif, with "look back" in accent violet)
- Artist's Statement (italic, secondary text)
- CTA: "Explore the collection" (scroll) + "View on GitHub" (ghost button)
- Stats: `29 installations` / `Apple Silicon` / `Voice cloning` / `Emotion detection`

### Featured Experiences Section

The Audio Mirror and Mirror of Truth get distinct treatment — not just wide cards, but a separate visual section with a subtle background gradient shift to signal hierarchy.

Each featured piece gets:
- Title (serif, large) + one-line concept
- 3-4 lines describing the experience (what happens to the viewer, not the technology)
- Small tech footnote (muted, not badges)
- More breathing room than grid cards — `padding: 3rem`, generous margins

### Gallery Grid

The remaining 27 prototypes in a responsive grid. Each card:

- **Name** (serif display font, dim until hover)
- **Tagline** (one line — what the viewer experiences)
- **Category tag** — evocative name, not functional (see Section 5)
- Hover: text brightens, accent glow on left border, `translateY(-2px)`, the piece "wakes up"
- **No technology badges on cards** — keep it clean. Tech is visible in the compact Process section below.

**Filtering:**
- Category buttons above the grid, styled as pill toggles
- `aria-pressed` state for accessibility
- Click to filter with CSS transitions for show/hide
- `location.hash` for filter state (shareable links, back button)
- "All" as default, visible active state, result count on change
- **Sticky filter bar on mobile** to prevent doomscroll
- Empty state: "No installations in this collection" (shouldn't happen, but guard against it)

### Process Section

One compact section replacing the separate Architecture / Technology Stack / Setup sections. Gallery first, tech second.

- **System diagram** — the topology (Mac + Afterwords + LLM + Pi), rendered as a clean flow
- **Quick start** code block with copy-to-clipboard
- **Stack list** — inline, not cards: MLX, Afterwords, OpenCV, librosa, Claude/Ollama

### Footer

Minimal: GitHub link / "Built with Lunar Tools" / License

---

## 4. Design System

### Colours

```css
:root {
  --bg: #0a0a10;           /* deep ink, not pure black */
  --bg-elevated: #12121c;
  --bg-card: #181824;
  --bg-card-hover: #1e1e2e;
  --bg-featured: linear-gradient(180deg, #0f0f1a 0%, #0a0a10 100%);
  --text: #e4e4f0;
  --text-secondary: #9494a8;
  --text-dim: #64647a;
  --accent: #9b8ec4;        /* muted violet */
  --accent-glow: rgba(155, 142, 196, 0.15);
  --accent-bright: #b0a4d4;
  --border: rgba(255, 255, 255, 0.06);
  --border-hover: rgba(155, 142, 196, 0.25);
}
```

### Typography

- Display: `'Instrument Serif', Georgia, serif`
- Body: `'Plus Jakarta Sans', system-ui, sans-serif`
- Mono: `'JetBrains Mono', 'SF Mono', monospace`
- Google Fonts with preconnect + `display=swap`

### Layout

- Max width: `900px`
- Gallery grid: `repeat(auto-fill, minmax(280px, 1fr))`
- Featured cards: full-width with `padding: 3rem`
- Section spacing: `margin-top: 10vh` between major sections (airy, gallery feel)

### Animations

- Hero: staggered fade-in (eyebrow → title → statement → CTA → stats)
- Scroll reveals: IntersectionObserver with `.reveal` class, section-level stagger (not per-card for large grids)
- Hover: `translateY(-2px)` + border-color + text brightening, 0.3s ease-out-expo
- Canvas: `requestAnimationFrame` loop, pauses when off-screen, respects `prefers-reduced-motion`
- Canvas DPR: `Math.min(devicePixelRatio, 2)` for retina

---

## 5. Prototype Inventory & Categories

### Inventory (29 installations, excluding __init__.py and example_base_usage.py)

Categories use evocative names for the gallery, with functional tags as secondary metadata for developers.

| Gallery Category | Internal tag | Description | Approx count |
|-----------------|-------------|-------------|-------------|
| **Echoes** | `voice` | Voice, speech, sonic interaction | 7 |
| **Reflections** | `interactive` | Real-time observation, audience participation | 8 |
| **Visions** | `visual` | Image generation, style transfer, rendering | 8 |
| **Whispers** | `generative` | Procedural/algorithmic, data-driven, ambient | 6 |

Four categories, not six — cleaner, less overlap. Each prototype gets exactly one.

### Prototype Data Schema

```json
{
  "id": "audio-mirror",
  "name": "Audio Mirror",
  "tagline": "An oracle that speaks in your own voice",
  "category": "echoes",
  "tech": ["MLX", "Afterwords", "Whisper"],
  "featured": true
}
```

Taglines will be written for all 29 prototypes based on their source files. Each tagline describes what the viewer experiences, not what the code does.

---

## 6. Accessibility

| Requirement | Implementation |
|-------------|---------------|
| Semantic HTML | `<main>`, `<article>`, `<section>`, `<h1>`-`<h3>` hierarchy |
| Filter buttons | `<button>` with `aria-pressed`, keyboard navigable |
| Focus order | Logical tab order follows visual layout. Focus visible: `outline: 2px solid var(--accent)` |
| Hero canvas | `role="presentation"`, `aria-hidden="true"` (decorative) |
| Reduced motion | `@media (prefers-reduced-motion: reduce)` disables all animations, stagger, canvas loop. Reveal elements start visible. |
| Color contrast | Text/background ratios meet WCAG AA (verified for `--text` on `--bg` and `--accent` on `--bg-card`) |
| Screen readers | Filter state announced, result count updated via `aria-live="polite"` region |

---

## 7. SEO & Social Sharing

### Meta Tags (complete set)

```html
<title>Lunar Tools Art Prototypes — Interactive AI Installations</title>
<meta name="description" content="29 interactive art installations exploring the edge where AI becomes a mirror. Voice cloning, emotion detection, generative visuals. Built on Apple Silicon with MLX.">
<meta property="og:title" content="Lunar Tools Art Prototypes">
<meta property="og:description" content="Interactive installations where AI observes, reflects, and reveals.">
<meta property="og:type" content="website">
<meta property="og:url" content="https://adrianwedd.github.io/lunar_tools_prototypes/">
<meta property="og:image" content="https://adrianwedd.github.io/lunar_tools_prototypes/og-image.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Lunar Tools Art Prototypes — 29 interactive AI art installations">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Lunar Tools Art Prototypes">
<meta name="twitter:description" content="Interactive installations where AI observes, reflects, and reveals.">
<meta name="twitter:image" content="https://adrianwedd.github.io/lunar_tools_prototypes/og-image.png">
<link rel="canonical" href="https://adrianwedd.github.io/lunar_tools_prototypes/">
```

### OG Image

- 1200x630, dark background with mirror-shatter fragments, title overlaid
- Generated via `docs/og-image.html` (same pattern as Afterwords)

---

## 8. Technical Implementation

### Single HTML file

Everything in `docs/index.html`. No build step, no bundler, no framework.

- ~50-60KB estimated
- No external JS libraries
- Google Fonts only external dependency
- All CSS inline in `<style>`, all JS inline in `<script>`

### Filtering JS

```javascript
// Category filter with hash state
const filters = document.querySelectorAll('.filter-btn');
const cards = document.querySelectorAll('.gallery-card');
const countEl = document.querySelector('.result-count');

function filterBy(category) {
  cards.forEach(card => {
    const show = category === 'all' || card.dataset.category === category;
    card.style.display = show ? '' : 'none';
    card.classList.toggle('hidden', !show);
  });
  filters.forEach(btn => btn.setAttribute('aria-pressed', btn.dataset.filter === category));
  location.hash = category === 'all' ? '' : category;
  countEl.textContent = `${document.querySelectorAll('.gallery-card:not(.hidden)').length} installations`;
}

// Init from hash
const initial = location.hash.slice(1) || 'all';
filterBy(initial);
```

### Responsive Breakpoints

```css
/* Desktop: 3 columns */
.gallery-grid { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }

/* Tablet */
@media (max-width: 768px) {
  .gallery-grid { grid-template-columns: 1fr 1fr; }
  .filter-bar { position: sticky; top: 0; z-index: 10; } /* sticky on mobile */
}

/* Mobile */
@media (max-width: 480px) {
  .gallery-grid { grid-template-columns: 1fr; }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
  .reveal { opacity: 1; transform: none; }
  #heroCanvas { display: none; }
}
```

### Performance

- Canvas animation pauses when off-screen (IntersectionObserver)
- No images (everything is CSS/canvas/text)
- Font display: `swap`
- Section-level stagger for reveal (not per-card, avoids 29 timers)

---

## 9. What's NOT in scope

- Individual detail pages (single-page only)
- Live demos (prototypes need hardware)
- Blog/news/analytics/contact form
- Audio samples (unlike Afterwords — these are visual/interactive installations)

---

## 10. Success Criteria

1. Looks like a gallery, not a README
2. Every prototype has a compelling one-line tagline
3. Responsive and smooth on mobile — filter bar is sticky, no doomscroll
4. Loads in < 2s on 3G
5. OG image renders well on Twitter/LinkedIn/Slack
6. A developer understands the project within 10 seconds
7. An artist/curator can browse the collection and understand the artistic intent
8. WCAG AA compliant — keyboard navigable, screen reader friendly, reduced motion respected
9. Hero canvas is visually distinct from Afterwords' waveforms
