# NEU-ESC feedback mockup

One interactive design direction for the teammate feedback received on 2026-11-12.

Open `mockup-share.html` directly for a self-contained version, or serve the parent `design-previews` directory and open `/2026-11-12/`.

## Included

- The current sentence prediction concept, with sentiment, score, topic and expandable topic scores.
- A four-column feedback / phrase / contribution / total table inspired by reference image 1.
- Positive/negative phrase highlights linked to table selection, inspired by image 2.
- A four-class sentiment donut and topic counts, with linked feedback evidence.
- A co-occurrence graph with selectable terms and illustrative communities.
- Responsive desktop, tablet and mobile layouts, keyboard controls and reduced motion.

## Data and boundaries

All predictions, attribution weights and labels are authored design fixtures. No API, LLM, model, database, telemetry or remote assets are used. Input outside the single authored sentence receives no prediction; a reset action restores the fixture. The 350 ms transition demonstrates a UI state, not inference performance.

Attribution is illustrative: +12.4 - 28.6 - 48.8 - 8.6 = -73.6. With a +0.8 baseline, the result is -72.8, matching the fixture's positive score (10.6) minus negative score (83.4). This prototype does not implement Shapley or make an attribution-validity claim.

The 24 authored feedback records contain 6 Positive, 14 Negative, 3 Neutral and 1 Toxic labels. Donut, topic counts, net sentiment and feedback drill-down are calculated from those records. Graph nodes count matching feedback records; edges count co-occurrence within the same feedback, with the strongest 44 displayed. Node positions and three communities are authored visual examples, not clustering results. Graph colors mean communities, not sentiment.

Desktop uses four table columns. On tablet, feedback moves above the contribution columns. On mobile, feedback, phrase/score rows and total stack in reading order. The highlight copy and weights intentionally remain visible without hover.

## Files

- `index.html`, `styles.css`, `mockup.js`: editable source.
- `mockup-share.html`: generated portable HTML with embedded fonts, styles and script.
- `analysis-desktop.png`: preview of the main analysis surface.
- `mockup-desktop.png`, `mockup-mobile.png`: full-page previews.

Fonts reuse the project's local Be Vietnam Pro files under the SIL Open Font License. The portable version embeds the fonts and license. No production application files are changed by this mockup.

## Verification

Checked in headless Chromium at 320, 390, 768, 1024, 1440 and 1920 px without horizontal document overflow. Verified linked highlights, ten topic scores, all four sentiment filters, topic drill-down, additional evidence, graph keyboard selection, community selection, the mobile term picker, unsupported input and clearing a pending preview transition. No console errors or failed asset requests occurred. The portable file also opened directly from disk with working interactions and no HTTP(S) requests. Desktop and mobile screenshots were inspected.
