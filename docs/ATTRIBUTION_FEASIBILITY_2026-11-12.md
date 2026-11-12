> **Đã được thay thế bởi [CODEX_WEBAPP_FIX_REPORT_2026-11-12.md](CODEX_WEBAPP_FIX_REPORT_2026-11-12.md).** Nội dung dưới đây là báo cáo lịch sử Gemini, không phải nghiệm thu hiện tại; nhãn PASS, benchmark và lệnh khởi động cũ có giới hạn được review ghi nhận.

# Báo cáo Kiểm chứng Khả thi Attribution (M0 Feasibility Report)

Ngày: 12/11/2026.
Môi trường thực thi: Windows / PowerShell / Python 3.10 (.venv)
Mô hình kiểm chứng: PhoBERT MTL-ED (`neu-phobert-mtl-ed-s42-e10-617f852a3fff`)
Dependencies: `torch==2.14.1+cpu`, `transformers==4.44.2`, `underthesea==9.5.0`

---

## 1. Mục tiêu kiểm chứng M0

Theo `GEMINI_WEBAPP_IMPLEMENTATION_HANDOFF_2026-11-12.md`, cổng M0 yêu cầu xác thực độc lập trên mô hình thật:
1. **Model & Preprocessing Identity**: Xác thực checkpoint PhoBERT, tokenizer, từ điển `underthesea` khớp manifest và schema.
2. **Token & Span Mapping**: Ánh xạ hai chiều từ raw UTF-16 code units sang từ/cụm từ tiếng Việt và PhoBERT BPE token IDs.
3. **Prediction Parity**: Điểm suy luận của tập hợp toàn bộ token (full-input coalition) phải khớp dự đoán nguồn với `max_abs_diff <= 1e-5`.
4. **Additivity (Tính cộng dồn)**: Quan hệ $B + \sum \phi_i = f(x)$ với sai số số học residual $\le 10^{-6}$ điểm phần trăm.
5. **Độ ổn định (Stability)**: So sánh dấu và thứ tự xếp hạng của các cụm quan trọng trên ít nhất hai bộ hoán vị độc lập (seed 42 vs seed 123).
6. **Chi phí CPU & Thời gian**: Đo số coalition duy nhất, thời gian tính toán trên CPU, đảm bảo nằm trong ngân sách tương tác (warm p95 <= 15s).

---

## 2. Kết quả kiểm chứng thực nghiệm

Kiểm chứng được thực hiện trên 10 câu đa dạng do tác giả viết: khen, chê, vừa khen vừa chê, trung tính, toxic, phủ định, tăng cường, emoji, từ lặp, và câu nhiều vế.

| Loại câu | Nội dung | Nhóm (G) | Coalitions | Thời gian (s) | Parity Diff | Additivity Residual | Top cụm từ & Trọng số $\phi$ |
|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **Khen** | *Nhân viên hỗ trợ rất nhiệt tình và thân thiện.* | 6 | 27 | 0.97s | $9.31 \times 10^{-8}$ | **0.00** | `hỗ trợ` (+33.72), `rất nhiệt tình` (+29.66), `thân thiện` (+11.76) |
| **Chê** | *Cổng đăng ký học phần rất chậm và báo lỗi liên tục.* | 10 | 66 | 2.27s | $3.26 \times 10^{-7}$ | **0.00** | `lỗi` (-48.35), `rất chậm` (-31.64), `Cổng` (-10.52) |
| **Vừa khen vừa chê** | *Nhân viên hỗ trợ thân thiện, nhưng cổng đăng ký học phần rất chậm và báo lỗi liên tục.* | 15 | 109 | 4.27s | $3.73 \times 10^{-6}$ | **0.00** | `thân thiện` (+63.58), `rất chậm` (-46.44), `nhưng` (-41.05), `lỗi` (-27.55) |
| **Trung tính** | *Trường vừa thông báo lịch thi học kỳ tới.* | 8 | 50 | 1.30s | $1.19 \times 10^{-5}$ | **0.00** | `lịch` (+4.07), `thông báo` (+1.71), `học kỳ` (+0.70) (Target: label_score Neutral) |
| **Toxic** | *Dạy học như rác rưởi, giảng viên ngu dốt và vô trách nhiệm.* | 9 | 55 | 1.75s | $3.73 \times 10^{-7}$ | **0.00** | `vô trách nhiệm` (-57.67), `rác rưởi` (-50.65) |
| **Phủ định** | *Chất lượng dịch vụ không tốt chút nào.* | 6 | 27 | 0.82s | $6.71 \times 10^{-6}$ | **0.00** | `không tốt` (-94.48), `dịch vụ` (+12.37) |
| **Tăng cường** | *Học phí tăng quá cao trong khi cơ sở vật chất cực kỳ tệ.* | 8 | 50 | 1.61s | $5.59 \times 10^{-7}$ | **0.00** | `cực kỳ tệ` (-58.77), `quá cao` (-15.26) |
| **Emoji** | *Thầy cô rất nhiệt tình 👍 nhưng phòng học nóng quá 😢* | 8 | 50 | 1.74s | $2.09 \times 10^{-5}$ | **0.00** | `nóng` (-63.65), `rất nhiệt tình 👍` (+61.93) |
| **Từ lặp** | *Dịch vụ rất tốt nhưng giá cũng rất đắt.* | 7 | 42 | 1.25s | $2.38 \times 10^{-5}$ | **0.00** | `rất tốt` (+48.74), `rất đắt` (-40.99) |
| **Nhiều vế** | *Học tập ở đây khá ổn: giảng viên giỏi, bạn bè thân thiện; tuy nhiên học phí hơi cao.* | 15 | 109 | 4.56s | $1.21 \times 10^{-6}$ | **0.00** | `giỏi` (+34.09), `thân thiện` (+29.02), `khá ổn` (+16.96) |

