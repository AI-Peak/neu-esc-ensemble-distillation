#Hướng dẫn
Viết vào đây các ý chính là đc. Dạng liệt kê thành từng gạch đầu dòng cũng đc.
Có table kết quả nào được điền ở đâu thì viết nguyên table đó vào đây luôn, alabtion cũng vậy. Để y xi nguyên đúc giống theo ý định để trong paper
Mục đích: để tui hiểu và nhìn ra được tổng quan paper (thứ tự trong paper viết như nào thì ở đây viết vậy nhưng viết gắn ngọn nhất có thể và dễ hiểu đc rồi)
Viết tiếng việt

---

# Bản nháp paper (dàn ý + toàn bộ bảng)

Số liệu lấy từ [baseline_reproduce](baseline_reproduce/README.md), [improvement](improvement/README.md), [uit_vsfc](uit_vsfc/README.md), [logit_bias](logit_bias/summary.md). Mọi số là test accuracy / macro-F1 (%), trung bình ± std qua nhiều seed, checkpoint chọn theo validation.

**Tên đề xuất:** *Reproducing NEU-ESC under a Multi-Seed Protocol and Improving It with Out-of-Fold Ensemble Distillation*

---

## 0. Abstract (ý chính)

- NEU-ESC là bộ dữ liệu tiếng Việt (bình luận sinh viên), 2 task: sentiment (4 lớp) và topic (10 lớp). Paper gốc báo cáo accuracy cao nhất ở các setup có SMART (sentiment: MTL + MLM + SMART; topic: MTL + SMART), mỗi dòng chỉ **1 lần chạy**.
- Nhóm **reproduce lại** theo code công khai của tác giả, **15 seed** mỗi dòng. Kết quả lệch paper trung bình 0.42 điểm, nhỏ hơn biên độ trung bình giữa các seed (1.40 điểm); riêng 4/20 ô không có seed nào đạt số của paper.
- Đề xuất **ED (Ensemble Distillation)**: train 30 model theo fold, lấy dự đoán out-of-fold làm nhãn mềm, distill vào **một** model MTL. Không đổi kiến trúc, không tăng chi phí suy luận.
- Ablation teacher trên NEU-ESC: out-of-fold cao hơn teacher in-sample có ý nghĩa về accuracy (+0.33 đến +0.70), nhưng không khác có ý nghĩa về macro-F1.
- Trên NEU-ESC, ED **thắng cả 5 baseline reproduce** ở cả 2 backbone, 2 task, trên cả accuracy và macro-F1 (p Holm ≤ 0.022). Ví dụ PhoBERT: 83.51 / 79.65 so với 82.85 / 79.05 của MTL + SMART.
- Kiểm tra trên **UIT-VSFC**: ED tăng có ý nghĩa ở accuracy topic, nhưng sau hiệu chỉnh Holm macro-F1 topic của PhoBERT không còn có ý nghĩa. Ở sentiment, ED không khác có ý nghĩa so với baseline mạnh nhất.

## 1. Introduction

- Bối cảnh: phân loại phản hồi sinh viên tiếng Việt; MTL dùng chung encoder cho 2 task.
- Vấn đề 1: kết quả paper gốc chỉ có 1 lần chạy, không có độ lệch chuẩn → khó biết cải tiến là thật hay do may.
- Vấn đề 2: phân tích của nhóm cho thấy dự đoán có **phương sai** lớn giữa các lần chạy. Ensemble nhiều model cao hơn một model khoảng +2 điểm, nhưng tốn chi phí suy luận.
- Ý tưởng: dồn sức mạnh ensemble vào một model bằng distillation.
- **Đóng góp:**
  1. Reproduce đầy đủ NEU-ESC (10 dòng Table 6 × 15 seed) với giao thức nhiều seed.
  2. Phương pháp ED: distill từ ensemble out-of-fold vào một model MTL, cải thiện có ý nghĩa thống kê so với mọi baseline.
  3. Kiểm tra tổng quát hoá trên UIT-VSFC với cùng siêu tham số.

## 2. Related Work (gạch ý, cần kiểm lại trích dẫn trước khi nộp)

