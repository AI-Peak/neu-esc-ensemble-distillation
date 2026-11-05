# ED results against the reproduced baselines (NEU-ESC)

Test accuracy in %, mean ± std over seeds, validation selection. Paper = Table 6 (one run).

| Backbone | Setup | n | Sentiment | Topic | Paper |
|---|---|---:|---:|---:|---:|
| phobert | single | 15 | 82.27 ± 0.40 | 78.16 ± 0.58 | 81.75 / 78.65 |
| phobert | mtl | 15 | 82.39 ± 0.71 | 78.75 ± 0.36 | 82.88 / 79.25 |
| phobert | mtl_smart | 15 | 82.85 ± 0.24 | 79.05 ± 0.17 | 83.26 / 79.31 |
| phobert | mtl_mlm | 15 | 82.25 ± 0.53 | 78.46 ± 0.44 | 82.67 / 78.48 |
| phobert | mtl_mlm_smart | 15 | 82.83 ± 0.16 | 79.09 ± 0.17 | 83.66 / 79.49 |
| phobert | mtl_ed | 15 | 83.51 ± 0.24 | 79.65 ± 0.27 | — |
| visobert | single | 15 | 82.30 ± 0.64 | 78.11 ± 0.42 | 82.78 / 77.94 |
| visobert | mtl | 15 | 82.04 ± 0.43 | 78.22 ± 0.55 | 82.63 / 78.56 |
| visobert | mtl_smart | 15 | 82.71 ± 0.18 | 79.35 ± 0.16 | 83.58 / 79.80 |
| visobert | mtl_mlm | 15 | 81.83 ± 0.68 | 78.18 ± 0.41 | 82.23 / 78.38 |
| visobert | mtl_mlm_smart | 15 | 82.82 ± 0.16 | 79.55 ± 0.20 | 83.12 / 79.25 |
| visobert | mtl_ed | 15 | 83.25 ± 0.18 | 79.73 ± 0.17 | — |

## ED vs each baseline: test accuracy (Δ of means, Welch p)

| Backbone | Task | n | ED | Δ vs single | p | Δ vs mtl | p | Δ vs mtl_smart | p | Δ vs mtl_mlm | p | Δ vs mtl_mlm_smart | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| phobert | sentiment | 15 | 83.51 ± 0.24 | +1.24 | 0.000 | +1.12 | 0.000 | +0.66 | 0.000 | +1.26 | 0.000 | +0.68 | 0.000 |
| phobert | topic | 15 | 79.65 ± 0.27 | +1.49 | 0.000 | +0.90 | 0.000 | +0.60 | 0.000 | +1.19 | 0.000 | +0.56 | 0.000 |
| visobert | sentiment | 15 | 83.25 ± 0.18 | +0.96 | 0.000 | +1.21 | 0.000 | +0.54 | 0.000 | +1.42 | 0.000 | +0.43 | 0.000 |
| visobert | topic | 15 | 79.73 ± 0.17 | +1.62 | 0.000 | +1.51 | 0.000 | +0.38 | 0.000 | +1.55 | 0.000 | +0.18 | 0.011 |

## ED vs each baseline: test macro-F1 (Δ of means, Welch p)

| Backbone | Task | n | ED | Δ vs single | p | Δ vs mtl | p | Δ vs mtl_smart | p | Δ vs mtl_mlm | p | Δ vs mtl_mlm_smart | p |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| phobert | sentiment | 15 | 77.91 ± 0.28 | +0.67 | 0.000 | +1.05 | 0.000 | +1.85 | 0.000 | +1.06 | 0.000 | +1.68 | 0.000 |
| phobert | topic | 15 | 63.57 ± 0.40 | +2.08 | 0.000 | +1.34 | 0.000 | +1.62 | 0.000 | +1.66 | 0.000 | +1.46 | 0.000 |
| visobert | sentiment | 15 | 77.22 ± 0.28 | +0.71 | 0.000 | +1.15 | 0.000 | +1.50 | 0.000 | +1.23 | 0.000 | +1.17 | 0.000 |
| visobert | topic | 15 | 63.05 ± 0.26 | +1.73 | 0.000 | +1.35 | 0.000 | +0.84 | 0.000 | +1.49 | 0.000 | +0.47 | 0.021 |
