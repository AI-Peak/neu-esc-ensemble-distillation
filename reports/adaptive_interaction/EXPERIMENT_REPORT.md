# Báo cáo Adaptive Interaction NEU-ESC

## Tóm tắt điều hành

Đã kiểm toán repository tại commit `a6760e6c2cdae6f2bc9c0d5063b563703314dc9f` và triển khai module Adaptive Interaction với ba biến thể kiểm soát: chiếu độc lập, trao đổi không cổng, và trao đổi hai chiều có cổng học được. Workflow Kaggle có 20 run định trước (4 biến thể × 5 seed 42–46), checkpoint chọn theo trung bình macro-F1 trên validation, và không dùng test để chọn mô hình.

GPU chưa được thực thi: máy hiện tại không có NVIDIA GPU, không có Kaggle CLI hoặc phiên Kaggle đã xác thực, và connector không đọc được notebook đích. Vì vậy không có metric mới nào được coi là kết quả GPU; mọi ô còn thiếu trong bảng là thiếu có chủ ý. CPU smoke run trên encoder nhỏ đã hoàn thành, chỉ kiểm tra hình dạng, lan truyền gradient và lưu artifact, không báo cáo như thực nghiệm.

## Kiểm chứng baseline

Baseline PhoBERT multi-task dùng encoder dùng chung, pooling token đầu tiên, hai head tuyến tính và loss `0.5*(CE_sentiment + CE_topic)`. Báo cáo đã commit có cohort 15 seed cho `phobert/mtl` (42–56). Slice 42–46 được trích xuất trong `baseline_phobert_mtl_seeds42_46.csv`; số liệu lịch sử không được dùng để thay thế cho kết quả Adaptive Interaction. CR-SD và CR-SD + D là so sánh phụ, khác seed và ngân sách.

Dataset có 23,048/3,305/6,613 dòng, 4 nhãn sentiment và 10 nhãn topic. Audit độc lập xác nhận không có overlap văn bản sau chuẩn hóa NFC và khoảng trắng.

## Kiến trúc đề xuất

PhoBERT tạo `H`; token đầu tiên được dùng làm vector ngữ cảnh. Hai projection tạo `h_s` và `h_a`, sau đó trao đổi thông tin hai chiều. Với biến thể đầy đủ: `g_s=sigmoid(W_s[h_s;h_a])`, `g_a=sigmoid(W_a[h_a;h_s])`, `z_s=LN(h_s+g_s⊙T_s(h_a))`, `z_a=LN(h_a+g_a⊙T_a(h_s))`. Hai head xuất 4 và 10 logits. Không thêm SMART, MLM, distillation hay loss weight mới trong cohort chính.

## Thiết lập và tái lập

Lệnh CPU smoke: `python src_adaptive/run_experiment.py --variant adaptive --seed 42 --smoke --epochs 2 --cpu --out-dir runs/adaptive_smoke`. Lệnh Kaggle đầy đủ nằm trong `adaptive_interaction_kaggle.ipynb`; notebook kiểm GPU, tải dữ liệu có hash, chạy 20 run idempotent và tổng hợp chỉ các run `COMPLETED`.

## Kết quả định lượng

`comparison_metrics.csv` ghi baseline lịch sử đã xác minh và các trường Adaptive Interaction còn trống do chưa có GPU execution evidence. Không được suy ra cải thiện từ CPU smoke.

## Kiểm soát chất lượng

Pass 1: `py_compile` và smoke test kiểm tra tensor dimensions, output 4/10 logits, loss, gradient và serialization. Pass 2: audit split/hash và manifest run giữ cặp seed 42–46; test chỉ đọc sau checkpoint validation. Pass 3: bảng CSV được sinh từ artifact baseline đã commit; không có số liệu đề xuất được điền bằng ước lượng.

## Hạn chế và đánh giá khoa học

Chưa thể trả lời liệu cổng adaptive cải thiện macro-F1, có ổn định qua seed, hay đáng chi phí thêm hay không. Kết luận hợp lệ hiện tại là kiến trúc đã IMPLEMENTED và TESTED ở mức smoke, workflow GPU đã chuẩn bị, nhưng kết quả GPU/EVALUATED/VERIFIED cho mô hình mới đang BLOCKED bởi quyền truy cập Kaggle và phần cứng. Cần chạy notebook với accelerator T4 (hoặc tương thích), tải đủ 20 run, sau đó chạy `aggregate.py` và kiểm toán lại trước khi kết luận giữ hay loại bỏ đóng góp.
