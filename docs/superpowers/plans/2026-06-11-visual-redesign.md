# Visual Redesign Spec: "Terminal Reader" → "Reading Room"

**Date:** 2026-06-11
**Status:** Spec — awaiting implementation
**Target:** `web/static/style.css` (CSS-only, one template tweak)
**Constraint:** No new dependencies, min-width 1024px, htmx 1.x compatible

---

## 0. Design Direction

**From:** A flat, utilitarian dark terminal — uniform cards, no depth, no warmth.
**To:** A "Reading Room" — intentional, curated, pleasant to spend time in. Think Matter, Readwise Reader, or Linear's clean density.

**Core moves:**
1. Three-layer background depth (deep → surface → elevated)
2. Reading-optimized typography (18px body, generous line-height on reader)
3. Accent variations to signal content type (blue=link, purple=AI, gold=highlight)
4. Subtle hover transitions everywhere (0.15-0.2s)
5. Home page: grid of cluster cards on wider screens
6. Reader: larger title, wider line-height, distinct analysis sections
7. Admin: dashboard stat cards with better visual weight
8. Empty states: emoji + softer treatment

---

## A. Color System

### A.1 Updated CSS Variables (replace the `:root` block)

```css
:root {
    /* ── Background layers ── */
    --bg-deep:      #0a0e14;   /* page background (deeper shadow) */
    --bg-base:      #0d1117;   /* unchanged — compatibility anchor */
    --bg-surface:   #161b22;   /* cards, sections */
    --bg-elevated:  #1c2333;   /* hover states, active cards, promos */
    --bg-overlay:   #212936;   /* tooltips, dropdowns, modals (future) */

    /* ── Borders ── */
    --border:        #30363d;   /* default border */
    --border-light:  #3a4350;   /* subtle inner dividers */
    --border-accent: #58a6ff;   /* highlighted borders */

    /* ── Text ── */
    --text:          #c9d1d9;   /* body text */
    --text-muted:    #8b949e;   /* secondary text, captions */
    --text-dim:      #6e7681;   /* tertiary, placeholders */

    /* ── Accent palette ── */
    --accent:            #58a6ff;   /* primary: links, active states */
    --accent-hover:      #79c0ff;   /* hover variant */
    --accent-soft:       rgba(88, 166, 255, 0.12);  /* subtle bg tint */
    --accent-secondary:  #a371f7;   /* purple: AI-generated, concept tags */
    --accent-warm:       #d29922;   /* gold: highlights, stars, priority */

    /* ── Semantic colors ── */
    --success:  #3fb950;   /* green — brighter than old #2ea043 */
    --warning:  #d29922;   /* gold — replacing #ff9800 */
    --danger:   #f85149;   /* red — unchanged */
    --info:     #58a6ff;   /* blue — same as accent */

    /* ── Lifecycle badges ── */
    --lifecycle-new:       #58a6ff;
    --lifecycle-rising:    #3fb950;
    --lifecycle-stable:    #8b949e;
    --lifecycle-declining: #d29922;

    /* ── Buttons ── */
    --btn-bg:         #21262d;
    --btn-hover-bg:   #30363d;
    --btn-primary-bg: #1f6feb;
    --btn-primary-hover: #388bfd;

    /* ── Typography scale ── */
    --text-xs:   0.75rem;    /* 12px */
    --text-sm:   0.875rem;   /* 14px */
    --text-base: 1rem;       /* 16px */
    --text-md:   1.125rem;   /* 18px */
    --text-lg:   1.25rem;    /* 20px */
    --text-xl:   1.5rem;     /* 24px */
    --text-2xl:  2rem;       /* 32px */

    /* ── Typography weights ── */
    --weight-normal:   400;
    --weight-medium:   500;
    --weight-semibold: 600;
    --weight-bold:     700;

    /* ── Line heights ── */
    --leading-tight:   1.25;   /* headings */
    --leading-normal:  1.5;    /* compact body, lists */
    --leading-relaxed: 1.7;    /* default body */
    --leading-loose:   1.85;   /* reader/article body */

    /* ── Spacing scale ── */
    --space-1:  4px;
    --space-2:  8px;
    --space-3:  12px;
    --space-4:  16px;
    --space-5:  20px;
    --space-6:  24px;
    --space-8:  32px;
    --space-10: 40px;
    --space-12: 48px;

    /* ── Border radius ── */
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    --radius-xl: 12px;

    /* ── Transitions ── */
    --transition-fast:   0.15s ease;
    --transition-normal: 0.2s ease;
    --transition-slow:   0.3s ease;

    /* ── Shadows ── */
    --shadow-sm:  0 1px 3px rgba(0,0,0,0.3);
    --shadow-md:  0 2px 12px rgba(0,0,0,0.25);
    --shadow-lg:  0 4px 24px rgba(0,0,0,0.35);

    /* ── Gradients ── */
    --gradient-surface:  linear-gradient(135deg, #161b22 0%, #1a202c 100%);
    --gradient-elevated: linear-gradient(135deg, #1c2333 0%, #212c3d 100%);
    --gradient-accent:   linear-gradient(135deg, #1f6feb 0%, #58a6ff 100%);
}
```

