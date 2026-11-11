# NEU-ESC UI previews

Three screens in one proposed light / teal design direction. These are standalone visual prototypes for approval; the application source has not been changed.

- `index.html`: overview, topic attention, sentiment distribution, next reviews.
- `review.html`: persistent list/detail layout, review form, sensitivity example.
- `quick-analysis.html`: sentence input, sample results, waiting/cancel states.

Open the HTML files directly or serve this directory with a local static HTTP server. Fonts are bundled locally under the SIL Open Font License (see fonts/OFL.txt); the previews make no external network calls.

All data is illustrative. Review actions only modify in-memory preview state and reset on reload. The analysis button simulates UI transitions for three fixed examples; arbitrary input does not generate a prediction. No API/model/database connection is made. The simulated wait is not a performance benchmark.

Feedback to collect: overall direction, information density, sidebar, review split, quick-analysis result and waiting states. Implement in the real application only after approval.