- **Dữ liệu tiếng Việt:** NEU-ESC (arXiv 2506.23524); UIT-VSFC (Nguyen et al., KSE 2018).
- **Backbone:** PhoBERT (Nguyen & Nguyen, 2020); ViSoBERT (Nguyen et al., 2023).
- **Multi-task learning:** Caruana (1997); chia sẻ encoder + nhiều head.
- **Regularization:** SMART (Jiang et al., 2020) là tên paper gốc dùng. Code công khai của tác giả cộng nhiễu vào token ID rồi ép kiểu `.long()`, nên thực chất là đổi token ngẫu nhiên kèm consistency regularization. Nhóm giữ đúng code này để reproduce.
- **Knowledge distillation:** model compression (Buciluă et al., 2006); KD với nhãn mềm (Hinton et al., 2015); born-again networks (Furlanello et al., 2018).
- **Out-of-fold prediction:** ý tưởng của stacking / cross-validation, dùng để nhãn mềm không bị "học thuộc".
- Khác biệt của nhóm: áp dụng cho MTL tiếng Việt, đánh giá nhiều seed, so với baseline đã reproduce chứ không chép số paper.

## 3. Dataset và giao thức đánh giá

**NEU-ESC:** train 23,048 / val 3,305 / test 6,613 câu, dùng đúng split của tác giả.

| Task | Lớp (tỉ lệ trên train) |
|---|---|
| Sentiment (4) | Neutral 69.1%, Positive 12.6%, Negative 15.7%, Toxic 2.5% |
| Topic (10) | Other 43.7%, Academic 31.9%, Service 7.1%, Personal Affairs 4.5%, News 2.7%, Jobs & Recruitment 2.4%, Social Affairs 2.3%, Help & Share 2.0%, Club & Events 2.0%, Spam 1.2% |

**UIT-VSFC** (chỉ dùng ở §7): train 11,426 / val 1,583 / test 3,166, split chính thức. Sentiment 3 lớp (Neutral chỉ ~5%), topic 4 lớp.

**Giao thức (áp dụng cho mọi bảng):**
- Chọn checkpoint theo **mean val macro-F1 của 2 task** (single-task: val macro-F1 của task đó); test đúng **1 lần**.
- Báo **trung bình ± std** qua 15 seed (42–56) trên NEU-ESC, 10 seed (42–51) trên UIT-VSFC.
- So sánh bằng **Welch t-test** (riêng Bảng 6 dùng t-test ghép cặp theo seed).
- Hiệu chỉnh đa so sánh bằng **Holm** ở α = 0.05, riêng từng dataset, trên mọi cặp ED − baseline về accuracy và macro-F1: 40 phép so sánh trên NEU-ESC, 32 trên UIT-VSFC. "Có ý nghĩa" ở Bảng 4 và Bảng 5 hiểu theo p đã hiệu chỉnh này.
- Bảng 3b hiệu chỉnh Holm riêng trên 8 phép so sánh của nó.
- Không chọn seed, không nhìn test để chọn epoch.

## 4. Reproduce baseline NEU-ESC

**Thiết lập:** PhoBERT-base-v2 và ViSoBERT; head [CLS] → Linear → SiLU → LayerNorm → lớp; lr 2e-5, batch 128, max length 128, AdamW, LinearLR; MTL 20 epoch, loss 0.5/0.5. Theo đúng code tác giả (commit b5637cc0). Single-task dùng `AutoModelForSequenceClassification`, 15 epoch, early stopping patience 4. Sai khác có chủ đích: fp16 (T4) thay fp32, chia micro-batch, chọn checkpoint MTL theo val (tác giả lưu mọi epoch và không ghi tiêu chí chọn). Riêng các dòng MLM: tắt SMART để có dòng MTL + MLM (trainer gốc luôn bật SMART), và giới hạn token ngẫu nhiên trong từ vựng ViSoBERT (code gốc báo lỗi với backbone này).

**Bảng 1 – Reproduce Table 6 (test accuracy, 15 seed):**

| Backbone | Setup | Sentiment | Paper | Δ | Topic | Paper | Δ |
|---|---|---|---|---|---|---|---|
| PhoBERT | Single-task | 82.27 ± 0.40 | 81.75 | +0.52 | 78.16 ± 0.58 | 78.65 | −0.49 |
| PhoBERT | MTL | 82.39 ± 0.71 | 82.88 | −0.49 | 78.75 ± 0.36 | 79.25 | −0.50 |
| PhoBERT | MTL + SMART | **82.85 ± 0.24** | 83.26 | −0.41 | 79.05 ± 0.17 | 79.31 | −0.26 |
| PhoBERT | MTL + MLM | 82.25 ± 0.53 | 82.67 | −0.42 | 78.46 ± 0.44 | 78.48 | −0.02 |
| PhoBERT | MTL + MLM + SMART | 82.83 ± 0.16 | 83.66 | −0.83 | 79.09 ± 0.17 | 79.49 | −0.40 |
| ViSoBERT | Single-task | 82.30 ± 0.64 | 82.78 | −0.48 | 78.11 ± 0.42 | 77.94 | +0.17 |
| ViSoBERT | MTL | 82.04 ± 0.43 | 82.63 | −0.59 | 78.22 ± 0.55 | 78.56 | −0.34 |
| ViSoBERT | MTL + SMART | 82.71 ± 0.18 | 83.58 | −0.87 | 79.35 ± 0.16 | 79.80 | −0.45 |
| ViSoBERT | MTL + MLM | 81.83 ± 0.68 | 82.23 | −0.40 | 78.18 ± 0.41 | 78.38 | −0.20 |
| ViSoBERT | MTL + MLM + SMART | 82.82 ± 0.16 | 83.12 | −0.30 | **79.55 ± 0.20** | 79.25 | +0.30 |

