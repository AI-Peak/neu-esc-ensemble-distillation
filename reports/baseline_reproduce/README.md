# Báo cáo tình trạng Baseline Reproduce (NEU-ESC, arXiv 2506.23524)

Nhóm 5, DPL302m. Cập nhật 2026-11-05.

## 1. Kết luận

**Nhóm đã reproduce đúng baseline.**
- Code chạy theo đúng code gốc của tác giả.
- Kết quả trung bình lệch paper khoảng 0.4 điểm.
- Xu hướng giống paper về accuracy: SMART tăng so với MTL ở cả 4 ô. Macro-F1 thì không giống: SMART giảm ở 3/4 ô (chỉ PhoBERT sentiment có ý nghĩa: −0.79, p = 0.001, paper +1.53) và chỉ tăng ở ViSoBERT topic (+0.52, paper +1.47); xem [metrics/summary.md](metrics/summary.md).

Hai con số baseline chốt dùng để so sánh với phần cải tiến:

| Task | Baseline reproduce | Cấu hình | Paper |
|---|---|---|---|
| **Sentiment** | **82.85 ± 0.24** | PhoBERT MTL + SMART, 15 seed | 83.26 |
| **Topic** | **79.55 ± 0.20** | ViSoBERT MTL + MLM + SMART, 15 seed | 79.25 |

Cách tính hai số này như sau:
- Chọn checkpoint theo tập **validation**, như paper mô tả.
- Đánh giá **một lần** trên test.
- Lấy **trung bình ± độ lệch chuẩn** qua 15 lần chạy với 15 seed khác nhau (42–56).
- Không nhìn test để chọn epoch, không chọn seed may mắn.

Mỗi task lấy setup có trung bình cao nhất trong 10 dòng của §2, với mọi dòng đều có 15 seed. Ở topic, ViSoBERT MTL+MLM+SMART (79.55) cao hơn ViSoBERT MTL+SMART (79.35 ± 0.16), dòng được chốt trước khi dòng MLM đủ 15 seed.

Mốc lớn nhất trong paper là 83.66 / 79.80 (§3).
- Ô topic 79.80 là dòng ViSoBERT MTL+SMART. Trung bình nhóm ở dòng này là 79.35, thấp hơn 0.45 điểm, và 0/15 lần chạy đạt tới (§3).
- Ô sentiment 83.66 là dòng PhoBERT MTL+MLM+SMART. Nhóm đã chạy dòng này nhưng không đạt (§3).

## 2. Kết quả đầy đủ (test accuracy %, trung bình ± độ lệch chuẩn)

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

Số lần chạy: 15 seed (42–56) cho mọi dòng.

Cách đọc bảng:
- Độ lệch trung bình (giá trị tuyệt đối) là **0.42 điểm**. Biên độ giữa các seed (max − min) từ 0.48 đến 2.51 điểm, trung bình 1.40. Vậy độ lệch trung bình nhỏ hơn mức dao động trung bình của một lần chạy; các ô 0/15 ở §3 là ngoại lệ.
- Hầu hết các ô của nhóm **thấp hơn paper một chút**. Đây là điều dễ hiểu: paper chỉ báo **một lần chạy** cho mỗi dòng, còn nhóm báo **trung bình nhiều lần**. Số của một lần chạy được chọn để báo cáo thường cao hơn số trung bình.

## 3. Đã kiểm tra những nguyên nhân gì

Nhóm dùng 10 tài khoản Kaggle (GPU T4) và chạy tổng cộng **210 lần**. Kết quả theo từng giả thuyết:

| # | Giả thuyết | Cách kiểm | Kết quả |
|---|---|---|---|
| 1 | Paper chỉ chạy 1 lần, gặp may | Tăng từ 5 lên 15 seed | **Đúng với phần lớn các ô.** 16/20 ô có ít nhất một seed đạt số của paper. Bốn ô đạt 0/15: ViSoBERT MTL+SMART (83.58, 79.80) và PhoBERT MTL+MLM+SMART (83.66, 79.49). |
| 2 | Tác giả chọn epoch bằng cách nhìn test (code lưu mọi epoch, không ghi tiêu chí chọn) | Lưu kết quả test ở mọi epoch, so 4 cách chọn | Nếu nhìn test thì MTL tăng thêm khoảng +0.3 đến +0.9. **Không giải thích được 2 ô lệch lớn** (xem dưới). |
| 3 | fp32 (tác giả) khác fp16 (nhóm) | Chạy lại MTL và MTL+SMART bằng fp32, cùng 5 seed | **Không ảnh hưởng.** Chênh lệch từ −0.28 đến +0.41, trung bình gần 0. |
| 4 | SMART bị cài sai | Đặt nhiễu lên embedding như SMART gốc của Jiang et al. | Accuracy **sụp xuống khoảng 72%**. Code gốc mới là bản đúng để reproduce (giải thích dưới). |
| 5 | Dòng MLM chưa được chạy | Cài đúng trainer 3 head của tác giả | **Đã reproduce.** MTL+MLM khớp paper; MTL+MLM+SMART thấp hơn (xem dưới). |