### A.2 Contrast Reference

| Element | FG | BG | Ratio | WCAG |
|---------|----|----|-------|------|
| Body text | `#c9d1d9` | `#0a0e14` | ~12:1 | AAA |
| Muted text | `#8b949e` | `#0a0e14` | ~6:1 | AA |
| Dim text | `#6e7681` | `#0a0e14` | ~4.5:1 | AA |
| Accent link | `#58a6ff` | `#0a0e14` | ~4.8:1 | AA |
| Accent on surface | `#58a6ff` | `#161b22` | ~4.3:1 | AA |
| Success green | `#3fb950` | `#161b22` | ~4.8:1 | AA |
| Danger red | `#f85149` | `#161b22` | ~4.5:1 | AA |
| Warning gold | `#d29922` | `#161b22` | ~3.5:1 | < AA (use on bg only) |

**Rule:** Warning `#d29922` must only appear on `--bg-elevated` or as a badge background, never as bare text on `--bg-surface`.

---

## B. Typography

### B.1 Global Body Reset

```css
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: var(--bg-deep);
    color: var(--text);
    min-width: 1024px;
    line-height: var(--leading-relaxed);   /* was 1.6, now 1.7 */
    font-size: var(--text-base);            /* was inherited, explicitly 16px */
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
```

### B.2 Type Scale Application (updated selectors)

```css
/* Page heading */
h1 {
    font-size: var(--text-xl);        /* 24px, was 1.5rem */
    font-weight: var(--weight-bold);  /* 700 */
    line-height: var(--leading-tight);
    margin-bottom: var(--space-4);
    letter-spacing: -0.01em;          /* subtle tightening */
}

/* Section heading */
h2 {
    font-size: var(--text-lg);         /* 20px */
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
    margin: var(--space-8) 0 var(--space-3);
    color: var(--text);
}

h3 {
    font-size: var(--text-md);         /* 18px */
    font-weight: var(--weight-semibold);
    line-height: var(--leading-tight);
    margin-bottom: var(--space-3);
}

/* Cluster label (card title) */
.cluster-label {
    font-size: var(--text-lg);          /* 20px, was 1.1rem */
    color: var(--accent);
    margin-bottom: var(--space-3);      /* was 8px */
    font-weight: var(--weight-semibold);
}

/* Article title in reader */
.reader-header + h1,                    /* targets article title */
h1.article-title {
    font-size: var(--text-2xl);         /* 32px */
    font-weight: var(--weight-bold);
    line-height: var(--leading-tight);
    margin: var(--space-6) 0 var(--space-3);
    color: var(--text);
}

/* Reading body */
.article-body {
    font-size: var(--text-md);          /* 18px, was 1rem */
    line-height: var(--leading-loose);  /* 1.85, was 1.8 */
    margin: var(--space-6) 0;
    color: var(--text);
}

/* Meta / captions */
.article-meta {
    color: var(--text-muted);
    font-size: var(--text-sm);           /* 14px, was 0.85rem */
    white-space: nowrap;
    margin-left: var(--space-3);
}

.article-count {
    color: var(--text-muted);
    font-size: var(--text-xs);           /* 12px */
    font-weight: var(--weight-normal);
}

/* Badges */
.lifecycle-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--radius-xl);     /* 12px */
    font-size: var(--text-xs);           /* 12px */
    font-weight: var(--weight-medium);
    color: #fff;
}
```