- Lệch trung bình |Δ| = 0.42, nhỏ hơn biên độ trung bình giữa các seed (1.40 điểm; từng ô từ 0.48 đến 2.51). Paper là 1 lần chạy nên thường cao hơn trung bình: 17/20 ô của nhóm thấp hơn paper.
- 16/20 ô có ít nhất một seed đạt số của paper. 4 ô còn lại đạt 0/15: ViSoBERT MTL + SMART (83.58, 79.80) và PhoBERT MTL + MLM + SMART (83.66, 79.49).
- Hai ô sentiment 83.58 và 83.66 không giải thích được bằng may rủi hay cách chọn epoch: lấy epoch có test cao nhất rồi lấy seed tốt nhất cũng chỉ đạt 83.09 và 83.25, đổi sang fp32 cũng không giúp. Từ phần đã công bố, nhóm không xác định được nguyên nhân.
- Xu hướng giống paper **về accuracy**: SMART tăng so với MTL ở cả 4 ô. Macro-F1 thì không giống: SMART giảm ở 3/4 ô (chỉ PhoBERT sentiment có ý nghĩa: −0.79, p = 0.001, paper +1.53) và chỉ tăng ở ViSoBERT topic (+0.52, paper +1.47).

## 5. Phương pháp: ED (Ensemble Distillation)

**Động lực:** đo trên 150 model baseline mỗi task (180 run), 44.7% mẫu test ở cả 2 task có model đúng có model sai tùy seed/cấu hình; chỉ tính 120 model MTL thì là 42.1% / 41.7% → phương sai lớn. Trung bình 30 model đạt 84.14 / 80.46 trên test, so với 82.09 / 78.10 của một model fold.

**Bước 1 – Teacher out-of-fold:**
- Chia train thành 5 fold cố định (seed 2026).
- Train model `mtl` trên 4 fold, dự đoán fold còn lại → mỗi câu chỉ được dự đoán bởi model chưa thấy nó.
- 2 backbone × 3 seed × 5 fold = **30 model**; mỗi câu train có 6 dự đoán, lấy trung bình xác suất → p_ens.
- Accuracy out-of-fold của teacher trên train: 83.55 / 80.47 (một model ~82.0 / 78.5).
- Test không dùng ở bước nào. Val chỉ dùng để chọn checkpoint của từng model fold, như mọi setup khác.

**Bước 2 – Distill vào student:**
- Student = model `mtl` của baseline (không SMART, không MLM, giữ nguyên kiến trúc).
- Loss: **L = Σ_task 0.5 · [ CE(y, p) + γ · KL(p_ens ‖ p) ]**, γ = 1, từ epoch 1.
- Suy luận: một model, một lượt forward, chi phí như baseline.

**Hình 1 – Kiến trúc ED:** [docs/figures/ed_architecture.drawio](../docs/figures/ed_architecture.drawio) (mở bằng draw.io).

## 6. Kết quả trên NEU-ESC

**Bảng 2 – Kết quả chính (test accuracy):** so tại hai mốc cao nhất tác giả báo cáo trong Table 6, cùng backbone và cùng setup.

| Task | Backbone | Setup của mốc | Reported (tác giả, 1 lần chạy) | Reproduce baseline (15 seed) | **ED** (15 seed) | Δ ED − reproduce (p) |
|---|---|---|---|---|---|---|
| Sentiment | PhoBERT | MTL + MLM + SMART | 83.66 | 82.83 ± 0.16 | **83.51 ± 0.24** | **+0.68** (< 0.001) |
| Topic | ViSoBERT | MTL + SMART | 79.80 | 79.35 ± 0.16 | **79.73 ± 0.17** | **+0.38** (< 0.001) |