### Hai ô lệch lớn: không phải lỗi của nhóm

| Ô | Paper | Trung bình nhóm | Số lần chạy đạt paper | Mức cao nhất có thể* |
|---|---|---|---|---|
| ViSoBERT MTL+SMART, sentiment | 83.58 | 82.71 ± 0.18 | 0/15 | 83.09 |
| PhoBERT MTL+MLM+SMART, sentiment | 83.66 | 82.83 ± 0.16 | 0/15 | 83.25 |

\*Mức cao nhất có thể: lấy epoch có test cao nhất cho riêng task đó, rồi lấy seed tốt nhất. Đây là kiểu "gian lận tối đa", chỉ dùng để chứng minh, không dùng để báo cáo.

Kể cả khi gian lận tối đa, nhóm vẫn không chạm được hai số này. Ngoài ra:
- Đổi sang fp32 không giúp được.
- Code tác giả công bố không cho ra được số này.

Theo nguyên tắc nhóm đặt ra từ đầu, **hai ô này được kết luận là do phía tác giả.** Có thể họ đã chạy một phiên bản code, dữ liệu hoặc cấu hình khác với bản công bố. Từ những gì đã công bố, nhóm không thể sửa được.

### Những điểm lạ trong code của tác giả (nhóm phát hiện)

1. **SMART thực chất không phải SMART.**
   - Code cộng nhiễu vào *token ID* chứ không phải vào embedding, rồi ép kiểu `.long()`. Khi đó nhiều token bị đổi thành token có ID liền kề.
   - Vì vậy phần "SMART" của paper thực ra là **thay token ngẫu nhiên rồi bắt mô hình dự đoán giống nhau** (consistency regularization).
   - Nếu đặt nhiễu đúng lên embedding theo thuật toán của chính họ, nhiễu bị chuẩn hóa về độ lớn khoảng 1, lớn hơn embedding (khoảng 0.05) rất nhiều, nên mô hình hỏng.
   - Nhóm reproduce theo **code gốc**, vì bản này cho đúng xu hướng tăng như paper: ViSoBERT sentiment +0.67 (paper +0.95), topic +1.13 (paper +1.24).
2. **ViSoBERT + MLM không chạy được với code gốc.** Code chọn token ngẫu nhiên trong khoảng 0–64000, theo kích thước từ vựng của PhoBERT. Từ vựng ViSoBERT nhỏ hơn nhiều (khoảng 15k), nên sẽ báo lỗi. Nhóm giới hạn trong từ vựng của ViSoBERT; đây là sai khác duy nhất và có ghi lại trong config.
3. **Trainer MLM luôn bật SMART**, vì dòng `if is_smart` đã bị comment. Dòng "MTL+MLM không SMART" trong paper vì vậy không thể sinh ra từ code công bố nếu không sửa code. Nhóm đã tắt SMART để chạy dòng này.
4. **MTL không chọn checkpoint tự động.** Code lưu mọi epoch từ epoch 4 và không ghi tiêu chí chọn. Ngoài ra code không đặt seed, nên chính tác giả cũng không thể chạy lại ra đúng số cũ.

## 4. Ý nghĩa cho phần cải tiến

- So sánh cải tiến với **82.85 (sentiment)** và **79.55 (topic)**, theo đúng cách tính ở trên: chọn theo val và lấy trung bình nhiều seed.
- Trong bảng chính, nên so **cùng backbone** (ví dụ PhoBERT MTL+SMART với PhoBERT ED) để phép so sánh công bằng.

## Phụ lục: số liệu kiểm tra

Mỗi ô ghi theo dạng **sentiment / topic**, test accuracy %.

### A. Cách chọn checkpoint (giả thuyết 2)

Các run có lưu test ở mọi epoch:
- 10 seed cho MTL và MTL+SMART.
- 15 seed cho hai dòng MLM.

Cách đọc các cột:
- **Val**: cách của nhóm, chọn epoch theo tập validation.
- **Nhìn test**: chọn epoch có test trung bình hai task cao nhất.
- **Trần**: lấy epoch tốt nhất cho riêng từng task, rồi lấy seed tốt nhất.

