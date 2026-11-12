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

Top-level navigation: default route `#/demo` for the single sentence analysis, datasets `#/`, new dataset `#/new`, research `#/research`, status/help `#/help`.
The Sentence Demo (`#/demo`) implements the clean 2026-11-12 redesigned interface in a vertical flow:
- **Header**: Brand title `NEU–ESC`, navigation links (`Phân tích câu`, `Câu vừa phân tích`, `Mạng từ`), and profile selector.
- **Input row**: Full-width textarea with character counter, "Phân tích" primary button, and "Xóa" button. Redundant boilerplate and preset buttons removed per teammate Dat's feedback.
- **Local AI Prediction**: Renders immediately when the quick-analysis job finishes. Shows primary sentiment and topic tags, confidence percentages, score stack, and complete probability bars for all classes (10 NEU topics or 4 UIT topics) with uncalibrated score notices.
- **Word Attribution & Contributions (P0)**: 4-column desktop layout (`Phản hồi`, `Từ quan trọng`, `Trọng số cảm xúc`, `Tổng đóng góp`). The feedback cell centers the quote with quotes and interactive word marks. Table rows display weight meters and percentage points. Single merged total cell displays the net contribution. Bi-directional selection between words and table rows. Expandable "Cách tính tổng" reveals sampled K=8 permutation Shapley, float64 additivity equation, baseline and limitations. Neutral/Toxic uses label_score with blue/amber indicators. No external LLM dependencies.
- **Latest Sentence Overview (P1)**: Informational SVG contribution donut using all original groups from the same validated attribution snapshot as the table. Positive/negative contribution mass is normalized to100%; the center reads “Đóng góp từ ngữ”, with two textual percentage legend rows and a short limitation note. Polarity uses green/red “Nghiêng tích cực/tiêu cực”; label_score uses blue/brown “Tăng/Giảm điểm [profile label]”. No count/net sentiment KPI, interactive segments or evidence filter on this chart. Loading/error/unsupported/zero contributions have explicit states; summary loading never gates the donut. Topic attention ranking retains negative counts, proportions, small-sample warnings and evidence filtering on the latest quick-analysis dataset/run. One input remains a single text item even when it has several sentences, without history accumulation or a dataset selector.
- **Word Co-occurrence Network (P2)**: SVG graph canvas displaying terms from that same latest sentence (window=5 original segmented-token positions before stopword filtering, distance <=4) connected by co-occurrence edges, connected components groups with consistent color swatches, sidebar insights, and drill-down to matching feedback items. Editing, clearing or changing profile removes the previous analysis scope.
- **Evidence Drill-Down**: Interactive cards displaying matching feedback rows with active filter chips, sentiment/topic badges, and pagination.

Dataset work uses tabs, shared filters, chart buttons, a paginated server table, and a native dialog aligned to the right for detail. Hash routes keep deep links usable with a static server. Filters persist per dataset for the browser session.

Every chart button applies the same filter model as list, summary and export. Denominators explicitly count rows with a label. AI predictions, reference labels, and human reviews have separate sections and export fields. Reviews are independent for sentiment/topic. Text edits create revisions; historical results warn when stale.

Native form controls, visible keyboard focus, dialog focus management, semantic headings and live status messages support keyboard and assistive technology. At 650px, the item table becomes a stacked list and the detail dialog fills the screen. Reduced motion disables transitions and panel entry. Empty states describe the next action; missing models never produce synthetic predictions.

## Validation

`npm run build` passes strict TypeScript and the Vite production build. Dependencies are pinned with a package lock; `npm audit` reports zero vulnerabilities (Vite 7.3.7).

Playwright checked the complete CSV/import → analysis → chart filtering → independent review → snapshot export → API restart flow at 1440px and import/persistence/missing-model behavior at 390px, with no page errors or horizontal body overflow. Additional browser assertions covered AI confirmation, review undo, double-task save-next, text revisions and stale warnings, disabled restoration from older input revisions, and quick-analysis polling/add-to-dataset. Screenshots were inspected. These integration runs explicitly use a test-only predictor double, not a production model or benchmark claim.

Network/model errors remain visible and actionable; retries never replace real inference with fabricated output. Missing-model technical paths live inside collapsed details; empty summaries show an explanatory state until labels exist.
