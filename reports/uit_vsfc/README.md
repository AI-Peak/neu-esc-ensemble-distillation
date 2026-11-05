# ED trên UIT-VSFC (kiểm tra tổng quát hoá ngoài NEU-ESC)

Chạy lại đúng pipeline của NEU-ESC trên UIT-VSFC: cùng hyperparameter, cùng quy tắc chọn checkpoint
theo validation, cùng runner (`53754f0d`), không tinh chỉnh gì thêm cho dataset mới.
Dữ liệu và cách tạo CSV: [data/UIT-VSFC/README.md](../../data/UIT-VSFC/README.md).
Bảng tự sinh: [summary.md](summary.md), từng run: [per_run.csv](per_run.csv).

## 1. Kết quả

Test, mean ± std trên 10 seed (42–51), 4 baseline reproduce và ED:

| Backbone | Setup | Sent acc | Sent macro-F1 | F1 Neutral | Topic acc | Topic macro-F1 |
|---|---|---:|---:|---:|---:|---:|
| PhoBERT | `mtl` | 93.77 ± 0.16 | 82.11 ± 0.82 | 55.3 | 89.05 ± 0.70 | 80.01 ± 0.62 |
| PhoBERT | `mtl_smart` | 92.44 ± 0.20 | 76.86 ± 0.99 | 41.9 | 88.96 ± 0.22 | 78.78 ± 0.72 |
| PhoBERT | `mtl_mlm` | 93.84 ± 0.13 | 82.59 ± 0.50 | 56.6 | 89.10 ± 0.40 | 79.86 ± 0.71 |
| PhoBERT | `mtl_mlm_smart` | 92.54 ± 0.21 | 77.14 ± 0.95 | 42.5 | 89.11 ± 0.23 | 79.13 ± 0.46 |
| PhoBERT | **ED** | **93.88 ± 0.12** | 82.02 ± 0.51 | 54.9 | **89.71 ± 0.11** | **80.70 ± 0.58** |
| ViSoBERT | `mtl` | 92.71 ± 0.20 | 80.47 ± 1.17 | 52.2 | 88.77 ± 0.48 | 79.47 ± 0.43 |
| ViSoBERT | `mtl_smart` | 92.36 ± 0.24 | 78.11 ± 0.64 | 46.0 | 88.91 ± 0.19 | 79.52 ± 0.58 |
| ViSoBERT | `mtl_mlm` | 92.80 ± 0.29 | 80.71 ± 0.87 | 52.8 | 88.54 ± 0.48 | 79.27 ± 0.69 |
| ViSoBERT | `mtl_mlm_smart` | 92.42 ± 0.24 | 78.32 ± 0.66 | 46.5 | 88.85 ± 0.25 | 79.43 ± 0.65 |
| ViSoBERT | **ED** | **93.08 ± 0.10** | 80.34 ± 0.49 | 51.3 | **89.32 ± 0.16** | **80.42 ± 0.34** |

### So với baseline mạnh nhất

Mỗi ô lấy baseline có mean test cao nhất trong 4 baseline, chọn riêng cho từng metric (so sánh khắt khe với ED). Welch t-test:

| Backbone | Task | Metric | Baseline mạnh nhất | ED | Δ (p) |
|---|---|---|---|---:|---:|
| PhoBERT | Sentiment | acc | `mtl_mlm` 93.84 ± 0.13 | 93.88 ± 0.12 | +0.03 (0.54) |
| PhoBERT | Sentiment | macro-F1 | `mtl_mlm` 82.59 ± 0.50 | 82.02 ± 0.51 | **−0.57** (0.022) |
| PhoBERT | Topic | acc | `mtl_mlm_smart` 89.11 ± 0.23 | 89.71 ± 0.11 | **+0.60** (<0.001) |
| PhoBERT | Topic | macro-F1 | `mtl` 80.01 ± 0.62 | 80.70 ± 0.58 | **+0.69** (0.019) |
| ViSoBERT | Sentiment | acc | `mtl_mlm` 92.80 ± 0.29 | 93.08 ± 0.10 | **+0.28** (0.013) |
| ViSoBERT | Sentiment | macro-F1 | `mtl_mlm` 80.71 ± 0.87 | 80.34 ± 0.49 | −0.37 (0.26) |
| ViSoBERT | Topic | acc | `mtl_smart` 88.91 ± 0.19 | 89.32 ± 0.16 | **+0.41** (<0.001) |
| ViSoBERT | Topic | macro-F1 | `mtl_smart` 79.52 ± 0.58 | 80.42 ± 0.34 | **+0.90** (0.001) |