- ED tăng có ý nghĩa so với baseline reproduce tại cả hai mốc.
- So với số reported, ED vẫn thấp hơn một chút (−0.15 và −0.07). Baseline không có seed nào đạt hai mốc này (0/15); trung bình 15 seed của chính cấu hình đó thấp hơn 0.83 và 0.45 (§4).
- Bảng này so theo mốc reported nên ở topic, +0.38 là so với MTL + SMART. So với baseline reproduce mạnh nhất của ViSoBERT topic (MTL + MLM + SMART, 79.55), ED chỉ tăng +0.18 (p = 0.011, xem Bảng 4).

**Bảng 3 – Ablation: bỏ ED (= `mtl`) và so với chính teacher (test accuracy):**

| Setup | PhoBERT sent | PhoBERT topic | ViSoBERT sent | ViSoBERT topic |
|---|---|---|---|---|
| `mtl` (ED bỏ term KL) | 82.39 | 78.75 | 82.04 | 78.22 |
| `mtl_smart` (baseline paper) | 82.85 | 79.05 | 82.71 | 79.35 |
| **ED** | **83.51** | **79.65** | **83.25** | **79.73** |
| Phần ED thêm vào so với `mtl` | +1.12 | +0.90 | +1.21 | +1.51 |
| Teacher: ensemble 15 model cùng backbone | 83.28 | 79.46 | 82.81 | 79.34 |
| Teacher: ensemble 30 model (2 backbone) | 84.14 | 80.46 | 84.14 | 80.46 |
| Phần khoảng cách `mtl_smart` → ensemble 30 đã lấp | 51% | 43% | 38% | 34% |

- Chỉ thêm term KL vào `mtl` đã tăng +0.9 đến +1.5 (p < 0.001), lớn hơn mức SMART mang lại.
- Một model ED **vượt cả ensemble 15 model cùng backbone**, và lấy lại 1/3 đến 1/2 mức lợi của ensemble 30 model, với 1/30 chi phí suy luận.

**Bảng 3b – Ablation teacher: out-of-fold so với in-sample (test, NEU-ESC, 15 seed):** ED in-sample dùng teacher gồm 6 model `mtl` train trên toàn bộ train (2 backbone × 3 seed), dự đoán lại chính các câu đã học. Mỗi câu vẫn có 6 dự đoán, student và loss giữ nguyên. Accuracy của teacher trên train: 97.83 / 96.03, so với 83.55 / 80.47 của teacher out-of-fold. p Holm tính trên 8 phép so sánh của bảng này.

| Backbone | Task | Chỉ số | `mtl` | ED in-sample | ED out-of-fold | Δ OOF − in-sample | p Holm |
|---|---|---|---:|---:|---:|---:|---:|
| PhoBERT | Sentiment | Accuracy | 82.39 | 82.82 ± 0.37 | 83.51 ± 0.24 | **+0.70** | **< 0.001** |
| PhoBERT | Sentiment | Macro-F1 | 76.86 | 77.58 ± 0.40 | 77.91 ± 0.28 | +0.33 | 0.061 |
| PhoBERT | Topic | Accuracy | 78.75 | 79.09 ± 0.28 | 79.65 ± 0.27 | **+0.56** | **< 0.001** |
| PhoBERT | Topic | Macro-F1 | 62.23 | 63.16 ± 0.48 | 63.57 ± 0.40 | +0.41 | 0.061 |
| ViSoBERT | Sentiment | Accuracy | 82.04 | 82.93 ± 0.22 | 83.25 ± 0.18 | **+0.33** | **< 0.001** |
| ViSoBERT | Sentiment | Macro-F1 | 76.08 | 77.11 ± 0.40 | 77.22 ± 0.28 | +0.12 | 0.726 |
| ViSoBERT | Topic | Accuracy | 78.22 | 79.25 ± 0.22 | 79.73 ± 0.17 | **+0.48** | **< 0.001** |
| ViSoBERT | Topic | Macro-F1 | 61.70 | 63.07 ± 0.42 | 63.05 ± 0.26 | −0.02 | 0.876 |

