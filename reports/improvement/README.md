# Báo cáo cải tiến: CR-SD + D

Nhóm 5, DPL302m. Cập nhật 2026-11-04.

## 1. Kết luận

**Phương án được chốt: CR-SD + D** (setup `crsd_ens`). Phương án này cải thiện so với baseline reproduce ở cả 2 backbone và 2 task. Mọi mức tăng đều có ý nghĩa thống kê (p < 0.001, 15 seed mỗi bên).

| Backbone | Task | Baseline reproduce (`mtl_smart`) | **CR-SD + D** | Δ | Paper (1 lần chạy) |
|---|---|---|---|---|---|
| PhoBERT | Sentiment | 82.85 ± 0.24 | **83.56 ± 0.17** | **+0.71** | 83.26 |
| PhoBERT | Topic | 79.05 ± 0.17 | **80.00 ± 0.18** | **+0.94** | 79.31 |
| ViSoBERT | Sentiment | 82.71 ± 0.18 | **83.51 ± 0.13** | **+0.80** | 83.58 |
| ViSoBERT | Topic | 79.35 ± 0.16 | **79.85 ± 0.16** | **+0.50** | 79.80 |

Test accuracy %, trung bình ± độ lệch chuẩn qua 15 seed (42–56). Checkpoint được chọn theo tập validation, giống hệt cách tính baseline (xem [baseline_reproduce](../baseline_reproduce/README.md)).

- **Run thấp nhất** của CR-SD + D vẫn cao hơn **trung bình** baseline ở cả 4 ô.
- Topic vượt mốc tốt nhất của paper (79.80) ở cả 2 backbone. Sentiment đạt khoảng 83.5, ngang các dòng tốt nhất của paper (83.26–83.66). Lưu ý paper chỉ chạy 1 lần.
- Khi dùng thật vẫn chỉ cần **một model**, cùng kiến trúc và tốc độ suy luận như baseline.

## 2. Phương pháp (giải thích ngắn)

CR-SD + D xây trên model MTL 2 head của baseline (`mtl`) và giữ nguyên kiến trúc. Chỉ cách train thay đổi, gồm ba thành phần.

| Thành phần | Làm gì | Vì sao giúp |
|---|---|---|
| **R-Drop** (α = 1) | Mỗi câu đi qua model 2 lần với dropout khác nhau; phạt khi 2 dự đoán lệch nhau (KL hai chiều) | Buộc model ổn định với nhiễu. Đây là thứ "SMART" của tác giả thực chất đang làm (xem báo cáo baseline §3) |
| **EMA teacher** (μ = 0.999) | Giữ một bản trung bình trượt của trọng số làm teacher; từ epoch 2, student học theo teacher (β = 1). Chọn checkpoint và test bằng trọng số EMA | Trung bình trọng số giảm dao động giữa các bước train |
| **D: ensemble teacher** (γ = 1) | Từ epoch 1, student học theo phân phối mềm của một ensemble đã train sẵn | Ensemble chính xác hơn hẳn một model. Distill giúp một model đơn lẻ học được phần lớn sức mạnh đó |

**Ensemble teacher được tạo như sau:**
1. Chia tập train thành 5 fold cố định.
2. Mỗi model `mtl` train trên 4 fold và dự đoán fold còn lại. Gọi là dự đoán *out-of-fold*: mỗi câu chỉ được dự đoán bởi model chưa từng thấy câu đó.
3. Làm như vậy cho 2 backbone × 3 seed, tổng cộng 30 model. Mỗi câu train nhận 6 dự đoán, lấy trung bình xác suất.
4. Accuracy của ensemble trên tập train (out-of-fold) là **83.55 / 80.47**, so với khoảng 82.0 / 78.5 của một model đơn lẻ.

Val và test **không được dùng** ở bất kỳ bước nào để tạo teacher.

## 3. Mỗi thành phần đóng góp bao nhiêu (ablation)

Test accuracy %, 15 seed mỗi dòng.