- **Topic: ED thắng baseline mạnh nhất có ý nghĩa ở cả 2 backbone, cả accuracy lẫn macro-F1.**
- **Sentiment accuracy:** ED thắng với ViSoBERT (+0.28) và ngang với PhoBERT (+0.03, không có ý nghĩa).
- **Sentiment macro-F1:** ED thấp hơn `mtl_mlm`. Với PhoBERT chênh −0.57 (p = 0.022), với ViSoBERT −0.37 (không có ý nghĩa). So với `mtl` thì ngang (−0.09 và −0.13, p > 0.7).
- **So với `mtl_smart` (baseline chính của paper):** ED thắng ở cả 4 ô, trên cả accuracy lẫn macro-F1 (p ≤ 0.001).
- **SMART không giúp trên UIT-VSFC.** Hai setup có SMART thấp hơn hẳn ở sentiment (PhoBERT: −1.3 accuracy, −5 macro-F1 so với `mtl`).
  MLM thì giúp nhẹ ở sentiment: `mtl_mlm` là baseline sentiment mạnh nhất trên cả 2 backbone.
- Bảng đầy đủ so ED với từng baseline: [summary.md](summary.md).

Tóm lại: lợi ích của ED tổng quát hoá sang UIT-VSFC, rõ nhất ở topic. Ở sentiment, một model PhoBERT đã ngang ensemble teacher (§3) nên ED gần như không tăng;
ViSoBERT còn cách ensemble khoảng 1 điểm nên accuracy vẫn tăng. Macro-F1 sentiment của ED ngang `mtl` và thấp hơn `mtl_mlm` trên cả 2 backbone.

## 2. Lớp thiểu số

- Neutral chỉ chiếm khoảng 5% số câu (167/3166 ở test), nên F1 lớp này dao động mạnh và quyết định macro-F1 của sentiment.
- **ED giữ F1 Neutral ngang `mtl`:** PhoBERT 54.9 so với 55.3, ViSoBERT 51.3 so với 52.2 (p > 0.4).
  So với `mtl_smart` thì cao hơn nhiều: +13.0 (PhoBERT) và +5.3 (ViSoBERT), p < 0.001.
- `mtl_mlm` có F1 Neutral cao nhất (56.6 / 52.8), đây là lý do nó hơn ED về macro-F1 sentiment.
- Ở topic, lớp "others" (khoảng 5%) của ED đạt 55.6 F1.

## 3. So với ensemble teacher

Teacher gồm 30 model `mtl` theo fold (2 backbone × 3 seed × 5 fold), chỉ train trên tập train của UIT-VSFC.
Kết quả trên test:

| Teacher | Sentiment acc / mF1 / F1 Neutral | Topic acc / mF1 |
|---|---|---|
| Ensemble 30 model | 93.75 / 81.81 / 54.48 | 90.05 / 81.38 |
| Ensemble 15 model PhoBERT | 93.94 / 81.77 / 53.93 | 89.83 / 81.03 |
| Ensemble 15 model ViSoBERT | 92.96 / 80.13 / 50.75 | 89.64 / 80.81 |
| Một model fold (trung bình) | 92.99 | 88.76 |

- **Sentiment:** một model `mtl` PhoBERT train trên toàn bộ train (93.77) đã ngang ensemble 30 model (93.75).
  Teacher không có gì để dạy thêm, nên ED không tăng được nhiều accuracy sentiment với PhoBERT.
  ViSoBERT `mtl` (92.71) còn cách ensemble 1.04 điểm, và ED hơn `mtl` +0.37 (p < 0.001).
- **Topic:** teacher hơn `mtl` khoảng 1 điểm. ED thu hẹp được 66% khoảng cách này với PhoBERT
  (89.05 → 89.71 / 90.05) và 43% với ViSoBERT (88.77 → 89.32).
- Out-of-fold accuracy của teacher trên train: 94.88 (sentiment) và 89.73 (topic).

## 4. Chi phí

- **Thời gian (wall-clock trung bình mỗi run, 2×T4):** `mtl` 0.15–0.17 h, ED 0.15–0.17 h, `mtl_mlm` 0.30–0.33 h,
  `mtl_smart` 0.38–0.40 h, `mtl_mlm_smart` 0.64–0.65 h. Chưa tính 30 run fold của teacher.