- **Accuracy:** out-of-fold cao hơn in-sample có ý nghĩa ở cả 4 ô (+0.33 đến +0.70). Đây là bằng chứng out-of-fold có tác dụng.
- **Macro-F1:** không khác có ý nghĩa ở cả 4 ô sau Holm.
- **Phần còn lại không nhờ out-of-fold:** ED in-sample vẫn cao hơn `mtl` ở 7/8 ô (p gốc chưa hiệu chỉnh ≤ 0.008; riêng accuracy sentiment PhoBERT p = 0.052). In-sample đã đạt 38–73% mức tăng accuracy và 69–101% mức tăng macro-F1 mà ED out-of-fold có so với `mtl`. Vì vậy distill tự nó đã giúp, out-of-fold thêm một phần accuracy.
- **Chi phí:** teacher in-sample chỉ cần 3.9 giờ GPU so với ~16 giờ. Nếu ưu tiên macro-F1 hoặc thời gian train, đây là phương án rẻ hơn đáng cân nhắc.
- **Khác biệt ngoài out-of-fold:** model của teacher in-sample học trên 100% train, model fold học trên 80%. Thí nghiệm này chạy sau, với runner có thêm cờ lưu dự đoán train (SHA `245fc620`, ED gốc `4f4d7f0d`).

**Bảng 4 – Toàn bộ setup trên NEU-ESC: accuracy, macro-F1, weighted-F1 và F1 lớp Toxic (test, 15 seed):**

| Backbone | Setup | Sent acc | Sent macro-F1 | Sent weighted-F1 | F1 Toxic | Topic acc | Topic macro-F1 | Topic weighted-F1 |
|---|---|---|---|---|---|---|---|---|
| PhoBERT | Single-task | 82.27 ± 0.40 | 77.24 ± 0.37 | 82.27 ± 0.29 | 85.32 | 78.16 ± 0.58 | 61.49 ± 0.58 | 77.97 ± 0.44 |
| PhoBERT | MTL | 82.39 ± 0.71 | 76.86 ± 0.63 | 82.39 ± 0.53 | 82.86 | 78.75 ± 0.36 | 62.23 ± 0.41 | 78.38 ± 0.24 |
| PhoBERT | MTL + SMART | 82.85 ± 0.24 | 76.07 ± 0.57 | 82.02 ± 0.32 | **85.35** | 79.05 ± 0.17 | 61.95 ± 0.60 | 78.23 ± 0.19 |
| PhoBERT | MTL + MLM | 82.25 ± 0.53 | 76.85 ± 0.41 | 82.32 ± 0.37 | 82.79 | 78.46 ± 0.44 | 61.92 ± 0.54 | 78.18 ± 0.32 |
| PhoBERT | MTL + MLM + SMART | 82.83 ± 0.16 | 76.23 ± 0.54 | 82.08 ± 0.29 | **85.35** | 79.09 ± 0.17 | 62.11 ± 0.60 | 78.24 ± 0.21 |
| PhoBERT | **ED** | **83.51 ± 0.24** | **77.91 ± 0.28** | **83.42 ± 0.18** | 83.28 | **79.65 ± 0.27** | **63.57 ± 0.40** | **79.27 ± 0.24** |
| ViSoBERT | Single-task | 82.30 ± 0.64 | 76.51 ± 0.46 | 82.18 ± 0.44 | 83.39 | 78.11 ± 0.42 | 61.32 ± 0.41 | 77.79 ± 0.29 |
| ViSoBERT | MTL | 82.04 ± 0.43 | 76.08 ± 0.76 | 81.93 ± 0.43 | 82.60 | 78.22 ± 0.55 | 61.70 ± 0.60 | 77.95 ± 0.44 |
| ViSoBERT | MTL + SMART | 82.71 ± 0.18 | 75.73 ± 0.43 | 81.88 ± 0.28 | 84.49 | 79.35 ± 0.16 | 62.21 ± 0.41 | 78.49 ± 0.21 |
| ViSoBERT | MTL + MLM | 81.83 ± 0.68 | 76.00 ± 0.47 | 81.79 ± 0.47 | 82.53 | 78.18 ± 0.41 | 61.56 ± 0.47 | 77.89 ± 0.33 |
| ViSoBERT | MTL + MLM + SMART | 82.82 ± 0.16 | 76.05 ± 0.42 | 82.07 ± 0.26 | **84.68** | 79.55 ± 0.20 | 62.58 ± 0.67 | 78.76 ± 0.28 |
| ViSoBERT | **ED** | **83.25 ± 0.18** | **77.22 ± 0.28** | **83.05 ± 0.15** | 82.94 | **79.73 ± 0.17** | **63.05 ± 0.26** | **79.21 ± 0.14** |