| Setup | PhoBERT sentiment | PhoBERT topic | ViSoBERT sentiment | ViSoBERT topic |
|---|---|---|---|---|
| `mtl` (MTL thường) | 82.39 | 78.75 | 82.04 | 78.22 |
| `mtl_smart` (baseline tốt nhất) | 82.85 | 79.05 | 82.71 | 79.35 |
| CR-SD (`selfdistill`) | 83.29 | 79.69 | 82.89 | 79.18 |
| **CR-SD + D** (`crsd_ens`) | **83.56** | **80.00** | **83.51** | **79.85** |
| Phần D thêm vào (so với CR-SD) | +0.26 (p = 0.002) | +0.31 (p < 0.001) | +0.63 (p < 0.001) | +0.67 (p < 0.001) |

- **CR-SD một mình** giúp rõ với PhoBERT (+0.44 / +0.64 so với `mtl_smart`). Với ViSoBERT thì gần như không giúp: sentiment +0.17, topic −0.17.
- **Thêm D** thì cải thiện ở cả 4 ô. ViSoBERT hưởng lợi nhiều nhất, nên D là phần làm phương pháp ổn định trên cả 2 backbone.
- **EMA hay student?**
  - Với CR-SD + D, student (không EMA) gần như bằng EMA: PhoBERT 83.49 / 79.99, ViSoBERT 83.50 / 79.92. Ensemble teacher đã làm thay vai trò ổn định của EMA.
  - Với CR-SD, EMA giúp thêm khoảng 0.0–0.2.

## 4. Các chỉ số khác

### Macro-F1 và weighted-F1 (so với `mtl_smart`)

| Backbone | Task | Accuracy | Macro-F1 | Weighted-F1 |
|---|---|---|---|---|
| PhoBERT | Sentiment | +0.71 | **+1.38** (76.07 → 77.45) | +1.29 |
| PhoBERT | Topic | +0.94 | +1.08 (61.95 → 63.03) | +1.11 |
| ViSoBERT | Sentiment | +0.80 | **+1.34** (75.73 → 77.07) | +1.17 |
| ViSoBERT | Topic | +0.50 | +0.12 (62.21 → 62.33, p = 0.45) | +0.54 |

Macro-F1 tăng nhiều hơn accuracy ở 3/4 ô. Riêng ViSoBERT topic thì macro-F1 gần như đứng yên.

### Điểm đánh đổi: lớp hiếm

F1 của lớp **Toxic** giảm ở cả 2 backbone. Ở topic, các lớp rất hiếm (dưới 3% dữ liệu) giảm chủ yếu với ViSoBERT; với PhoBERT phần lớn vẫn tăng. Thay đổi F1 (điểm %) so với `mtl_smart`:

| Lớp | Tỉ lệ | PhoBERT | ViSoBERT |
|---|---|---|---|
| Sentiment: **Toxic** | 2.6% | **−2.81** | −1.17 |
| Topic: Spam | 1.2% | +1.91 | −2.29 |
| Topic: News | 2.7% | +0.86 | −1.58 |
| Topic: Jobs & Recruitment | 2.5% | −0.47 | −0.38 |
| Topic: Social Affairs | 2.3% | −1.37 | +2.67 |
| Topic: Help & Share | 2.0% | +0.64 | −2.81 |
| Topic: Club & Events | 2.0% | +2.85 | +0.89 |

- Toxic giảm chủ yếu do **recall** giảm. PhoBERT bắt được 74.1% câu toxic, trước là 78.9%; precision giữ nguyên (93.0 → 93.1). ViSoBERT giảm nhẹ cả hai: recall 74.9 → 73.9, precision 96.8 → 95.4.
- Nguyên nhân có thể là distillation kéo dự đoán về phân phối mềm của teacher, nơi lớp hiếm vốn có xác suất nhỏ. Đây là hiện tượng đã được biết ở knowledge distillation trên dữ liệu lệch lớp.
- Hướng khắc phục chưa thử:
  - chỉnh ngưỡng (logit bias) cho lớp hiếm, chọn trên val;
  - giảm γ cho lớp hiếm;
  - kết hợp với loss cân bằng lớp.

## 5. Chi phí

| | Thời gian một run (Kaggle T4) |
|---|---|
| `mtl` | 0.65 giờ |
| `mtl_smart` (baseline) | 1.7 giờ |
| CR-SD / CR-SD + D | 1.3 giờ |
| Một run fold teacher | 0.5 giờ |

