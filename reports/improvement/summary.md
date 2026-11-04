# CR-SD results against the reproduced baselines

Test accuracy in %, mean ± std over seeds, validation selection. Paper = Table 6 (one run).

| Backbone | Setup | n | Sentiment | Topic | Paper |
|---|---|---:|---:|---:|---:|
| phobert | single | 15 | 82.27 ± 0.40 | 78.16 ± 0.58 | 81.75 / 78.65 |
| phobert | mtl | 15 | 82.39 ± 0.71 | 78.75 ± 0.36 | 82.88 / 79.25 |
| phobert | mtl_smart | 15 | 82.85 ± 0.24 | 79.05 ± 0.17 | 83.26 / 79.31 |
| phobert | mtl_mlm | 5 | 82.42 ± 0.26 | 78.38 ± 0.64 | 82.67 / 78.48 |
| phobert | mtl_mlm_smart | 5 | 82.77 ± 0.06 | 79.09 ± 0.18 | 83.66 / 79.49 |
| phobert | selfdistill | 15 | 83.29 ± 0.23 | 79.69 ± 0.25 | — |
| phobert | crsd_ens | 15 | 83.56 ± 0.17 | 80.00 ± 0.18 | — |
| visobert | single | 15 | 82.30 ± 0.64 | 78.11 ± 0.42 | 82.78 / 77.94 |
| visobert | mtl | 15 | 82.04 ± 0.43 | 78.22 ± 0.55 | 82.63 / 78.56 |
| visobert | mtl_smart | 15 | 82.71 ± 0.18 | 79.35 ± 0.16 | 83.58 / 79.80 |
| visobert | mtl_mlm | 5 | 81.89 ± 0.29 | 78.04 ± 0.20 | 82.23 / 78.38 |
| visobert | mtl_mlm_smart | 5 | 82.83 ± 0.14 | 79.46 ± 0.23 | 83.12 / 79.25 |
| visobert | selfdistill | 15 | 82.89 ± 0.19 | 79.18 ± 0.23 | — |
| visobert | crsd_ens | 15 | 83.51 ± 0.13 | 79.85 ± 0.16 | — |

## Improvement vs baseline (Δ of means, Welch p)

| Backbone | Setup | Task | n | EMA (reported) | Student | Δ vs mtl | p | Δ vs mtl_smart | p |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| phobert | selfdistill | sentiment | 15 | 83.29 ± 0.23 | 83.26 ± 0.23 | +0.90 | 0.000 | +0.44 | 0.000 |
| phobert | selfdistill | topic | 15 | 79.69 ± 0.25 | 79.45 ± 0.28 | +0.94 | 0.000 | +0.64 | 0.000 |
| phobert | crsd_ens | sentiment | 15 | 83.56 ± 0.17 | 83.49 ± 0.18 | +1.17 | 0.000 | +0.71 | 0.000 |
| phobert | crsd_ens | topic | 15 | 80.00 ± 0.18 | 79.99 ± 0.20 | +1.24 | 0.000 | +0.94 | 0.000 |
| visobert | selfdistill | sentiment | 15 | 82.89 ± 0.19 | 82.68 ± 0.18 | +0.84 | 0.000 | +0.17 | 0.015 |
| visobert | selfdistill | topic | 15 | 79.18 ± 0.23 | 79.12 ± 0.26 | +0.96 | 0.000 | -0.17 | 0.027 |
| visobert | crsd_ens | sentiment | 15 | 83.51 ± 0.13 | 83.50 ± 0.15 | +1.47 | 0.000 | +0.80 | 0.000 |
| visobert | crsd_ens | topic | 15 | 79.85 ± 0.16 | 79.92 ± 0.14 | +1.63 | 0.000 | +0.50 | 0.000 |
