# Báo cáo cải tiến: ED (Ensemble Distillation)

Nhóm 5, DPL302m. Cập nhật 2026-11-05.

## 1. Kết luận

**Phương pháp: ED** (setup `mtl_ed`). ED cải thiện so với baseline reproduce ở cả 2 backbone và 2 task, trên cả accuracy lẫn macro-F1. Mọi mức tăng đều có ý nghĩa thống kê (15 seed mỗi bên), kể cả khi so với setup baseline mạnh nhất của từng ô (bảng thứ hai).

| Backbone | Task | `mtl_smart` reported (tác giả) | `mtl_smart` reproduce (nhóm) | **ED** | Δ (so với reproduce) |
|---|---|---|---|---|---|
| PhoBERT | Sentiment | 83.26 | 82.85 ± 0.24 | **83.51 ± 0.24** | **+0.66** |
| PhoBERT | Topic | 79.31 | 79.05 ± 0.17 | **79.65 ± 0.27** | **+0.60** |
| ViSoBERT | Sentiment | 83.58 | 82.71 ± 0.18 | **83.25 ± 0.18** | **+0.54** |
| ViSoBERT | Topic | 79.80 | 79.35 ± 0.16 | **79.73 ± 0.17** | **+0.38** |

Test accuracy %, trung bình ± độ lệch chuẩn qua 15 seed (42–56), p < 0.001 ở cả 4 ô (Welch t-test). Checkpoint được chọn theo tập validation, giống hệt cách tính baseline (xem [baseline_reproduce](../baseline_reproduce/README.md)). Cột reported là số tác giả báo cáo cho setup "2-task & SMART" ở Table 6 của [paper NEU-ESC](../../docs/papers/NEU-ESC.pdf), mỗi số là 1 lần chạy.

### So với baseline reproduce mạnh nhất

Mỗi ô lấy setup baseline có trung bình cao nhất trong 5 setup (single, `mtl`, `mtl_smart`, `mtl_mlm`, `mtl_mlm_smart`) của cùng backbone, chọn riêng cho từng metric. Mọi setup đều có 15 seed (42–56).

| Backbone | Task | Metric | Baseline mạnh nhất | Reproduce (nhóm) | **ED** | Δ | p (Welch) |
|---|---|---|---|---|---|---|---|
| PhoBERT | Sentiment | acc | `mtl_smart` | 82.85 ± 0.24 | **83.51 ± 0.24** | **+0.66** | < 0.001 |
| PhoBERT | Sentiment | macro-F1 | single | 77.24 ± 0.37 | **77.91 ± 0.28** | **+0.67** | < 0.001 |
| PhoBERT | Topic | acc | `mtl_mlm_smart` | 79.09 ± 0.17 | **79.65 ± 0.27** | **+0.56** | < 0.001 |
| PhoBERT | Topic | macro-F1 | `mtl` | 62.23 ± 0.41 | **63.57 ± 0.40** | **+1.34** | < 0.001 |
| ViSoBERT | Sentiment | acc | `mtl_mlm_smart` | 82.82 ± 0.16 | **83.25 ± 0.18** | **+0.43** | < 0.001 |
| ViSoBERT | Sentiment | macro-F1 | single | 76.51 ± 0.46 | **77.22 ± 0.28** | **+0.71** | < 0.001 |
| ViSoBERT | Topic | acc | `mtl_mlm_smart` | 79.55 ± 0.20 | **79.73 ± 0.17** | **+0.18** | 0.011 |
| ViSoBERT | Topic | macro-F1 | `mtl_mlm_smart` | 62.58 ± 0.67 | **63.05 ± 0.26** | **+0.47** | 0.021 |

- ViSoBERT topic là ô có mức tăng nhỏ nhất (+0.18 accuracy), nhưng vẫn có ý nghĩa thống kê.
- **Run thấp nhất** của ED vẫn cao hơn **trung bình** baseline mạnh nhất ở 7/8 ô. Ngoại lệ là accuracy ViSoBERT topic.
- Khi dùng thật vẫn chỉ cần **một model**, cùng kiến trúc và tốc độ suy luận như baseline. Thời gian train một run bằng `mtl` thường, nhanh hơn `mtl_smart` khoảng 2.7 lần.
- Bảng đầy đủ so ED với từng baseline (accuracy và macro-F1): [summary.md](summary.md).