---

## C. Spacing & Layout

### C.1 Container Refinements

Add a `body` class per page (ONE template change — see Section G).

```css
/* Reading-optimized pages */
body.reader .container,
body.concepts .container,
body.search .container,
body.review .container {
    max-width: 780px;           /* narrower for reading focus */
    margin: 0 auto;
    padding: var(--space-8) var(--space-8);
}

/* Data-dense / browsing pages */
body.home .container,
body.admin .container,
body.sources .container {
    max-width: 1120px;          /* wider for tables, grids */
    margin: 0 auto;
    padding: var(--space-6) var(--space-8);
}

/* Default fallback */
.container {
    max-width: 960px;
    margin: 0 auto;
    padding: var(--space-6) var(--space-8);  /* was 24px 32px */
}
```

### C.2 Header

```css
.app-header {
    padding: var(--space-3) var(--space-8);   /* 12px 32px */
    border-bottom: 1px solid var(--border);
    background: var(--bg-base);              /* NEW: distinct from page bg */
    backdrop-filter: blur(8px);              /* subtle glass if content scrolls */
}

.app-title {
    font-size: var(--text-md);               /* 18px, was 1.1rem */
    font-weight: var(--weight-bold);
    color: var(--text);
    text-decoration: none;
    letter-spacing: -0.01em;
    transition: color var(--transition-fast);
}
.app-title:hover {
    color: var(--accent);
    text-decoration: none;
}
```

### C.3 Cluster Cards (Home Page)

```css
.cluster-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-5) var(--space-6);   /* 20px 24px, was 16px 20px */
    margin-bottom: var(--space-4);             /* 16px, was 12px */
    transition: border-color var(--transition-normal),
                box-shadow var(--transition-normal);
}
.cluster-card:hover {
    border-color: var(--border-light);
    box-shadow: var(--shadow-md);
}

/* Article items inside cards */
.article-item {
    padding: var(--space-2) 0;                /* 8px, was 6px */
    border-bottom: 1px solid var(--border-light);
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    transition: background var(--transition-fast);
}
.article-item:hover {
    background: var(--bg-elevated);
    margin: 0 calc(-1 * var(--space-6));      /* expand to card edge */
    padding-left: var(--space-6);
    padding-right: var(--space-6);
    border-radius: var(--radius-sm);
}
.article-item:last-child {
    border-bottom: none;
}

/* Article link inside items */
.article-link {
    color: var(--text);                        /* was accent blue */
    text-decoration: none;
    font-weight: var(--weight-medium);
    transition: color var(--transition-fast);
}
.article-link:hover {
    color: var(--accent);
    text-decoration: none;
}
```

### C.4 Home Page — Responsive Grid

```css
/* Single column by default */
.clusters {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-4);
}

/* Two columns on wider viewports */
@media (min-width: 1200px) {
    .clusters {
        grid-template-columns: 1fr 1fr;
    }
    /* Span the first (most important) cluster full width */
    .cluster-card:first-child {
        grid-column: 1 / -1;
    }
}
```

### C.5 Digest Summary

```css
.digest-summary {
    color: var(--text-muted);
    margin-bottom: var(--space-6);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--border);
    font-size: var(--text-sm);
    display: flex;
    align-items: center;
    gap: var(--space-2);
}
```

---

## D. Component Styles

### D.1 Buttons

