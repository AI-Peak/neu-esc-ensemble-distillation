# NEU-ESC Feedback Workspace

## Context

An operator reads and checks student feedback on a laptop at a desk in daylight. The interface is a dense, readable working tool. White surfaces preserve contrast; cobalt identifies the next action and current selection. Research is a secondary navigation destination.

## Tokens

- Background: pure white, `oklch(1 0 0)`.
- Brand anchor: cobalt, `oklch(0.550 0.149 250)`; hover `oklch(.47 .145 250)`.
- Demo Theme (Layout 2): Deep teal `#0f766e` / `#0d9488`, slate neutrals, soft teal tints for active cards and progress indicators.
- Ink: `oklch(.25 .022 250)`; supporting text `oklch(.46 .025 250)`.
- Neutral surface: `oklch(.977 .006 250)`; border `oklch(.88 .013 250)`.
- System font: Segoe UI, system-ui. Font Be Vietnam Pro (`/fonts/be-vietnam-pro-*.ttf`) bundled locally for optimal Vietnamese typography in the Sentence Demo without external Google Fonts requests. Base 14px / 1.5; table 12–13px; headings 16–25px. All support Vietnamese without remote font requests.
- Sentence Demo overrides the workspace scale: body 16–18px, labels/captions at least 14px, including shared sensitivity/attention components inside the demo. Preserve the approved teal layout.
- Corners: controls 5–6px, dialogs 10px. Dividers organize the workspace rather than nested cards.

## Interaction

Top-level navigation: default route `#/demo` for the single sentence 3-layer demo, datasets `#/`, new dataset `#/new`, research `#/research`, status/help `#/help`.
The Sentence Demo (`#/demo`) implements Layout 2 in a vertical stack:
- **Header**: Brand title, dataset shortcut, and research tab link.
- **Input row**: Full-width textarea with character counter, 3 sample preset buttons (populates text without auto-submitting), and profile selector.
- **Layer 1 (AI Prediction)**: Renders immediately when the quick-analysis job finishes. Shows primary sentiment and topic tags, confidence percentages, and complete probability bars for all classes (10 NEU topics or 4 UIT topics) with uncalibrated score notices.
- **Layer 2 (Signals, Explanation & Sensitivity)**: Shows local review signals (`review_signals`) instantly. Auto-triggers upstream explanation via 9router (`POST /api/v1/quick-analysis/{job_id}/explanation`) with an indeterminate loading shimmer while Layer 1 remains interactive. Renders sanitized `reading` and `caution` with a retry action, followed by the embedded SensitivityPanel.
- **Layer 3 (Decision Support)**: Connects to selected real datasets via `/datasets/{id}/summary` and `/datasets/{id}/items`. Displays the highest-negative topic, distributions, drill-down feedback items with pagination, and an action to open the dataset in the main workspace. No synthetic numbers.

Dataset work uses tabs, shared filters, chart buttons, a paginated server table, and a native dialog aligned to the right for detail. Hash routes keep deep links usable with a static server. Filters persist per dataset for the browser session.

Every chart button applies the same filter model as list, summary and export. Denominators explicitly count rows with a label. AI predictions, reference labels, and human reviews have separate sections and export fields. Reviews are independent for sentiment/topic. Text edits create revisions; historical results warn when stale.

Native form controls, visible keyboard focus, dialog focus management, semantic headings and live status messages support keyboard and assistive technology. At 650px, the item table becomes a stacked list and the detail dialog fills the screen. Reduced motion disables transitions and panel entry. Empty states describe the next action; missing models never produce synthetic predictions.

## Validation

`npm run build` passes strict TypeScript and the Vite production build. Dependencies are pinned with a package lock; `npm audit` reports zero vulnerabilities (Vite 7.3.7).

Playwright checked the complete CSV/import → analysis → chart filtering → independent review → snapshot export → API restart flow at 1440px and import/persistence/missing-model behavior at 390px, with no page errors or horizontal body overflow. Additional browser assertions covered AI confirmation, review undo, double-task save-next, text revisions and stale warnings, disabled restoration from older input revisions, and quick-analysis polling/add-to-dataset. Screenshots were inspected. These integration runs explicitly use a test-only predictor double, not a production model or benchmark claim.

Network/model errors remain visible and actionable; retries never replace real inference with fabricated output. Missing-model technical paths live inside collapsed details; empty summaries show an explanatory state until labels exist.