## 2. Phương pháp

ED (*Ensemble Distillation*) xây trên model MTL 2 head của baseline (`mtl`) và giữ nguyên kiến trúc. Chỉ thêm một term vào hàm loss:

L = Σ_task 0.5 · [ CE(y, p) + γ · KL(p_ens ‖ p) ], γ = 1, áp dụng từ epoch 1.

- p là dự đoán của model, y là nhãn thật, p_ens là phân phối mềm của một ensemble đã train sẵn trên tập train.
- Không có SMART, không có MLM. Chọn checkpoint và test bằng chính model.
- Ensemble chính xác hơn hẳn một model; distill giúp một model đơn lẻ học được một phần sức mạnh đó.

**Ensemble teacher được tạo như sau:**
1. Chia tập train thành 5 fold cố định (`FOLD_SEED` = 2026).
2. Mỗi model `mtl` train trên 4 fold và dự đoán fold còn lại. Gọi là dự đoán *out-of-fold*: mỗi câu chỉ được dự đoán bởi model chưa từng thấy câu đó, nên nhãn mềm mang thông tin thật, không phải nhãn đã học thuộc.
3. Làm như vậy cho 2 backbone × 3 seed, tổng cộng 30 model. Mỗi câu train nhận 6 dự đoán, lấy trung bình xác suất.
4. Accuracy của ensemble trên tập train (out-of-fold) là **83.55 / 80.47**, so với khoảng 82.0 / 78.5 của một model đơn lẻ.

Test **không được dùng** ở bất kỳ bước nào để tạo teacher. Val chỉ dùng để chọn checkpoint của từng model fold, như mọi setup khác.

**Liên hệ tài liệu.** Distill từ ensemble vào một model là kỹ thuật đã có (Buciluă et al. 2006; Hinton et al. 2015); dùng dự đoán out-of-fold làm nhãn mềm giống ý tưởng stacking. Đóng góp của nhóm là áp dụng cho bài toán MTL tiếng Việt và đánh giá kỹ (NEU-ESC 15 seed, UIT-VSFC 10 seed, 2 backbone).

## 3. So với chính ensemble teacher

Trung bình xác suất của cả 30 model fold trên tập test (mỗi model train trên 4/5 tập train) đạt **84.14 / 80.46**. Một model fold đơn lẻ đạt trung bình 82.09 / 78.10. Tách theo backbone: ensemble 15 model PhoBERT đạt 83.28 / 79.46, 15 model ViSoBERT đạt 82.81 / 79.34.

| Backbone | Task | `mtl_smart` | ED | Ensemble 30 model | Còn thiếu so với ensemble | Phần khoảng cách đã lấp |
|---|---|---|---|---|---|---|
| PhoBERT | Sentiment | 82.85 | 83.51 | 84.14 | 0.63 | 51% |
| PhoBERT | Topic | 79.05 | 79.65 | 80.46 | 0.81 | 43% |
| ViSoBERT | Sentiment | 82.71 | 83.25 | 84.14 | 0.89 | 38% |
| ViSoBERT | Topic | 79.35 | 79.73 | 80.46 | 0.73 | 34% |

"Phần khoảng cách đã lấp" = (ED − `mtl_smart`) / (ensemble − `mtl_smart`). Một model distill lấy lại khoảng một phần ba đến một nửa mức lợi của ensemble, trong khi chỉ tốn 1/30 chi phí suy luận. Ensemble không được chọn hay chỉnh gì trên test; số trên chỉ để tham chiếu.

**Phương sai dự đoán.** Trên logits test của các run baseline, 44.7% mẫu ở cả sentiment và topic có ít nhất một model đúng và ít nhất một model sai (150 model mỗi task, từ 180 run). Chỉ tính 120 model MTL thì là 42.1% / 41.7%. Số này tính trực tiếp từ `logits.npz`, chưa có script riêng trong repo.