```css
.btn {
    display: inline-flex;                     /* was inline-block */
    align-items: center;
    gap: var(--space-1);
    background: var(--btn-bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: var(--space-2) var(--space-3);   /* 8px 12px, was 6px 14px */
    border-radius: var(--radius-md);
    cursor: pointer;
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    text-decoration: none;
    transition: all var(--transition-fast);
}
.btn:hover {
    border-color: var(--accent);
    color: var(--accent-hover);
    background: var(--btn-hover-bg);
}

.btn-primary {
    background: var(--btn-primary-bg);
    border-color: var(--btn-primary-bg);
    color: #fff;
}
.btn-primary:hover {
    background: var(--btn-primary-hover);
    border-color: var(--btn-primary-hover);
    color: #fff;
}

.btn-danger {
    color: var(--danger);
}
.btn-danger:hover {
    border-color: var(--danger);
    background: rgba(248, 81, 73, 0.1);
}

.btn-sm {
    padding: 2px 8px;
    font-size: var(--text-xs);
}

.btn-secondary {
    margin-left: var(--space-2);
}

/* Positive / negative feedback buttons */
.btn-positive {
    background: var(--success);
    color: #fff;
    border: none;
    cursor: pointer;
}
.btn-positive:hover {
    opacity: 0.9;
    background: var(--success);
}

.btn-negative {
    background: var(--danger);
    color: #fff;
    border: none;
    cursor: pointer;
}
.btn-negative:hover {
    opacity: 0.9;
    background: var(--danger);
}

.btn-feedback-sm {
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md);
}
.btn-feedback {
    padding: var(--space-2) var(--space-4);
    border-radius: var(--radius-md);
    font-size: var(--text-sm);
}
```

### D.2 Forms & Inputs

```css
.search-input {
    width: 100%;
    padding: var(--space-3) var(--space-4);
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    color: var(--text);
    font-size: var(--text-base);
    margin-bottom: var(--space-3);
    transition: border-color var(--transition-fast),
                box-shadow var(--transition-fast);
}
.search-input:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}
.search-input::placeholder {
    color: var(--text-dim);
}

.add-source-form input,
.add-source-form select {
    display: block;
    width: 100%;
    margin-bottom: var(--space-2);
    padding: var(--space-2) var(--space-3);
    background: var(--bg-base);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
    transition: border-color var(--transition-fast);
}
.add-source-form input:focus,
.add-source-form select:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.15);
}
.add-source-form label {
    display: block;
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    margin-bottom: var(--space-1);
    color: var(--text);
}
```

### D.3 Tables

```css
.sources-table {
    width: 100%;
    border-collapse: collapse;
    margin: var(--space-4) 0;
}
.sources-table th,
.sources-table td {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--border);
    text-align: left;
}
.sources-table th {
    color: var(--text-muted);
    font-weight: var(--weight-semibold);
    font-size: var(--text-xs);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding-top: var(--space-3);
    padding-bottom: var(--space-3);
}
/* Zebra striping */
.sources-table tbody tr:nth-child(even) {
    background: rgba(255,255,255,0.015);
}
.sources-table tbody tr:hover {
    background: var(--bg-elevated);
    transition: background var(--transition-fast);
}

.candidates-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: var(--space-4);
}
.candidates-table thead tr {
    border-bottom: 2px solid var(--border);
}
.candidates-table th,
.candidates-table td {
    padding: var(--space-3);
    text-align: left;
}
.candidates-table tbody tr {
    border-bottom: 1px solid var(--border-light);
    transition: background var(--transition-fast);
}
.candidates-table tbody tr:hover {
    background: var(--bg-elevated);
}
```

### D.4 Badges & Labels

```css
.lifecycle-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: var(--radius-xl);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    color: #fff;
}

/* Color-coded cluster badges use accent variations */
.cluster-badge {
    background: var(--accent-secondary);       /* purple instead of hardcoded #9c27b0 */
    color: #fff;
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
    padding: 1px 6px;
    border-radius: var(--radius-sm);
}

/* Concept badge */
.concept-badge {
    background: var(--accent-secondary);       /* was #1a237e */
    color: #fff;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    margin: 2px;
    font-size: var(--text-xs);
    display: inline-block;
}

/* Priority dot */
.priority-dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--priority-color, var(--text-muted));
    margin-right: var(--space-1);
}

/* Recommendation reason */
.rec-card-reason {
    color: var(--accent-secondary);            /* purple, was #9c27b0 */
    font-size: var(--text-xs);
    margin-top: 2px;
}
```

### D.5 Analysis Sections (Reader)

