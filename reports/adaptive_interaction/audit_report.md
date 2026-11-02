# Audit report

- Source revision audited: `a6760e6c2cdae6f2bc9c0d5063b563703314dc9f`.
- Dataset audit: 23,048 train / 3,305 validation / 6,613 test; normalized text overlap is zero for all split pairs.
- Existing `phobert/mtl` report contains 15 seeds (42–56); the matched primary slice 42–46 is extracted without changing selection rules.
- Existing MLM rows contain 5 seeds; CR-SD reports contain 2 seeds and are secondary.
- New runs: no full-data GPU run was executed because this host has no NVIDIA device and no authenticated Kaggle execution interface.
- No proposed metric is imputed; placeholders remain missing.