## 4. Các chỉ số khác

### Macro-F1 và weighted-F1 (so với `mtl_smart`)

| Backbone | Task | Accuracy | Macro-F1 | Weighted-F1 |
|---|---|---|---|---|
| PhoBERT | Sentiment | +0.66 | **+1.85** (76.07 → 77.91) | +1.40 |
| PhoBERT | Topic | +0.60 | **+1.62** (61.95 → 63.57) | +1.04 |
| ViSoBERT | Sentiment | +0.54 | **+1.50** (75.73 → 77.22) | +1.17 |
| ViSoBERT | Topic | +0.38 | +0.84 (62.21 → 63.05) | +0.72 |

Macro-F1 tăng nhiều hơn accuracy ở cả 4 ô (p < 0.001), tức ED giúp cả các lớp ít dữ liệu chứ không chỉ lớp lớn.

### F1 từng lớp

Thay đổi F1 (điểm %) so với `mtl_smart`, trung bình 15 seed:

| Lớp | Tỉ lệ (train) | PhoBERT | ViSoBERT |
|---|---|---|---|
| Sentiment: Neutral | 69.1% | +0.19 | +0.19 |
| Sentiment: Positive | 12.6% | +4.54 | +2.67 |
| Sentiment: Negative | 15.7% | +4.73 | +4.68 |
| Sentiment: **Toxic** | 2.5% | **−2.08** | **−1.55** |
| Topic: Spam | 1.2% | +3.37 | −1.29 |
| Topic: News | 2.7% | +2.29 | +0.19 |
| Topic: Jobs & Recruitment | 2.4% | −0.29 | +0.41 |
| Topic: Social Affairs | 2.3% | −1.92 | +3.25 |
| Topic: Help & Share | 2.0% | +3.52 | −1.31 |
| Topic: Club & Events | 2.0% | +3.56 | +0.59 |

- Positive và Negative tăng mạnh (+2.7 đến +4.7) nhờ recall tăng khoảng 8–12 điểm: model bớt dồn câu về lớp Neutral chiếm đa số.
- **Toxic là điểm đánh đổi** ở cả 2 backbone. Với PhoBERT, recall giảm 78.9 → 76.2 và precision 93.0 → 91.8. Với ViSoBERT, recall giữ nguyên (74.9 → 75.0), precision giảm 96.8 → 92.7.
- Nguyên nhân có thể là distillation kéo dự đoán về phân phối mềm của teacher, nơi lớp hiếm vốn có xác suất nhỏ (chưa kiểm chứng).
- Ở topic, các lớp hiếm (dưới 3%) phần lớn tăng; giảm ở vài lớp, khác nhau giữa hai backbone.
- Đã thử logit bias cho Toxic, chọn trên val: F1 Toxic không đổi có ý nghĩa (PhoBERT −0.07, p = 0.754; ViSoBERT +0.33, p = 0.161) và vẫn thấp hơn setup có SMART tốt nhất khi cùng dùng bias (83.21 so với 85.40; 83.26 so với 85.37). Số liệu: `reports/logit_bias/summary.md`.
- Hướng khắc phục chưa thử: giảm γ cho lớp hiếm; kết hợp loss cân bằng lớp.

## 5. Chi phí

| | Thời gian một run (Kaggle T4) |
|---|---|
| `mtl` | 0.65 giờ |
| `mtl_smart` (baseline) | 1.7 giờ |
| ED (`mtl_ed`) | 0.65 giờ |
| Một run fold teacher | 0.52 giờ |

- Train một model ED tốn gần bằng `mtl` thường, nhanh hơn `mtl_smart` khoảng 2.7 lần, vì SMART tốn thêm 2 lượt forward/backward.
- Chi phí thêm nằm ở **teacher**: 30 run × 0.52 giờ ≈ **16 giờ GPU**, chỉ tốn một lần. Mọi run ED của cả 2 backbone dùng chung một file teacher.
- Best epoch trung bình 14.6 (PhoBERT) và 14.3 (ViSoBERT) trên 20, tức model đã hội tụ trước khi hết epoch.
- Khi dùng thật (inference), chi phí bằng baseline: một model, một lượt forward.