```css
.analysis-section {
    margin: var(--space-6) 0;
    padding: var(--space-4) var(--space-5);
    background: var(--bg-surface);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent-secondary);  /* purple left accent */
}
.analysis-section h3 {
    margin-bottom: var(--space-3);
    color: var(--accent);
    font-size: var(--text-md);
}

/* Details/summary toggle */
.analysis-toggle {
    cursor: pointer;
    color: var(--accent);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    margin-bottom: var(--space-3);
    transition: color var(--transition-fast);
}
.analysis-toggle:hover {
    color: var(--accent-hover);
}
.analysis-toggle::-webkit-details-marker,
.analysis-toggle::marker {
    display: none;
    content: "";
}
.analysis-toggle-body {
    margin-top: var(--space-3);
}
```

### D.6 Feedback Bar

```css
.feedback-bar {
    margin: var(--space-8) 0;
    padding: var(--space-4) var(--space-5);
    background: var(--gradient-surface);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
    display: flex;
    gap: var(--space-3);
    align-items: center;
    flex-wrap: wrap;
}
.feedback-bar-label {
    font-weight: var(--weight-medium);
    font-size: var(--text-sm);
    color: var(--text-muted);
}
```

### D.7 Navigation

```css
.bottom-nav {
    margin-top: var(--space-12);
    padding: var(--space-4) 0;
    border-top: 1px solid var(--border);
    display: flex;
    gap: var(--space-8);                      /* was 24px */
    justify-content: center;
    font-size: var(--text-sm);
}
.bottom-nav a {
    color: var(--text-muted);
    text-decoration: none;
    font-weight: var(--weight-medium);
    padding: var(--space-1) 0;
    border-bottom: 2px solid transparent;
    transition: color var(--transition-fast),
                border-color var(--transition-fast);
}
.bottom-nav a:hover {
    color: var(--text);
    border-bottom-color: var(--border-light);
}
/* Highlight current section (requires server-side active class or JS) */
.bottom-nav a.active,
.bottom-nav a[aria-current="page"] {
    color: var(--accent);
    border-bottom-color: var(--accent);
}
```

### D.8 Back Link

```css
.back-link {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    margin-bottom: var(--space-4);
    font-size: var(--text-sm);
    color: var(--text-muted);
    transition: color var(--transition-fast);
}
.back-link:hover {
    color: var(--text);
    text-decoration: none;
}
```

### D.9 Concept Lookup

```css
.concept-lookup {
    margin: var(--space-4) 0;
    display: flex;
    align-items: center;
    gap: var(--space-2);
}
.concept-lookup .hint {
    color: var(--text-muted);
    font-size: var(--text-sm);
}
.concept-lookup-result {
    margin-left: var(--space-2);
    font-size: var(--text-sm);
}
```

### D.10 Recommendation Cards

```css
.rec-section {
    margin: var(--space-6) 0;
}
.rec-title {
    margin-bottom: var(--space-2);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    color: var(--text-muted);
}
.rec-card {
    padding: var(--space-2) var(--space-3);
    margin: var(--space-1) 0;
    background: var(--bg-surface);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--accent-warm);   /* gold accent */
}
.rec-card-link {
    font-weight: var(--weight-medium);
}
.rec-card-source {
    color: var(--text-muted);
    font-size: var(--text-xs);
    margin-left: var(--space-2);
}
```

### D.11 Horizontal Rule

```css
hr {
    border: none;
    border-top: 1px solid var(--border-light);
    margin: var(--space-6) 0;
}
```

### D.12 Skeleton Loading

```css
.skeleton {
    color: var(--text-muted);
    animation: pulse 1.5s ease-in-out infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
}
```

---

## E. Page-Specific Layouts

### E.1 Home Page (`home.html`)

**Current:** Single column of `.cluster-card` divs. Each card has a `.cluster-label` heading and a list of `.article-item` rows.

**After redesign:**
- Container: 1120px max-width (wider)
- Grid: single column below 1200px, 2-column above
- First (top-priority) cluster spans full width
- Cards have hover lift effect
- Article items are regular text color (not blue), turning accent on hover
- Article items expand to card edge on hover with `--bg-elevated` background

**No template changes needed.** The `.clusters` wrapper already exists.

### E.2 Reader Page (`reader.html`)

**Current:** 960px single column, article title is h1 at 1.5rem, body at 1rem.

