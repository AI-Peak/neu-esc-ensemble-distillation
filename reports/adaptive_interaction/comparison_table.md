# Bảng so sánh kết quả: Repo GitHub vs Phương pháp mới (Adaptive Interaction)

## 1. Bảng số liệu tổng hợp

| Nhóm | Mô hình / Phương pháp | Sentiment Macro-F1 (%) | Sentiment Acc (%) | Topic Macro-F1 (%) | Topic Acc (%) | Parameters | Training Time | $\Delta$ Acc (vs Baseline MTL) | Ghi chú |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Gốc từ Paper** | Paper (Table 6) | 75.99 | 82.88 | 62.11 | 79.25 | ~135M | — | — | Baseline MTL từ bài báo gốc |
| | Paper + SMART | 77.52 | 83.26 | 62.79 | 79.31 | ~135M | — | +0.38 / +0.06 | Paper gốc thêm SMART regularization |
| **Repo GitHub (Tái lập)** | PhoBERT Single-task | 77.24 | 82.27 | 61.49 | 78.16 | ~270M | 0.70h | -0.12 / -0.59 | 2 mô hình huấn luyện độc lập |
| | **PhoBERT MTL (baseline)** | **76.62** | **82.30** | **62.27** | **78.80** | **134.98M** | **0.65h** | **Gốc chuẩn (0.00)** | Tái lập chính thức (slice 5 seeds) |
| | PhoBERT MTL + SMART | 76.07 | 82.85 | 61.95 | 79.05 | 134.98M | 1.69h | +0.46 / +0.25 | Tái lập MTL kết hợp SMART |
| **Repo GitHub (Cải tiến cũ)** | **CR-SD (selfdistill)** | **77.40** | **83.30** | **63.15** | **79.72** | **135.20M** | **1.45h** | **+0.91 / +0.97** | Self-distillation (2 seeds) |
| | CR-SD + D (crsd_ens) | 77.85 | 83.65 | 63.48 | 80.05 | 270.40M | 2.90h | +1.26 / +1.25 | Ensemble 2 mô hình CR-SD |
| **Phương pháp mới (Đề xuất)** | **Independent Projection** | 75.45 | 81.22 | 60.95 | 77.45 | 136.16M | 2h31m | -1.08 / -1.35 | Chiếu độc lập, không trao đổi |
| | **Ungated Interaction** | 75.68 | 81.35 | 61.25 | 77.70 | 137.34M | 2h39m | -0.95 / -1.10 | Trao đổi hai chiều không cổng |
| | **Adaptive Interaction (full)** | **76.05** | **81.78** | **61.68** | **78.22** | **138.52M** | **2h47m** | **-0.52 / -0.58** | Trao đổi hai chiều có cổng gating học được |

---

## 2. Nhận xét phân tích chuyên môn

1. **Hiệu năng so với Baseline MTL**:
   * Mô hình `Adaptive Interaction` đạt độ chính xác **81.78%** (Sentiment) và **78.22%** (Topic), thấp hơn baseline MTL tương ứng **-0.52%** và **-0.58%**. Thời gian huấn luyện tăng lên **2h47m** do chi phí lan truyền ngược và tính toán qua module gating bổ sung.
   * Macro-F1 ở cả hai tác vụ ghi nhận ở mức $76.05\%$ và $61.68\%$, cho thấy khi chưa được kết hợp các cơ chế điều hòa (như SMART) hoặc tối ưu siêu tham số riêng, kiến trúc tương tác đa nhiệm có thể chịu tổn thất nhỏ về độ tổng quát hóa so với baseline trực tiếp.

2. **So với phương pháp SOTA trong repo (CR-SD)**:
   * `Adaptive Interaction` có kết quả thấp hơn đáng kể so với `CR-SD (selfdistill)` ($81.78\%$ vs $83.30\%$ Sentiment; $78.22\%$ vs $79.72\%$ Topic).
   * Điều này giải thích hợp lý vì CR-SD tận dụng phân phối mềm từ chính mô hình (self-distillation) để làm mượt bề mặt hàm loss, giúp tối ưu tốt hơn nhiều so với việc chỉ can thiệp cấu trúc biểu diễn đầu ra.

3. **Nghiên cứu bóc tách (Ablation Study)**:
   * Giữ vững tính phân cấp nội bộ hợp lý:
     - `Independent Projection` ($81.22\% / 77.45\%$) thấp nhất do chia cắt hoàn toàn đặc trưng của 2 nhiệm vụ.
     - `Ungated Interaction` ($81.35\% / 77.70\%$) cải thiện nhẹ nhưng bị giới hạn bởi nhiễu chéo khi ghép nối trực tiếp.
     - `Adaptive Interaction` ($81.78\% / 78.22\%$) đạt điểm tốt nhất trong nhóm cải tiến mới nhờ bộ cổng Sigmoid học cách tiết chế thông tin truyền qua giữa hai head.
