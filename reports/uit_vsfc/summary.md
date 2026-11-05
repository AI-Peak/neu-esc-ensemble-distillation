# ED results against the reproduced baselines (UIT-VSFC)

Test accuracy in %, mean ± std over seeds, validation selection.

| Backbone | Setup | n | Sentiment | Topic | Paper |
|---|---|---:|---:|---:|---:|
| phobert | mtl | 10 | 93.77 ± 0.16 | 89.05 ± 0.70 | — |
| phobert | mtl_smart | 10 | 92.44 ± 0.20 | 88.96 ± 0.22 | — |
| phobert | mtl_mlm | 10 | 93.84 ± 0.13 | 89.10 ± 0.40 | — |
| phobert | mtl_mlm_smart | 10 | 92.54 ± 0.21 | 89.11 ± 0.23 | — |
| phobert | mtl_ed | 10 | 93.88 ± 0.12 | 89.71 ± 0.11 | — |
| visobert | mtl | 10 | 92.71 ± 0.20 | 88.77 ± 0.48 | — |
| visobert | mtl_smart | 10 | 92.36 ± 0.24 | 88.91 ± 0.19 | — |
| visobert | mtl_mlm | 10 | 92.80 ± 0.29 | 88.54 ± 0.48 | — |
| visobert | mtl_mlm_smart | 10 | 92.42 ± 0.24 | 88.85 ± 0.25 | — |
| visobert | mtl_ed | 10 | 93.08 ± 0.10 | 89.32 ± 0.16 | — |

## ED vs each baseline: test accuracy (Δ of means, Welch p)

| Backbone | Task | n | ED | Δ vs single | p | Δ vs mtl | p | Δ vs mtl_smart | p | Δ vs mtl_mlm | p | Δ vs mtl_mlm_smart | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| phobert | sentiment | 10 | 93.88 ± 0.12 | — | — | +0.11 | 0.106 | +1.44 | 0.000 | +0.03 | 0.543 | +1.34 | 0.000 |
| phobert | topic | 10 | 89.71 ± 0.11 | — | — | +0.66 | 0.016 | +0.75 | 0.000 | +0.61 | 0.001 | +0.60 | 0.000 |
| visobert | sentiment | 10 | 93.08 ± 0.10 | — | — | +0.37 | 0.000 | +0.72 | 0.000 | +0.28 | 0.013 | +0.66 | 0.000 |
| visobert | topic | 10 | 89.32 ± 0.16 | — | — | +0.55 | 0.006 | +0.41 | 0.000 | +0.78 | 0.001 | +0.47 | 0.000 |

## ED vs each baseline: test macro-F1 (Δ of means, Welch p)

| Backbone | Task | n | ED | Δ vs single | p | Δ vs mtl | p | Δ vs mtl_smart | p | Δ vs mtl_mlm | p | Δ vs mtl_mlm_smart | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| phobert | sentiment | 10 | 82.02 ± 0.51 | — | — | -0.09 | 0.778 | +5.16 | 0.000 | -0.57 | 0.022 | +4.88 | 0.000 |
| phobert | topic | 10 | 80.70 ± 0.58 | — | — | +0.69 | 0.019 | +1.92 | 0.000 | +0.85 | 0.010 | +1.57 | 0.000 |
| visobert | sentiment | 10 | 80.34 ± 0.49 | — | — | -0.13 | 0.757 | +2.24 | 0.000 | -0.37 | 0.264 | +2.03 | 0.000 |
| visobert | topic | 10 | 80.42 ± 0.34 | — | — | +0.95 | 0.000 | +0.90 | 0.001 | +1.15 | 0.000 | +0.98 | 0.001 |