**After redesign:**
- Container: 780px max-width (narrower, reading-optimized)
- Article title: 32px bold, ample whitespace
- Article body: 18px, line-height 1.85
- Meta line under title: 14px muted
- Analysis sections: left purple border accent
- Feedback bar: subtle gradient background
- Concept lookup: lighter weight
- Separators (hr): softer `--border-light`

**No template changes needed.** Pure CSS refinement.

### E.3 Admin Page (`admin.html`)

**Current:** 4 stat cards in `.admin-stats` flex row, then tables.

**After redesign:**
- Container: 1120px max-width
- Stat cards get a subtle top border accent: blue for articles, purple for tokens, green for cost, gold for sources
- Stat numbers at 2.5rem (was 2rem), with `--weight-bold`
- Tables: uppercase headers, zebra striping, hover rows
- Error log: last column gets `.cell-truncate` for long messages

```css
/* Stat card color accents */
.admin-stats .admin-stat:nth-child(1) { border-top: 3px solid var(--accent); }
.admin-stats .admin-stat:nth-child(2) { border-top: 3px solid var(--accent-secondary); }
.admin-stats .admin-stat:nth-child(3) { border-top: 3px solid var(--success); }
.admin-stats .admin-stat:nth-child(4) { border-top: 3px solid var(--accent-warm); }

.admin-stat {
    flex: 1;
    text-align: center;
    padding: var(--space-4) var(--space-3);
    background: var(--gradient-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
}
.admin-stat-num {
    font-size: 2.5rem;                        /* was 2rem */
    font-weight: var(--weight-bold);
    color: var(--accent);
    line-height: 1.2;
}
.admin-stat-label {
    color: var(--text-muted);
    font-size: var(--text-xs);
    margin-top: var(--space-1);
}

.admin-meta {
    color: var(--text-muted);
    font-size: var(--text-sm);
    margin-bottom: var(--space-4);
}

.no-data {
    color: var(--text-muted);
    padding: var(--space-8) 0;
    text-align: center;
    font-style: italic;
}
```

### E.4 Graph Page (`graph.html`)

**Current:** Controls at top, SVG canvas below. Inline `<script>` for force layout.

**After redesign:**
- Container: 960px (centered)
- Controls: tighter grouping
- SVG container: elevated background, rounded corners, subtle border
- Labels below SVG: better typography
- Period links: pill-shaped, active state with accent background

```css
.graph-controls {
    margin-bottom: var(--space-4);
    display: flex;
    gap: var(--space-2);
    align-items: center;
}

.graph-period-link {
    font-weight: var(--weight-medium);
    padding: var(--space-1) var(--space-3);
    border-radius: var(--radius-xl);          /* pill shape */
    transition: all var(--transition-fast);
}
.graph-period-link.active {
    font-weight: var(--weight-semibold);
    background: var(--accent-soft);
    color: var(--accent);
}

.graph-compare-select {
    margin-left: var(--space-2);
    padding: var(--space-1) var(--space-2);
    background: var(--bg-surface);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: var(--text-sm);
}

.graph-compare-cancel {
    margin-left: var(--space-1);
}

.graph-compare-row {
    display: flex;
    gap: var(--space-4);
    flex-wrap: wrap;
}
.graph-compare-col {
    flex: 1;
    min-width: 300px;
}

.graph-label {
    text-align: center;
    color: var(--text-muted);
    margin-bottom: var(--space-1);
    font-size: var(--text-sm);
}
.graph-label-lg {
    margin-bottom: var(--space-2);
    font-size: var(--text-base);
}

.graph-svg {
    background: var(--bg-elevated);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
}
```

### E.5 Sources & Candidates Pages

**Container:** 1120px max-width.
**Tables:** Zebra striping, hover rows, uppercase headers.
**Add form:** Distinct card with subtle top accent border.

```css
.add-source-form {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
    border-left: 3px solid var(--accent);     /* blue left accent */
}

.sources-toolbar {
    margin-bottom: var(--space-4);
}

.candidate-url {
    color: var(--text-dim);
    font-size: var(--text-xs);
}
.candidate-empty {
    color: var(--text-muted);
    margin-top: var(--space-6);
    text-align: center;
    padding: var(--space-8) 0;
}
.candidate-actions {
    display: flex;
    gap: var(--space-2);
}
```