## 6. Giới hạn

- **Tính mới:** distillation từ ensemble là kỹ thuật đã có. Đóng góp là áp dụng cho MTL tiếng Việt, kèm đánh giá kỹ (15 seed, so với 5 baseline reproduce, kiểm thêm trên [UIT-VSFC](../uit_vsfc/README.md)).
- **Siêu tham số chưa tinh chỉnh:** γ = 1, teacher 3 seed × 5 fold × 2 backbone.
- **Lớp Toxic giảm F1** (§4).
- **File teacher lưu dạng float16** để nhúng vào kernel Kaggle. Sai số tối đa 0.00024 trên mỗi xác suất.

## 7. File và cách tạo lại

| File | Nội dung |
|---|---|
| `README.md` | Báo cáo này |
| `summary.md`, `per_run.csv` | Bảng tổng hợp do `src_improvement/aggregate_improvement.py` sinh ra |

**Code:** [src_improvement/neu_esc_improvement.py](../../src_improvement/README.md). SHA-256 của runner ghi trong `metrics.json` của từng run:
- ED (30 run): `4f4d7f0d…`, bản trước khi thêm `--dataset vsfc` (không có trong git). 30 run fold teacher: `c89c02e7…` (commit `a6760e6`).
- Runner hiện tại (`37244da6…`) là bản đã gỡ phần code thử nghiệm không dùng. Đã kiểm trên CPU rằng `mtl`, `mtl_ed`, `mtl_smart`, `mtl_mlm` và run fold cho logits, loss và `oof.npz` giống hệt bản `53754f0d` (bản đã chạy các run UIT-VSFC). Chưa ghi nhận kiểm tra logits trực tiếp giữa `4f4d7f0d` và các bản sau.

**Các bước:**

```bash
# 1. 30 run fold teacher (mtl, 5 fold, 3 seed, 2 backbone)
python src_improvement/run_queue.py --setups mtl --folds 5 --seeds 42 43 44 --data-dir DATA --out-dir runs/gap/c
# 2. Gộp thành nhãn mềm
python src_improvement/neu_esc_improvement.py ensemble-targets runs/gap/c/*-f?of5 --out runs/gap/c/ens_targets.npz
#    Bản dùng thật được lưu float16 (ens_targets_f16.npz) để nhúng vào kernel Kaggle, sai số tối đa 0.00024:
python -c "import numpy as np; z = np.load('runs/gap/c/ens_targets.npz'); np.savez_compressed('runs/gap/c/ens_targets_f16.npz', **{k: z[k].astype(np.float16) if k in ('sentiment', 'topic') else z[k] for k in z.files})"
# 3. ED, 15 seed
python src_improvement/run_queue.py --setups mtl_ed --seeds $(seq 42 56) --data-dir DATA --out-dir runs/gap/f -- --ens-targets runs/gap/c/ens_targets_f16.npz
# 4. Kiểm tra và tổng hợp
python src_improvement/check_runs.py runs/gap/f --setups mtl_ed --seeds $(seq 42 56)
python src_improvement/aggregate_improvement.py runs/gap/f runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 runs/gap/a runs/gap/mlm --out reports/improvement
```

Run gốc nằm trong (gitignored, chỉ có trên máy):
- `runs/gap/c`: 30 run fold teacher và file `ens_targets*.npz`.
- `runs/gap/f`: ED seed 42–56 (kernel Kaggle `neu-esc-ed-00` … `07`).
- `runs/s42..s46`, `runs/gap/a`, `runs/gap/mlm`: các run baseline (xem [baseline_reproduce](../baseline_reproduce/README.md)); `runs/gap/mlm` là `mtl_mlm` và `mtl_mlm_smart` seed 47–56.