| Backbone | Setup | Val (trung bình) | Nhìn test (trung bình) | Trần | Paper |
|---|---|---|---|---|---|
| PhoBERT | MTL | 82.43 / 78.73 | 83.02 / 78.93 | 83.43 / 79.36 | 82.88 / 79.25 |
| PhoBERT | MTL + SMART | 82.82 / 79.07 | 82.88 / 79.12 | 83.29 / 79.40 | 83.26 / 79.31 |
| PhoBERT | MTL + MLM | 82.25 / 78.46 | 82.98 / 79.00 | 83.38 / 79.57 | 82.67 / 78.48 |
| PhoBERT | MTL + MLM + SMART | 82.83 / 79.09 | 82.95 / 79.19 | **83.25** / 79.54 | **83.66** / 79.49 |
| ViSoBERT | MTL | 81.92 / 78.45 | 82.88 / 78.67 | 83.32 / 79.04 | 82.63 / 78.56 |
| ViSoBERT | MTL + SMART | 82.68 / 79.38 | 82.80 / 79.50 | **83.09** / 79.75 | **83.58** / 79.80 |
| ViSoBERT | MTL + MLM | 81.83 / 78.18 | 82.77 / 78.65 | 83.34 / 79.12 | 82.23 / 78.38 |
| ViSoBERT | MTL + MLM + SMART | 82.82 / 79.55 | 82.97 / 79.66 | 83.28 / 79.96 | 83.12 / 79.25 |

### B. fp32 so với fp16 (giả thuyết 3)

Cùng 5 seed 42–46, chạy một lần bằng fp16 và một lần bằng fp32.

| Backbone | Setup | fp16 | fp32 | Chênh lệch |
|---|---|---|---|---|
| PhoBERT | MTL | 82.30 / 78.80 | 82.08 / 78.52 | −0.22 / −0.28 |
| PhoBERT | MTL + SMART | 82.90 / 79.02 | 82.86 / 78.95 | −0.05 / −0.07 |
| ViSoBERT | MTL | 82.30 / 77.77 | 82.25 / 78.19 | −0.05 / +0.41 |
| ViSoBERT | MTL + SMART | 82.77 / 79.28 | 82.92 / 79.43 | +0.15 / +0.15 |

### C. SMART đặt nhiễu trên embedding (giả thuyết 4)

5 seed 42–46.

| Backbone | MTL | SMART theo code gốc | SMART trên embedding |
|---|---|---|---|
| PhoBERT | 82.30 / 78.80 | 82.90 / 79.02 | 72.49 / 72.38 |
| ViSoBERT | 82.30 / 77.77 | 82.77 / 79.28 | 72.21 / 70.96 |

### Thư mục này gồm những gì

| File / thư mục | Nội dung |
|---|---|
| `README.md` | Báo cáo này |
| `gap_runs.csv` | Kết quả từng run (210 run) dùng cho báo cáo |
| `metrics/` | Bảng đầy đủ accuracy, macro-F1, weighted-F1 của 15 seed so với paper (`src_baseline/aggregate.py`) |
| `paper/` | Số liệu Table 6 và Figure 3 chép từ paper, phần audit Figure 3 |
| `author_code/` | Bản sao code tác giả (commit b5637cc0), dùng cho `src_baseline/check_author_smart.py` |
| `data_source/` | Hash tải dữ liệu, thống kê nhãn, đối chiếu CSV gốc với bản `_processed` |

### Cách tạo lại

- Bảng phân tích: `python src_baseline/analyze_gap.py`. Lệnh in các bảng ra màn hình và ghi lại `gap_runs.csv`.
- Bảng metrics: `python src_baseline/aggregate.py runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 runs/gap/a runs/gap/mlm --out reports/baseline_reproduce/metrics`
- Run gốc nằm trong:
  - `runs/s42..s46`: 5 seed gốc.
  - `runs/gap/a`: thêm 10 seed và các dòng MLM seed 42–46.
  - `runs/gap/mlm`: các dòng MLM seed 47–56 (cùng runner `5a56bc35…`, cùng cờ `--test-every-epoch`).
  - `runs/gap/b`: fp32 và SMART trên embedding.
- Có hai phiên bản runner:
  - 40 run gốc chạy bằng `2a2a25ae…`.
  - Các run sau chạy bằng `5a56bc35…`. Bản này chỉ thêm code MLM và tùy chọn `--jobs`.
  - Hai bản cho logits giống hệt nhau ở các setup cũ (đã kiểm trên CPU), nên gộp chung được.