### E.6 Concepts Page

**Container:** 780px (reading width).

```css
.concepts-list {
    margin: var(--space-4) 0;
}
.concept-item {
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border-light);
}
.concept-item strong a {
    color: var(--accent);
    font-weight: var(--weight-semibold);
}
.query-count {
    color: var(--text-muted);
    font-size: var(--text-xs);
    margin-left: var(--space-2);
}
```

### E.7 Concept Detail Page

```css
.concept-meta {
    display: flex;
    gap: var(--space-5);
    margin: var(--space-3) 0;
    color: var(--text-muted);
    font-size: var(--text-sm);
}

.concept-chart {
    margin: var(--space-6) 0;
    padding: var(--space-4);
    background: var(--bg-surface);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
}
.concept-chart h2 {
    margin-top: 0;
    font-size: var(--text-md);
    color: var(--text-muted);
}

/* Related articles section */
.related-articles {
    margin-top: var(--space-6);
}
.related-articles h2 {
    font-size: var(--text-md);
    margin-bottom: var(--space-3);
}
```

### E.8 Search Page

**Container:** 780px.

```css
.search-results {
    margin: var(--space-4) 0;
}
.search-result-item {
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--border-light);
}
.snippet {
    color: var(--text-muted);
    font-size: var(--text-sm);
    margin-top: var(--space-1);
    line-height: var(--leading-normal);
}
.snippet mark {
    background: rgba(88, 166, 255, 0.25);     /* slightly more visible */
    color: var(--text);
    padding: 1px 3px;
    border-radius: 2px;
}
```

### E.9 Review Page

**Container:** 780px.

```css
.review-content {
    line-height: var(--leading-loose);
    margin: var(--space-4) 0;
    font-size: var(--text-base);
}
.review-meta {
    color: var(--text-muted);
    font-size: var(--text-sm);
}

.export-bar {
    margin: var(--space-4) 0;
}
```

### E.10 LLM Config Page

```css
/* Inherits .add-source-form for the config form */
/* The tips box at the bottom: */
.llm-tips {
    margin-top: var(--space-6);
    padding: var(--space-3) var(--space-4);
    background: var(--bg-surface);
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    font-size: var(--text-sm);
}
.llm-tips ul {
    margin: var(--space-2) 0 0 var(--space-4);
    color: var(--text-muted);
    line-height: var(--leading-relaxed);
}
```

---

## F. Empty States

### F.1 General Empty State

```css
.empty-state {
    text-align: center;
    padding: var(--space-16) 0;              /* 64px, was 80px */
    color: var(--text-muted);
}
.empty-state h2 {
    font-size: var(--text-xl);
    margin-bottom: var(--space-3);
    color: var(--text);
}
.empty-state p {
    font-size: var(--text-base);
    margin-bottom: var(--space-2);
    color: var(--text-muted);
}
```

### F.2 Setup Steps (Home empty state)

```css
.empty-state .setup-steps {
    text-align: left;
    max-width: 560px;                         /* was 600px */
    margin: var(--space-6) auto;
    padding: var(--space-5);
    background: var(--bg-surface);
    border: 1px dashed var(--border-light);   /* dashed — it's a guide */
    border-radius: var(--radius-lg);
}
.empty-state .setup-steps h3 {
    color: var(--text);
    margin-bottom: var(--space-3);
    font-size: var(--text-md);
}
.empty-state .setup-steps ol {
    padding-left: var(--space-5);
    line-height: var(--leading-relaxed);
    color: var(--text-muted);
}
.empty-state .setup-steps code {
    background: var(--bg-elevated);
    padding: 1px 6px;
    border-radius: var(--radius-sm);
    font-size: 0.9em;
    color: var(--accent-warm);                /* gold for paths/filenames */
}
.empty-state .setup-steps pre {
    background: var(--bg-deep);
    border: 1px solid var(--border);
    padding: var(--space-3);
    border-radius: var(--radius-md);
    overflow-x: auto;
    font-size: var(--text-sm);
    margin-top: var(--space-2);
}
.empty-state .setup-steps pre code {
    background: none;
    padding: 0;
    color: var(--text);
}
```