- Train một model CR-SD + D **nhanh hơn** baseline `mtl_smart`, vì SMART tốn thêm 2 lượt forward/backward.
- Chi phí thêm nằm ở **teacher**: 30 run × 0.5 giờ ≈ **16 giờ GPU**, chỉ tốn một lần. Mọi run CR-SD + D của cả 2 backbone đều dùng chung một file teacher.
- Khi dùng thật (inference), chi phí bằng baseline: một model, một lượt forward.

## 6. Giới hạn

- **Tính mới:** R-Drop, EMA teacher và distillation từ ensemble đều là kỹ thuật đã có. Đóng góp là cách kết hợp và áp dụng cho bài toán MTL tiếng Việt, kèm đánh giá kỹ (15 seed, ablation).
- **Chỉ một dataset** (NEU-ESC). Chưa kiểm trên dataset khác.
- **Siêu tham số chưa tinh chỉnh:** α = β = γ = 1, μ = 0.999. Best epoch trung bình khoảng 19.7/20, nên model có thể vẫn đang tăng khi kết thúc; train lâu hơn có thể giúp thêm.
- **Chưa đo accuracy của chính ensemble trên test**, nên chưa biết model distill giữ được bao nhiêu phần trăm sức mạnh của ensemble.
- **Chưa có ablation "chỉ D"** (`mtl` + ensemble teacher, không R-Drop và EMA).
- **File teacher lưu dạng float16** để nhúng vào kernel Kaggle. Sai số tối đa 0.00024 trên mỗi xác suất.

## 7. File và cách tạo lại

| File | Nội dung |
|---|---|
| `README.md` | Báo cáo này |
| `summary.md`, `per_run.csv` | Bảng tổng hợp do `src_improvement/aggregate_improvement.py` sinh ra |

**Code:** [src_improvement/neu_esc_improvement.py](../../src_improvement/README.md). SHA-256 của runner ghi trong `metrics.json` của từng run:
- CR-SD + D (30 run): `e031695b…`, đúng file hiện tại (commit `220d512`).
- CR-SD seed 44–56 và 30 run fold teacher: `c89c02e7…` (commit `a6760e6`). Bản này chỉ khác bản hiện tại ở lệnh `ensemble-targets` (cách khóa SHA của train CSV); phần train giống hệt.
- CR-SD seed 42–43: `b410dc12…`, bản runner cũ còn chứa code ablation giai thừa, không có trong git. `config.json` ghi cùng α, β, μ và epoch bắt đầu distill, với các tùy chọn giai thừa ở mặc định (head `sep`, tổng loss thường, CE), tức tương đương `mtl`.

**Các bước:**

```bash
# 1. 30 run fold teacher (mtl, 5 fold, 3 seed, 2 backbone)
python src_improvement/run_queue.py --setups mtl --folds 5 --seeds 42 43 44 --data-dir DATA --out-dir runs/gap/c
# 2. Gộp thành nhãn mềm
python src_improvement/neu_esc_improvement.py ensemble-targets runs/gap/c/*-f?of5 --out runs/gap/c/ens_targets.npz
#    Bản dùng thật được lưu float16 (ens_targets_f16.npz) để nhúng vào kernel Kaggle, sai số tối đa 0.00024:
python -c "import numpy as np; z = np.load('runs/gap/c/ens_targets.npz'); np.savez_compressed('runs/gap/c/ens_targets_f16.npz', **{k: z[k].astype(np.float16) if k in ('sentiment', 'topic') else z[k] for k in z.files})"
# 3. CR-SD + D, 15 seed (các run gốc đọc bản float16, đặt tên ens_targets.npz trong kernel)
python src_improvement/run_queue.py --setups crsd_ens --seeds $(seq 42 56) --data-dir DATA --out-dir runs/gap/d -- --ens-targets runs/gap/c/ens_targets.npz
# 4. Tổng hợp
python src_improvement/aggregate_improvement.py runs/improvement runs/gap/c runs/gap/d runs/gap/e runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 runs/gap/a --out reports/improvement
```

Run gốc nằm trong (gitignored, chỉ có trên máy):
- `runs/improvement/s42`, `s43`: CR-SD seed 42–43.
- `runs/gap/c`: CR-SD seed 44–56, 30 run fold teacher và file `ens_targets*.npz`.
- `runs/gap/d`, `runs/gap/e`: CR-SD + D seed 42–46 và 47–56.
