# NEU-ESC Feedback Workspace

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Người dùng giao quyền đề xuất công nghệ, đang cân nhắc JavaScript và Python. Đề xuất ngày 2026-11-05: TypeScript + React cho giao diện; Python + FastAPI + PyTorch/Transformers cho suy luận; SQLite cho dữ liệu local. Đây là lựa chọn trong kế hoạch, chưa phải stack đã triển khai.

## Users

- Đã xác nhận: người dùng muốn một công cụ sử dụng được, ưu tiên hơn việc thuyết trình; slide đã có.
- Đã xác nhận: chạy trên máy cá nhân trước, có thể đưa lên web sau.
- Chưa xác nhận người vận hành cuối cùng là giảng viên, trợ giảng, cán bộ đào tạo hay thành viên nhóm nghiên cứu. Kế hoạch lấy người cần đọc và tổng hợp nhiều phản hồi sinh viên làm đối tượng thiết kế tạm thời.

## Product Purpose

Đề xuất công cụ giúp nhập phản hồi tiếng Việt, tự động gán nhãn cảm xúc và chủ đề, tìm nhóm phản hồi cần quan tâm, kiểm tra/sửa kết quả, rồi xuất dữ liệu để sử dụng tiếp.

Luồng hoàn chỉnh được đề xuất: tạo bộ phản hồi → nhập dữ liệu → phân tích → lọc/tổng hợp → rà soát → xuất kết quả. Báo cáo nghiên cứu là tab phụ, không phải trang chủ.

## Positioning

Dự án gốc tái lập mô hình phân loại đồng thời sentiment/topic trên NEU-ESC, cải tiến bằng Ensemble Distillation (ED), và huấn luyện/đánh giá thêm trên UIT-VSFC. ED chuyển thông tin từ ensemble giáo viên sang một student; khi triển khai chỉ cần student đã huấn luyện.

## Operating Context

- Repo hiện là code nghiên cứu Python, notebook, CSV và báo cáo; chưa có web app, HTTP API hoặc checkpoint fine-tune để phục vụ câu mới.
- Thông tin máy được kiểm tra ngày 2026-11-05: AMD Ryzen 7 PRO 5850U, khoảng 30,8 GiB RAM, GPU tích hợp AMD Radeon. Kế hoạch local lấy CPU làm mặc định; chưa đo latency.
- Nội dung phản hồi và kết quả xử lý ở local trong phiên bản đầu; không cần gửi văn bản cho API LLM bên ngoài.
- Huấn luyện và xuất artifact là tác vụ riêng, không chạy trong request web.

## Capabilities and Constraints

- NEU: 4 lớp cảm xúc, 10 chủ đề thảo luận sinh viên; UIT: 3 lớp cảm xúc, 4 chủ đề đánh giá đào tạo. Hai hệ nhãn và hai checkpoint riêng; không hoán đổi.
- Dữ liệu sẵn có chỉ có `text`, `sentiment`, `classification`. Không có trường thời gian, giảng viên, môn học hoặc khoa để mặc định tạo các thống kê đó.
- Checkpoint tốt nhất hiện chỉ nằm trong RAM khi train; phải bổ sung xuất/nạp artifact trước khi bật suy luận thật.
- ViSoBERT dùng raw text. PhoBERT dùng processed text; công cụ xử lý NEU gốc chưa xác định đầy đủ. Kế hoạch ưu tiên ViSoBERT ED để đưa raw text vào công cụ local trước, không khẳng định nhanh hơn khi chưa đo.
- Điểm softmax không phải xác suất đúng đã được hiệu chuẩn. Điểm benchmark trung bình nhiều seed không phải chất lượng bảo đảm của một câu hoặc một checkpoint.
- Kết quả người dùng sửa phải lưu riêng với dự đoán gốc; thao tác sửa không tự huấn luyện lại model.
- Repo có mâu thuẫn thông tin quyền tái phân phối dataset. Bản public cần kiểm tra quyền trước khi đưa toàn văn dataset mẫu lên mạng.

## Evidence on Hand

- `src_baseline/`: pipeline tái lập, kiểm tra và tổng hợp thí nghiệm.
- `src_improvement/`: ED, OOF teachers, runner hỗ trợ hai dataset, phân tích logit bias.
- `data/NEU/`: 32.966 câu raw, 3 split; `data/UIT-VSFC/`: 16.175 câu, raw và processed.
- `reports/`: thống kê baseline, ED, UIT và bias; `reports/draft_paper.md` là bản nháp, không phải nguồn để sao chép mọi kết luận không kiểm tra.
- Không có `runs/`, weights fine-tune, OOF teacher artifact hoặc logits cấp câu trong checkout được kiểm tra.
- Bản đọc dự án và kế hoạch chi tiết: `docs/PROJECT_UNDERSTANDING.md`, `docs/WEB_APP_DEMO_PLAN.md`.

## Product Principles

1. Đưa người dùng tới dữ liệu và thao tác cần làm; phần nghiên cứu đứng sau công việc chính.
2. Giữ rõ nguồn của nhãn: model dự đoán, nhãn tham chiếu, hay người dùng đã xác nhận.
3. Cho phép tìm, rà soát, sửa và xuất kết quả; không chỉ hiển thị biểu đồ.
4. Hiển thị trạng thái thiếu model, lỗi dữ liệu và tiến độ thực; không thay bằng kết quả giả.
5. Giữ dữ liệu local theo mặc định và giữ đường nâng cấp lên web khi có nhu cầu.