- Best epoch trung bình của ED là 12.7 (PhoBERT) và 9.7 (ViSoBERT) trên 20.

## 5. Mốc tham chiếu ngoài

- Bài gốc UIT-VSFC (Nguyen et al., KSE 2018) báo cáo MaxEnt đạt F1 87.94 (sentiment) và 84.03 (topic).
  Đây chỉ là mốc sàn: khác metric, khác mô hình. Tất cả setup ở đây đều vượt xa mốc này.
- Không đưa số của các bài PhoBERT/ViSoBERT khác lên UIT-VSFC vào bảng khi chưa xác minh metric (accuracy, macro hay weighted F1),
  split (dev chính thức hay tự chia) và số lần chạy.

## 6. Hạn chế

- 10 seed mỗi ô (NEU-ESC dùng 15).
- Tách từ cho PhoBERT dùng underthesea 9.5.0 thay cho VnCoreNLP (xem README dữ liệu).
- Teacher dùng lại đúng cấu hình của NEU-ESC (3 seed × 5 fold × 2 backbone); γ = 1 không tinh chỉnh.
- Không chạy setup single-task trên UIT-VSFC.

## 7. Tái lập

Run nằm trong `runs/vsfc/` (không đưa vào git):
- `teach/`: 30 run fold và `ens_targets_vsfc{,_f16}.npz`.
- `base/`: `mtl`, `mtl_smart`.
- `mlm/`: `mtl_mlm`, `mtl_mlm_smart`.
- `ed/`: ED (`mtl_ed`).

Log từng kernel Kaggle nằm trong `*/logs/`. Mọi run đều dùng runner `53754f0d98ffd810…`.
Runner hiện tại (`37244da6…`) cho logits giống hệt bản này với mọi setup ở đây (đã kiểm trên CPU, xem [báo cáo NEU-ESC](../improvement/README.md) §7).

```bash
# 1. Teacher: 30 run fold (2 backbone x seed 42-44 x 5 fold)
python src_improvement/neu_esc_improvement.py fetch --dataset vsfc --data-dir data/UIT-VSFC
python src_improvement/run_queue.py --data-dir data/UIT-VSFC --out-dir runs/vsfc/teach --folds 5 \
    --jobs phobert:mtl:42 visobert:mtl:42 phobert:mtl:43 visobert:mtl:43 phobert:mtl:44 visobert:mtl:44 -- --dataset vsfc
python src_improvement/neu_esc_improvement.py ensemble-targets --dataset vsfc runs/vsfc/teach/vsfc-*-f?of5 --out runs/vsfc/teach/ens_targets_vsfc.npz
python -c "import numpy as np; z = np.load('runs/vsfc/teach/ens_targets_vsfc.npz'); np.savez_compressed('runs/vsfc/teach/ens_targets_vsfc_f16.npz', **{k: z[k].astype(np.float16) if k in ('sentiment', 'topic') else z[k] for k in z.files})"
# 2. mtl, mtl_smart, mtl_mlm, mtl_mlm_smart, mtl_ed x 2 backbone x seed 42-51
python src_improvement/run_queue.py --data-dir data/UIT-VSFC --out-dir runs/vsfc/base --jobs phobert:mtl:42 phobert:mtl_smart:42 ... -- --dataset vsfc
python src_improvement/run_queue.py --data-dir data/UIT-VSFC --out-dir runs/vsfc/mlm --jobs phobert:mtl_mlm:42 phobert:mtl_mlm_smart:42 ... -- --dataset vsfc
python src_improvement/run_queue.py --data-dir data/UIT-VSFC --out-dir runs/vsfc/ed --jobs phobert:mtl_ed:42 ... \
    -- --dataset vsfc --ens-targets runs/vsfc/teach/ens_targets_vsfc_f16.npz
# 3. Kiểm tra và tổng hợp
python src_improvement/check_runs.py runs/vsfc/base runs/vsfc/mlm runs/vsfc/ed --dataset vsfc --setups mtl mtl_smart mtl_mlm mtl_mlm_smart mtl_ed --seeds 42 43 44 45 46 47 48 49 50 51
python src_improvement/aggregate_improvement.py runs/vsfc/base runs/vsfc/mlm runs/vsfc/ed --dataset vsfc --out reports/uit_vsfc
```

F1 lớp Neutral, F1 từng lớp và số liệu của teacher (§2–§3) được tính lại từ `metrics.json` và `logits.npz` của từng run.