- ED cao nhất ở cả 6 cột accuracy / macro-F1 / weighted-F1, trên cả 2 backbone. Macro-F1 tăng nhiều hơn accuracy → nhìn chung các lớp nhỏ cũng được lợi, trừ F1 Toxic so với single-task và các setup có SMART (xem §9).
- So với baseline tốt nhất của từng cột (Welch t-test, p gốc), ED tăng có ý nghĩa ở cả 8 ô accuracy / macro-F1. Sau hiệu chỉnh Holm, cả 40 phép so sánh trên NEU-ESC vẫn có ý nghĩa (p Holm lớn nhất 0.022, ở hai ô topic ViSoBERT so với MTL + MLM + SMART):
  - PhoBERT: sent acc +0.66 (vs MTL + SMART), sent macro-F1 +0.67 (vs single), topic acc +0.56 (vs MTL + MLM + SMART), topic macro-F1 +1.34 (vs MTL); p < 0.001 cả 4.
  - ViSoBERT: sent acc +0.43 (vs MTL + MLM + SMART, p < 0.001), sent macro-F1 +0.71 (vs single, p < 0.001), topic acc +0.18 (vs MTL + MLM + SMART, p = 0.011), topic macro-F1 +0.47 (vs MTL + MLM + SMART, p = 0.021).
  - Run thấp nhất của ED vẫn cao hơn trung bình baseline tốt nhất ở 7/8 ô (trừ topic acc ViSoBERT, ô tăng ít nhất).
- **F1 Toxic (2.5% dữ liệu) là điểm đánh đổi:** ED thấp hơn các setup có SMART (83.28 so với 85.35; 82.94 so với 84.68) và single-task (85.32; 83.39), nhưng cao hơn MTL và MTL + MLM. Ghi vào phần hạn chế.
- F1 đầy đủ từng lớp (14 lớp × 6 setup) để ở phụ lục.

## 7. Tổng quát hoá: UIT-VSFC

Cùng siêu tham số, cùng pipeline, không tinh chỉnh. Teacher dựng lại trên train UIT-VSFC theo đúng cách §5. 10 seed. Khác NEU-ESC ở hai điểm: PhoBERT đọc bản tách từ bằng underthesea 9.5.0, và không chạy single-task nên chỉ có 4 baseline.

**Bảng 5 – Kết quả UIT-VSFC (test):**

| Backbone | Setup | Sent acc | Sent macro-F1 | F1 Neutral | Topic acc | Topic macro-F1 |
|---|---|---:|---:|---:|---:|---:|
| PhoBERT | `mtl` | 93.77 ± 0.16 | 82.11 ± 0.82 | 55.3 | 89.05 ± 0.70 | 80.01 ± 0.62 |
| PhoBERT | `mtl_smart` | 92.44 ± 0.20 | 76.86 ± 0.99 | 41.9 | 88.96 ± 0.22 | 78.78 ± 0.72 |
| PhoBERT | `mtl_mlm` | 93.84 ± 0.13 | **82.59 ± 0.50** | **56.6** | 89.10 ± 0.40 | 79.86 ± 0.71 |
| PhoBERT | `mtl_mlm_smart` | 92.54 ± 0.21 | 77.14 ± 0.95 | 42.5 | 89.11 ± 0.23 | 79.13 ± 0.46 |
| PhoBERT | **ED** | **93.88 ± 0.12** | 82.02 ± 0.51 | 54.9 | **89.71 ± 0.11** | **80.70 ± 0.58** |
| ViSoBERT | `mtl` | 92.71 ± 0.20 | 80.47 ± 1.17 | 52.2 | 88.77 ± 0.48 | 79.47 ± 0.43 |
| ViSoBERT | `mtl_smart` | 92.36 ± 0.24 | 78.11 ± 0.64 | 46.0 | 88.91 ± 0.19 | 79.52 ± 0.58 |
| ViSoBERT | `mtl_mlm` | 92.80 ± 0.29 | **80.71 ± 0.87** | **52.8** | 88.54 ± 0.48 | 79.27 ± 0.69 |
| ViSoBERT | `mtl_mlm_smart` | 92.42 ± 0.24 | 78.32 ± 0.66 | 46.5 | 88.85 ± 0.25 | 79.43 ± 0.65 |
| ViSoBERT | **ED** | **93.08 ± 0.10** | 80.34 ± 0.49 | 51.3 | **89.32 ± 0.16** | **80.42 ± 0.34** |

