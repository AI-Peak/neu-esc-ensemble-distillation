# NEU-ESC Feedback Workspace

<!-- impeccable:product-schema 1 -->

## Platform

web (local-first loopback on Windows)

## Stack

Đã triển khai cục bộ trên nhánh `webapp`:
- **Giao diện**: TypeScript + React 19 + TanStack Query + TanStack Table + Vite (`apps/web/`, build tĩnh được FastAPI phục vụ cùng origin tại `http://127.0.0.1:8765`).
- **API & Worker**: Python 3.10 + FastAPI + Uvicorn (`services/api/`) và tiến trình worker suy luận độc lập (`services/worker.py`).
- **Suy luận & Tiền xử lý**: PyTorch CPU FP32 + Transformers (`use_fast=False`, `max_length=128`) + `underthesea==9.5.0` (tách từ offline cho PhoBERT).
- **Lưu trữ**: SQLite WAL cục bộ (`runtime/workspace.sqlite3`) và bundle model phân phiên bản (`runtime/models/`).

## Users

- Công cụ làm việc cục bộ cho giảng viên, trợ giảng, cán bộ đào tạo hoặc nhóm nghiên cứu cần nhập phản hồi sinh viên tiếng Việt, phân loại cảm xúc và chủ đề, rà soát các trường hợp cần chú ý và xuất CSV.
- Chạy trên máy cá nhân trước (loopback `127.0.0.1`), không gửi văn bản phản hồi ra dịch vụ đám mây bên ngoài.

## Product Purpose

Nhập phản hồi tiếng Việt (dán dòng hoặc CSV UTF-8), tự động gán nhãn cảm xúc và chủ đề bằng student MTL-ED đã fine-tune, lọc/tổng hợp phân bố, rà soát và sửa nhãn độc lập theo từng tác vụ, sau đó xuất bản chụp CSV cố định. Báo cáo nghiên cứu là tab phụ (`#/research`), không thay thế quy trình làm việc chính.

## Positioning

Dự án tái lập đa seed các baseline của NEU-ESC theo code công khai, cải tiến bằng Out-of-Fold Ensemble Distillation (ED) với 30 teacher theo fold (2 backbone × 3 seed × 5 fold), và kiểm chứng mở rộng trên UIT-VSFC (`Springer_Nature_LaTeX_Paper/paper.tex`). Khi suy luận, hệ thống chỉ chạy **một** student MTL duy nhất (không chạy ensemble 30 model, SMART hay MLM).

## Operating Context

- **Checkpoint hiện có**: `demo/model.pt` (`phobert-mtl_ed-s42`, `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1`, seed 42, best epoch 10) đã được kiểm chứng và import thành bundle versioned tại `runtime/models/neu` (`neu-phobert-mtl-ed-s42`). Profile `uit` chưa có checkpoint riêng nên tiếp tục hiển thị `unavailable` và vẫn cho phép nhập/rà soát thủ công.
- **Phần cứng kiểm thử local**: AMD Ryzen 7 PRO 5850U (~30,8 GiB RAM, Windows 10/11, Python 3.10.11, CPU FP32).
- **Ranh giới thực thi**: Không huấn luyện, không tải teacher ensemble và không tải trọng số từ mạng trong request web.

## Capabilities and Constraints

- **Hai hệ nhãn tách biệt**:
  - `neu` (`neu-v1`): 4 lớp cảm xúc (`Neutral`, `Positive`, `Negative`, `Toxic`) và 10 chủ đề thảo luận sinh viên.
  - `uit` (`uit-v1`): 3 lớp cảm xúc (`negative`, `neutral`, `positive`) và 4 chủ đề đánh giá đào tạo (`lecturer`, `training_program`, `facility`, `others`). Không hoán đổi checkpoint giữa hai profile.
- **Tiền xử lý PhoBERT trên NEU**: Checkpoint PhoBERT học trên file `_processed.csv` đã tách từ của tác giả NEU (pipeline gốc của tác giả không được công bố đầy đủ). Khi chạy câu raw của người dùng, hệ thống dùng adapter `underthesea==9.5.0` (`word_tokenize(..., format="text")`) ở bước nội bộ trước tokenizer, gắn cờ `equivalence: "approximate"`, và **giữ nguyên văn bản gốc** trong database cũng như file xuất CSV.
- **Giới hạn thống kê theo paper (`paper.tex`)**:
  - Trên NEU-ESC (15 seed 42–56), ED vượt cả 5 baseline trên cả hai backbone và cả hai tác vụ về Accuracy và Macro-F1 sau hiệu chỉnh Holm (40 phép kiểm định Welch, $p_{\text{adj}} \le 0,022$). Tuy nhiên, F1 lớp hiếm `Toxic` (2,5% dữ liệu huấn luyện) của ED (`83,28%` PhoBERT) thấp hơn SMART (`85,35%`) và Single-task (`85,32%`); do đó `Toxic` chỉ dùng hỗ trợ rà soát, không dùng tự động kết luận về người viết.
  - Trên UIT-VSFC (10 seed 42–51, 4 baseline MTL), ED cải thiện rõ Topic Accuracy (`89,71%` PhoBERT, $p_{\text{adj}} \le 0,002$), trong khi Sentiment Accuracy và Macro-F1 không khác biệt có ý nghĩa so với `MTL + MLM` sau hiệu chỉnh Holm ($p_{\text{adj}} \ge 0,121$).
- **Điểm số & kiểm soát con người**: Điểm softmax chưa hiệu chuẩn, không phải xác suất đúng. Nhãn người duyệt (`confirmed`/`corrected`) lưu tách biệt với dự đoán AI gốc và không tự huấn luyện lại model.
- **Quyền dữ liệu**: Dữ liệu và weights local nằm trong thư mục gitignore; kiểm tra quyền tái phân phối trước khi công khai dataset mẫu.

## Product Principles

1. Đưa người dùng tới dữ liệu và thao tác cần làm; phần nghiên cứu đứng sau công việc chính.
2. Giữ rõ nguồn của nhãn: model dự đoán, nhãn tham chiếu, hay người dùng đã xác nhận.
3. Cho phép tìm, rà soát, sửa và xuất kết quả; không chỉ hiển thị biểu đồ.
4. Hiển thị trung thực trạng thái model, giới hạn tiền xử lý, lỗi dữ liệu và tiến độ thực; không dùng kết quả giả.
5. Giữ dữ liệu local theo mặc định và giữ đường mở rộng khi có nhu cầu.
