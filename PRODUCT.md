# NEU-ESC Feedback Workspace

<!-- impeccable:product-schema 1 -->

## Platform

web (local-first loopback on Windows)

## Stack

Đã triển khai cục bộ trên nhánh `webapp`:
- **Giao diện**: TypeScript + React 19 + TanStack Query + TanStack Table + Vite (`apps/web/`, build tĩnh được FastAPI phục vụ cùng origin tại `http://127.0.0.1:8765`). Tuyến đường mặc định `#/demo` phục vụ giao diện Demo Phân tích câu 3 lớp; các tuyến đường quản lý bộ dữ liệu (`#/`, `#/datasets/:id`), nhập liệu (`#/new`), nghiên cứu (`#/research`) và trợ giúp (`#/help`) được bảo toàn đầy đủ.
- **API & Worker**: Python 3.10 + FastAPI + Uvicorn (`services/api/`) và tiến trình worker suy luận độc lập (`services/worker.py`).
- **Dịch vụ diễn giải 9router (Tùy chọn)**: `services/explanation.py` tích hợp OpenAI-compatible gateway (9router/Gemini) để tự động diễn giải kết quả sau phân tích câu. Thiết kế bảo vệ: in-flight coalescing, cache LRU 100 mục (TTL 15 phút), giới hạn đồng thời (semaphore 2 upstream), kiểm tra Origin chống CSRF, lọc mã độc/HTML và che dấu API key trong log/lỗi. Không can thiệp vào suy luận cục bộ; nếu chưa cấu hình thì hiển thị thông báo hướng dẫn thay vì giả lập kết quả.
- **Suy luận & Tiền xử lý**: PyTorch CPU FP32 + Transformers (`use_fast=False`, `max_length=128`) + `underthesea==9.5.0` (tách từ offline cho PhoBERT).
- **Lưu trữ**: SQLite WAL cục bộ (`runtime/workspace.sqlite3`, schema v2 với hàng đợi ưu tiên và thử nghiệm độ nhạy TTL 15 phút) và bundle model phân phiên bản (`runtime/models/`).

## Users

- Công cụ làm việc cục bộ cho giảng viên, trợ giảng, cán bộ đào tạo hoặc nhóm nghiên cứu cần nhập phản hồi sinh viên tiếng Việt, phân loại cảm xúc và chủ đề, rà soát các trường hợp cần chú ý và xuất CSV.
- Chạy trên máy cá nhân trước (loopback `127.0.0.1`). Classifier và dữ liệu quản lý chạy local; khi phân tích câu thành công, câu và kết quả được gửi tới dịch vụ diễn giải ngoài nếu đã cấu hình. Hướng dẫn: `docs/SENTENCE_DEMO_EXPLANATION_OPERATIONS.md`.

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
- **Khả năng 3 tầng trên giao diện làm việc (`T01–T11`)**:
  - **Demo Phân tích câu 3 lớp (`#/demo`)**: Trải nghiệm phân tích nhanh theo luồng dọc (Layout 2, giao diện màu teal, font Be Vietnam Pro):
    + **Lớp 1 (Kết quả dự đoán AI)**: Phân loại trực tiếp bằng student PhoBERT MTL-ED cục bộ; hiển thị cảm xúc, chủ đề và toàn bộ phân bố xác suất softmax 10 chủ đề (NEU) hoặc 4 chủ đề (UIT), kèm cảnh báo điểm số chưa hiệu chuẩn.
    + **Lớp 2 (Tín hiệu review, Diễn giải & Độ nhạy)**: Hiển thị ngay cờ nghi ngờ/cắt ngắn cục bộ (`review_signals`); tự động kích hoạt tiến trình diễn giải qua 9router/OpenAI-compatible gateway (`services/explanation.py`) theo định dạng `reading` và `caution` tiếng Việt an toàn; tích hợp panel thử nghiệm độ nhạy để so sánh baseline và biến thể khi che/sửa từ.
    + **Lớp 3 (Gợi ý ra quyết định)**: Đọc số liệu thống kê thực từ API bộ phản hồi được chọn; hiển thị chủ đề có phản hồi tiêu cực cao nhất, phân bố cảm xúc/chủ đề, danh sách phản hồi mẫu có phân trang và nút mở bộ dữ liệu trong không gian làm việc; không sử dụng số liệu giả lập.
  - **Prediction & Decision Support (`Chủ đề cần chú ý`)**: Tổng hợp động theo bộ lọc hiện hành và lựa chọn nguồn nhãn (`Đã duyệt nếu có, còn lại AI` vs `Chỉ dự đoán AI gốc`), sắp xếp giảm dần theo số câu Tiêu cực, hiển thị mẫu số đủ hai nhãn, gắn cờ `Ít dữ liệu` (`n < 5`, quy ước hiển thị), đếm tách riêng `Toxic`, và lọc thẳng danh sách phản hồi tiêu cực theo chủ đề.
  - **Interpretability — Tín hiệu model (`review-signals-v1`)**: Cờ heuristic *thử nghiệm, chưa hiệu chuẩn* (`LOW_TOP1`, `SMALL_MARGIN`) tính từ điểm softmax gốc, tách riêng theo cảm xúc/chủ đề và tách biệt với cảnh báo **Đầu vào bị cắt ngắn** (`> 128` token). Giữ nguyên dấu hiệu gốc sau khi rà soát; chỉ cập nhật trạng thái đối chiếu ở hàng chờ tín hiệu.
  - **Interpretability — Khám phá dự đoán (`Sensitivity Exploration`)**: Cho phép chọn hoặc nhập cụm từ nguyên văn trên văn bản gốc (an toàn ranh giới Unicode/NFD/emoji qua UTF-16) để chạy lại cặp `baseline` vs `variant` bất đồng bộ trên đúng model identity và chế độ `cpu-fp32-eval`, hiển thị bảng chênh lệch điểm trên **cùng tập nhãn** với cảnh báo giới hạn phi nhân quả và cảnh báo cắt ngắn; không sửa hay ghi đè văn bản nguồn, nhãn duyệt hoặc bản chụp CSV.
- **Điểm số & kiểm soát con người**: Điểm softmax chưa hiệu chuẩn, không phải xác suất đúng; thử nghiệm độ nhạy không phải bằng chứng nhân quả hay phân bổ trọng số token (`attribution`). Nhãn người duyệt (`confirmed`/`corrected`) lưu tách biệt với dự đoán AI gốc và không tự huấn luyện lại model.
- **Quyền dữ liệu**: Dữ liệu và weights local nằm trong thư mục gitignore; kiểm tra quyền tái phân phối trước khi công khai dataset mẫu.

## Product Principles

1. Đưa người dùng tới dữ liệu và thao tác cần làm; phần nghiên cứu đứng sau công việc chính.
2. Giữ rõ nguồn của nhãn: model dự đoán, nhãn tham chiếu, hay người dùng đã xác nhận.
3. Cho phép tìm, rà soát, sửa và xuất kết quả; không chỉ hiển thị biểu đồ.
4. Hiển thị trung thực trạng thái model, giới hạn tiền xử lý, lỗi dữ liệu và tiến độ thực; không dùng kết quả giả.
5. Giữ dữ liệu local theo mặc định và giữ đường mở rộng khi có nhu cầu.