- Topic: ED cao nhất ở cả 2 backbone, cả accuracy và macro-F1. So với baseline tốt nhất từng cột, p gốc ≤ 0.019; sau Holm vẫn có ý nghĩa ở accuracy cả 2 backbone (p Holm ≤ 0.001) và macro-F1 ViSoBERT (0.011), nhưng macro-F1 PhoBERT thì không (+0.69, p Holm = 0.131). Lý do: ensemble 30 model đạt 90.05 trên test, cao hơn `mtl` (89.05 / 88.77) khoảng 1 điểm, nên teacher còn cái để dạy; ED lấp 66% (PhoBERT) và 43% (ViSoBERT) khoảng cách này.
- Sentiment, accuracy: ED cao nhất. PhoBERT `mtl` (93.77) đã ngang ensemble 30 (93.75) nên teacher không còn gì để dạy, ED chỉ ngang `mtl_mlm` (+0.03, p = 0.54). ViSoBERT `mtl` (92.71) còn cách ensemble 1.04 điểm, ED hơn `mtl` +0.37 (p < 0.001) và hơn `mtl_mlm` +0.28 (p = 0.013, nhưng p Holm = 0.121 nên không còn có ý nghĩa).
- Sentiment, macro-F1: `mtl_mlm` cao nhất, ED thấp hơn −0.57 (PhoBERT, p = 0.022, p Holm = 0.135) và −0.37 (ViSoBERT, p = 0.26, p Holm = 1), nên sau hiệu chỉnh không còn khác có ý nghĩa. Phần chênh này đi cùng lớp Neutral (~5%; F1 Neutral −1.76, p gốc = 0.016 và −1.48, p gốc = 0.13). So với `mtl`, ED ngang (−0.09 và −0.13, p > 0.7). Riêng ViSoBERT, ensemble 30 có macro-F1 81.81, cao hơn `mtl` 1.34 điểm, nhưng ED không tăng.
- So với `mtl_smart` (baseline chính của paper): ED thắng ở cả 4 ô, cả accuracy lẫn macro-F1.
- SMART **làm hại** trên UIT-VSFC (PhoBERT sentiment −1.3 acc, −5 macro-F1 so với `mtl`), còn ED thì không.
- Mốc ngoài: bài gốc UIT-VSFC (MaxEnt) F1 87.94 / 84.03, chỉ là mốc sàn (khác metric, khác mô hình).

**Kết luận phần này:** về accuracy, mức tăng của ED đi cùng khoảng cách giữa teacher và một model đơn lẻ. Khoảng cách lớn (NEU-ESC, topic UIT, sentiment UIT với ViSoBERT) → tăng; gần bằng 0 (sentiment UIT với PhoBERT) → không tăng. Macro-F1 sentiment không theo quy luật này: ED ngang `mtl` và thấp hơn `mtl_mlm` trên cả 2 backbone (không có ý nghĩa sau Holm).

## 8. Discussion

- **Tính mới:** distill từ ensemble là kỹ thuật đã có; đóng góp là áp dụng và đánh giá kỹ (NEU-ESC: 15 seed, 5 baseline reproduce; UIT-VSFC: 10 seed, 4 baseline).
- **Khi nào ED có lợi:** về accuracy, mức tăng đi cùng khoảng cách giữa teacher và một model đơn lẻ. Khoảng cách lớn (NEU-ESC, topic UIT, sentiment UIT với ViSoBERT) thì tăng; gần bằng 0 (sentiment UIT với PhoBERT) thì không tăng. Đây là quan sát trên các ô đã chạy, chưa kiểm định riêng, và không áp dụng cho macro-F1 sentiment trên UIT-VSFC.
- **Khi nào nên dùng:** ED hợp khi cần điểm tổng cao mà vẫn suy luận bằng một model. Trên NEU-ESC, nếu F1 Toxic là mục tiêu chính thì single-task và các setup có SMART vẫn cao hơn; trên UIT-VSFC, logit bias kéo được F1 Neutral lên (xem §9).

## 9. Hạn chế

- **Lớp hiếm:** F1 Toxic (NEU) của ED thấp hơn single-task và các setup có SMART, dù vẫn cao hơn MTL và MTL + MLM. F1 Neutral (UIT) ngang `mtl` (p > 0.4), thấp hơn `mtl_mlm` (p gốc: PhoBERT 0.016, ViSoBERT 0.13), và cao hơn các setup có SMART. Nguyên nhân có thể là KD kéo dự đoán về phân phối mềm, nơi lớp hiếm có xác suất nhỏ (chưa kiểm chứng). Logit bias chỉ sửa được ở UIT-VSFC (Bảng 6).

**Bảng 6 – Logit bias trên lớp hiếm của ED (test, NEU-ESC 15 seed, UIT-VSFC 10 seed):** bias chọn theo macro-F1 val, áp dụng một lần lên test. Δ và p (t-test ghép cặp theo seed) so với ED không có bias.

