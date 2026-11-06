# NEU-ESC Feedback Workspace

## Context

An operator reads and checks student feedback on a laptop at a desk in daylight. The interface is a dense, readable working tool. White surfaces preserve contrast; cobalt identifies the next action and current selection. Research is a secondary navigation destination.

## Tokens

- Background: pure white, `oklch(1 0 0)`.
- Brand anchor: cobalt, `oklch(0.550 0.149 250)`; hover `oklch(.47 .145 250)`.
- Ink: `oklch(.25 .022 250)`; supporting text `oklch(.46 .025 250)`.
- Neutral surface: `oklch(.977 .006 250)`; border `oklch(.88 .013 250)`.
- System font: Segoe UI, system-ui. Base 14px / 1.5; table 12–13px; headings 16–25px. All support Vietnamese without remote font requests.
- Corners: controls 5–6px, dialogs 10px. Dividers organize the workspace rather than nested cards.

## Interaction

Top-level navigation: datasets, quick sentence, research, status/help. Dataset work uses tabs, shared filters, chart buttons, a paginated server table, and a native dialog aligned to the right for detail. Hash routes keep deep links usable with a static server. Filters persist per dataset for the browser session.

Every chart button applies the same filter model as list, summary and export. Denominators explicitly count rows with a label. AI predictions, reference labels, and human reviews have separate sections and export fields. Reviews are independent for sentiment/topic. Text edits create revisions; historical results warn when stale.

Native form controls, visible keyboard focus, dialog focus management, semantic headings and live status messages support keyboard and assistive technology. At 650px, the item table becomes a stacked list and the detail dialog fills the screen. Reduced motion disables transitions and panel entry. Empty states describe the next action; missing models never produce synthetic predictions.

## Validation

`npm run build` passes strict TypeScript and the Vite production build. Dependencies are pinned with a package lock; `npm audit` reports zero vulnerabilities (Vite 7.3.7).

Playwright checked the complete CSV/import → analysis → chart filtering → independent review → snapshot export → API restart flow at 1440px and import/persistence/missing-model behavior at 390px, with no page errors or horizontal body overflow. Additional browser assertions covered AI confirmation, review undo, double-task save-next, text revisions and stale warnings, disabled restoration from older input revisions, and quick-analysis polling/add-to-dataset. Screenshots were inspected. These integration runs explicitly use a test-only predictor double, not a production model or benchmark claim.

Network/model errors remain visible and actionable; retries never replace real inference with fabricated output. Missing-model technical paths live inside collapsed details; empty summaries show an explanatory state until labels exist.