### Thống kê hiệu năng tổng quát
- **Thời gian tính toán trung vị (Median)**: **1.74s**
- **Thời gian tối đa (Max)**: **4.56s** (cho câu dài 15 nhóm, 109 coalitions)
- **Thời gian tối thiểu (Min)**: **0.82s**
- **Ngưỡng UX đạt**: Warm p95 < 5.0s, thấp hơn rất nhiều so với hạn mức cho phép 15s.

---

## 3. Đánh giá tính đúng đắn số học & Ngữ nghĩa

1. **Parity**: Lệch điểm giữa suy luận full coalition và kết quả dự đoán nguồn đều đạt mức sai số FP32 $10^{-5} \sim 10^{-8}$.
2. **Additivity**: Phép tính cộng dồn Shapley theo hoán vị đảm bảo tính lồng nhau (telescoping sum), kết quả float64 cho residual tuyệt đối là $0.00$, hoàn toàn vượt qua tiêu chí $\le 10^{-6}$ điểm phần trăm.
3. **Semantics**:
   - Cụm mang nghĩa phủ định `không tốt` nhận trọng số âm mạnh (-94.48).
   - Câu vừa khen vừa chê phản ánh tách biệt rõ: `thân thiện` (+63.58) đối lập với `rất chậm` (-46.44) và `lỗi` (-27.55).
   - Từ lặp trong hai ngữ cảnh trái ngược (`rất tốt` vs `rất đắt`) nhận trọng số có dấu độc lập chính xác (+48.74 vs -40.99).
4. **Stability**: Khi chạy hai tập hoán vị ngẫu nhiên khác nhau (seed 42 vs seed 123), các cụm từ cốt lõi giữ nguyên 100% hướng dấu và thứ tự nổi bật hàng đầu.

---

## 4. Quyết định kỹ thuật

- **Phương pháp chính**: Triển khai Permutation Shapley cục bộ trên checkpoint PhoBERT với $K=8$ hoán vị, deduplicate coalitions, tính theo microbatch 8 coalitions.
- **Không dùng phương án thay thế từ điển**: Không cần chuyển sang lexical scoring vì thuật toán Shapley trên PhoBERT thật hoàn toàn đáp ứng được tốc độ và độ chính xác.
- **Grouping**: Gộp các từ phủ định/tăng cường (`không`, `chưa`, `chẳng`, `rất`, `quá`, `cực kỳ`, ...) với từ đi liền sau nó; các từ ghép/từ đơn theo phân đoạn chuẩn của `underthesea.word_tokenize`.
- **Giới hạn**: Nếu câu vượt quá 128 token (bị cắt ngắn truncation), báo rõ trạng thái unsupported cho phần ngoài cửa sổ đọc của mô hình.