---

## G. Template Changes Required

### G.1 ONE Change: Body Class in `base.html`

**Current:**
```html
<body>
```

**Change to:**
```html
<body class="{{ page_class | default('') }}">
```

Then each template sets `{% set page_class = 'home' %}` (or `reader`, `admin`, etc.) at the top. This enables per-page CSS targeting without touching structure.

### G.2 Nav Active State (Optional Enhancement)

Add a conditional class to nav links based on `page_class`. This is a nice-to-have, not required.

---

## H. Transitions & Animations

### H.1 Global Transition Rules

Every interactive element gets a transition. Use the CSS variables:

```css
/* Links */
a {
    color: var(--accent);
    text-decoration: none;
    transition: color var(--transition-fast);
}
a:hover {
    color: var(--accent-hover);
    text-decoration: underline;
}

/* Cards */
.cluster-card,
.rec-card,
.analysis-section,
.add-source-form,
.concept-chart {
    transition: border-color var(--transition-normal),
                box-shadow var(--transition-normal);
}

/* Table rows */
.sources-table tbody tr,
.candidates-table tbody tr {
    transition: background var(--transition-fast);
}

/* Buttons */
.btn, .btn-primary, .btn-danger, .btn-positive, .btn-negative {
    transition: all var(--transition-fast);
}

/* Inputs */
.search-input,
.add-source-form input,
.add-source-form select {
    transition: border-color var(--transition-fast),
                box-shadow var(--transition-fast);
}

/* Nav links */
.bottom-nav a {
    transition: color var(--transition-fast),
                border-color var(--transition-fast);
}
```

### H.2 Hover Lift (Cards)

All cards get a subtle shadow on hover:

```css
.cluster-card:hover,
.rec-card:hover,
.analysis-section:hover {
    border-color: var(--border-light);
    box-shadow: var(--shadow-md);
}
```

### H.3 Pulse Animation (unchanged, refined)

```css
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
}
```

---

## I. Implementation Order (Priority)

### P0 — Foundation (affects all pages)
1. Replace `:root` block with new CSS variables
2. Update `body` global reset (bg, font-smoothing)
3. Update heading hierarchy (h1/h2/h3)
4. Update `.container` widths
5. Update `.app-header` / `.app-title`
6. Update `.bottom-nav` with link styles
7. Update `.btn` family
8. Add input focus styles
9. Add global transition rules

### P1 — Home Page
1. Update `.cluster-card` with hover
2. Update `.article-item` with hover expand
3. Change `.article-link` color scheme
4. Add `.clusters` grid layout
5. Update `.digest-summary`
6. Update `.empty-state` / `.setup-steps`

### P2 — Reader Page
1. Update article title sizing
2. Update `.article-body` typography
3. Update `.analysis-section` with left accent
4. Update `.feedback-bar` with gradient
5. Update `.concept-lookup` spacing
6. Update `.rec-card` styling

### P3 — Admin, Sources, Candidates
1. Update `.admin-stats` with color accents
2. Update table styles (zebra, hover, uppercase headers)
3. Update `.add-source-form`
4. Update `.candidate-*` styles

### P4 — Remaining Pages
1. Concepts list/detail
2. Search results
3. Review page
4. Graph controls
5. LLM config tips box

### P5 — Polish
1. Concept badge / lifecycle badge refinements
2. Back link styling
3. Priority dot
4. Export bar
5. Status colors

---

## J. Verification Checklist

- [ ] All 244 existing tests still pass
- [ ] No inline styles remain in templates
- [ ] No new `<script>` blocks added
- [ ] htmx interactions unchanged (no JS event conflicts)
- [ ] Min-width 1024px renders correctly
- [ ] Home page clusters in grid at 1200px+
- [ ] Reader page typography comfortable to read
- [ ] Admin stats have color-coded top borders
- [ ] Tables have zebra striping and hover
- [ ] All hover states have smooth 0.15-0.2s transitions
- [ ] Focus states visible on all inputs
- [ ] Empty states look intentional, not broken
- [ ] No hardcoded color values (all use CSS variables)
- [ ] Contrast ratios meet at least AA for all text