| Dataset | Backbone | Lớp | Δ acc (p) | Δ macro-F1 (p) | F1 lớp hiếm: gốc → bias | Δ (p) |
|---|---|---|---:|---:|---:|---:|
| NEU-ESC | PhoBERT | Toxic | −0.01 (0.461) | −0.02 (0.677) | 83.28 → 83.21 | −0.07 (0.754) |
| NEU-ESC | ViSoBERT | Toxic | +0.02 (0.157) | +0.07 (0.264) | 82.94 → 83.26 | +0.33 (0.161) |
| UIT-VSFC | PhoBERT | Neutral | −0.03 (0.483) | **+0.75 (0.019)** | 54.86 → 57.12 | **+2.26 (0.018)** |
| UIT-VSFC | ViSoBERT | Neutral | −0.05 (0.357) | **+1.63 (0.001)** | 51.29 → 56.08 | **+4.80 (< 0.001)** |

- **UIT-VSFC:** F1 Neutral và macro-F1 tăng, accuracy không giảm có ý nghĩa. Khi mọi setup cùng dùng bias, ED không còn thua `mtl_mlm` về macro-F1: PhoBERT +0.03 (p = 0.905), ViSoBERT +0.59 (p = 0.052).
- **NEU-ESC:** không đổi có ý nghĩa. Khi cùng dùng bias, F1 Toxic của ED vẫn thấp hơn setup có SMART tốt nhất (83.21 so với 85.40; 83.26 so với 85.37).
- **Một bias cho mỗi lớp:** không dùng, vì accuracy của ED giảm có ý nghĩa (NEU-ESC sentiment −0.40 / −0.53, topic −0.20 / −0.45; UIT-VSFC sentiment −0.10 / −0.34; p ≤ 0.042).
- **Cách đọc:** kết quả chính của paper vẫn là ED không có bias. Đây là phân tích sau huấn luyện, p của Bảng 6 chưa hiệu chỉnh đa so sánh.
- **Hướng tiếp theo:** giảm trọng số distill (γ) cho lớp hiếm, nhất là Toxic. Có thể thử thêm loss cân bằng lớp cùng ED, nhưng cách này có thể làm giảm accuracy.

**Hạn chế khác:**
- **Thời gian train lâu hơn:** tính cả tạo teacher (~16 giờ GPU, làm một lần cho mỗi dataset), ED mất 16.30 giờ để có model đầu tiên trên NEU-ESC, so với 0.65–2.19 giờ của các baseline MTL. Thời gian suy luận không đổi.
- **Siêu tham số không tinh chỉnh:** γ = 1, 30 teacher.

**Ablation có thể thêm nếu còn quota (chưa chạy):**
- γ ∈ {0.5, 2}.
- Số teacher (5 / 15 / 30 model) và teacher một backbone.

## 10. Conclusion

- Reproduce NEU-ESC theo code công khai với 15 seed. 16/20 ô có seed đạt số của paper; 4 ô không có seed nào đạt, trong đó 83.58 và 83.66 không giải thích được bằng may rủi hay cách chọn epoch.
- ED: một model MTL học từ ensemble out-of-fold, không đổi kiến trúc, không tăng chi phí suy luận; đổi lại, thời gian train lâu hơn do phải tạo teacher (§9).
- NEU-ESC: thắng mọi baseline ở mọi ô, cả accuracy và macro-F1. Kết quả này giữ nguyên sau hiệu chỉnh Holm. UIT-VSFC: topic tăng có ý nghĩa ở accuracy, riêng macro-F1 PhoBERT không còn có ý nghĩa sau Holm; sentiment không khác có ý nghĩa so với baseline mạnh nhất.
- Vai trò của out-of-fold (chỉ kiểm tra trên NEU-ESC): tăng accuracy có ý nghĩa so với teacher in-sample, không khác có ý nghĩa về macro-F1; phần lớn mức tăng macro-F1 đến từ chính việc distill.
- Hướng tiếp: xử lý lớp hiếm khi distill; thử teacher nhỏ hơn để giảm chi phí.

## Phụ lục (nếu cần)

- F1 từng lớp của cả 6 setup trên NEU-ESC (bổ sung cho Bảng 4).
- Danh sách siêu tham số đầy đủ và SHA-256 runner / dữ liệu.
- Tái lập: code `src_baseline/`, `src_improvement/`; số liệu `reports/*/per_run.csv` và `reports/baseline_reproduce/metrics/per_run.csv`.
