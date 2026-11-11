# Chạy Feedback Workspace trên Windows

Ứng dụng React + FastAPI + SQLite chạy cùng origin tại `http://127.0.0.1:8765`.
Trình duyệt đóng không xóa dữ liệu hoặc hủy công việc của worker. Ngày hiển thị là ngày nhập vào ứng dụng, không phải ngày sinh viên viết phản hồi.

## Cài và chạy

Cần Python 3.10+ (khuyến nghị bản đã kiểm 3.10.11), Node.js 22+ và npm.
Mở PowerShell ở thư mục repo:

```powershell
.\scripts\setup-local.ps1
.\scripts\start-local.ps1
```

Nếu PowerShell chặn script theo policy của máy, có thể chạy từng lệnh qua:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-local.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1
```

Script cài dependency API từ `requirements-api.lock.txt` (khóa cả dependency gián tiếp trên Windows/Python 3.10), ML/preprocessing (`torch`, `transformers`, `safetensors`, `sentencepiece`, `underthesea==9.5.0`) và test từ `requirements-model.lock.txt`/`requirements-test.lock.txt` khi chọn, chuẩn bị sẵn `config.json` của `vinai/phobert-base-v2` vào `runtime\cache\phobert-base-v2` (chỉ tải file cấu hình nhỏ, không tải weights pretrained), và frontend bằng `npm ci` với `package-lock.json`, rồi build assets cục bộ. Để import checkpoint PhoBERT local (`demo\model.pt`) cho profile NEU (offline sau khi chuẩn bị config) và kiểm tra trạng thái, xem [MODEL_WORKFLOW.md](MODEL_WORKFLOW.md):

```powershell
.\scripts\setup-local.ps1 -WithModelRuntime -WithTests
.\.venv\Scripts\python.exe scripts\model_prepare_phobert.py --out runtime\cache\phobert-base-v2 --source demo
.\.venv\Scripts\python.exe scripts\model_import_phobert.py --source demo --encoder-config runtime\cache\phobert-base-v2 --model-root runtime\models --profile neu
.\.venv\Scripts\python.exe scripts\model_status.py --model-root runtime\models --profile neu --load
```

Khi đã có dữ liệu NEU đã chuẩn bị (`data\cache\neu`), có thể chạy kiểm chứng đối chiếu bổ sung (kết quả lưu trong `runtime\models\neu\versions\<version>\verification.json` và file `--report-out` nếu chỉ định):

```powershell
.\.venv\Scripts\python.exe scripts\model_import_phobert.py --source demo --encoder-config runtime\cache\phobert-base-v2 --data-dir data\cache\neu --model-root runtime\models --profile neu --report-out runtime\validation\phobert-neu-verification.json
```

Tùy chọn `-ReuseInstalledPackages` tạo venv dùng các package đã cài trên máy; chỉ dùng khi chủ động muốn tái sử dụng môi trường hiện hữu. Lần setup đầu cần mạng để cài dependency; inference sau khi có bundle dùng file local, không gọi API LLM hay tải backbone tự động.

Khởi động dùng `.venv\Scripts\python.exe`, bind loopback, chạy một API và một worker riêng. Worker có khóa chống trùng. Script kiểm PID/thời điểm tạo và cổng trước khi chạy. Chạy lại script khi app đang chạy sẽ hiện URL hiện tại.

```powershell
.\scripts\stop-local.ps1
.\scripts\start-local.ps1 -Port 8766
```

Đổi nơi lưu bằng `-RuntimeDirectory 'D:\FeedbackData'` cho cả start/stop. Biến `FEEDBACK_RUNTIME` dùng khi chạy Python trực tiếp. Tránh đồng thời hai API dùng hai cổng nhưng cùng dữ liệu nếu không có nhu cầu; một worker đã đủ cho bản local.

## Luồng sử dụng

1. Tạo bộ phản hồi, chọn **Thảo luận sinh viên** (NEU) hoặc **Đánh giá đào tạo** (UIT). Profile cố định; sao chép sang bộ mới để đổi loại, chỉ sao chép văn bản và metadata.
2. Dán từng dòng hoặc nhập CSV UTF-8 có/không BOM. Xem preview, chọn cột văn bản. CSV hỗ trợ dấu phẩy/chấm phẩy/tab và newline đã quote. Dòng trùng được giữ. Dòng lỗi cần sửa hoặc chủ động bỏ qua; tối đa 500 phản hồi, 5 MB/file, 5.000 ký tự/văn bản.
3. Cột nhãn chỉ thành nhãn tham chiếu sau khi chọn cột, map giá trị theo schema và xác nhận nguồn. Chúng không thay dự đoán AI và không làm đầu vào model.
4. Phân tích khi profile có bundle hợp lệ (`neu` dùng PhoBERT MTL-ED với tách từ nội bộ `underthesea 9.5.0`, giữ nguyên văn bản gốc trong SQLite và CSV xuất; `uit` chưa có checkpoint nên chỉ dùng nhập/rà soát thủ công). Worker lưu tiến độ từng batch, hủy giữa batch, retry phần chưa xong; kết quả đã commit vẫn giữ khi restart.
5. Tìm/lọc, xem bảng **Chủ đề cần chú ý** (`TopicAttention` theo `Nguồn nhãn`: `Đã duyệt nếu có, còn lại AI` hoặc `Chỉ dự đoán AI gốc`, kèm mẫu số `eligible/filtered`, nhãn `Ít dữ liệu` khi `n < 5`, `Toxic` đếm tách riêng, và nút bấm lọc nhanh các câu Tiêu cực của từng chủ đề), lọc theo **Tín hiệu model** (`review-signals-v1`, ngưỡng heuristic *thử nghiệm, chưa hiệu chuẩn* tách riêng với cờ **Đầu vào bị cắt ngắn**), mở chi tiết để thử nghiệm độ nhạy tại mục **Khám phá dự đoán** (thử bỏ một cụm từ trên bản gốc, tính lại cặp gốc/biến thể trên cùng model bằng hàng đợi ưu tiên `priority=1`, TTL 15 phút, giới hạn 4 job chạy đồng thời / 10 lần trong 60 giây, không ghi đè dữ liệu gốc), và duyệt riêng cảm xúc/chủ đề. Sửa một task không xác nhận task còn lại. Nhãn AI gốc và giá trị số tín hiệu được giữ riêng (tín hiệu chỉ đối chiếu trạng thái hàng chờ theo từng tác vụ). Khi xem run khác, sửa ghi chú giữ nguyên nhãn và prediction nguồn đã xác nhận; nút **Xác nhận dự đoán đang xem** chủ động chọn nguồn mới. Nếu bản duyệt thay đổi ở tab khác, bản nháp được giữ và nút Lưu bị khóa: đối chiếu bản server rồi chọn **Tải bản server, bỏ bản nháp** hoặc **Áp lại bản nháp trên bản server**, sau đó Lưu. Refetch không tự nâng revision của bản nháp.
6. Xuất toàn bộ hoặc đúng phần lọc. CSV UTF-8 BOM đọc được bằng Excel Windows, có AI/reference/review/run/version và warnings riêng (giữ nguyên các cột CSV hiện có; không thêm cột mới cho tín hiệu hay thử nghiệm độ nhạy). `selected_run_id` là run chọn cho bản xuất; `run_id`/model từng dòng chỉ có khi prediction khớp revision đó. `prediction_status` cho biết `processed`, `failed` hoặc `unprocessed`; văn bản mới sửa/thêm chưa phân tích không mang model provenance cũ. Chọn run lịch sử sẽ xuất đúng văn bản/revision của run đó. File đã tạo là snapshot, không thay đổi khi tiếp tục sửa.

Điểm mô hình là điểm softmax, chưa được hiệu chuẩn thành xác suất đúng. Chính sách `review-signals-v1` (`services/review_policy.json`, công khai qua `/api/v1/review-policy`) là ngưỡng thử nghiệm chưa hiệu chuẩn để ưu tiên rà soát, không phát hiện được mỉa mai; thử nghiệm độ nhạy trong `Khám phá dự đoán` phản ánh phản ứng của mô hình khi đầu vào thay đổi và luôn gắn cảnh báo phi nhân quả. Model chỉ đọc tối đa 128 token; chi tiết và file xuất đánh dấu truncation. Không dùng thống kê nhiều seed trong tab báo cáo để bảo đảm chất lượng từng câu mới.

## Lưu trữ và backup

`runtime/` được gitignore; chứa `workspace.sqlite3`, file exports, models và log vận hành. Migrations có version trong `services/storage/` (hiện tại **schema v2**, bổ sung `jobs.priority`, `sensitivity_experiments` và `sensitivity_rate_limits`). Không tự sửa schema SQLite bằng tay. Xóa bộ phản hồi chỉ xóa dữ liệu/file thuộc bộ đó (kể cả dataset tạm của thử nghiệm độ nhạy gắn với bộ nguồn); không xóa weights và reports dùng chung.

Sao lưu bằng công cụ dưới đây dùng SQLite online backup để giữ tính nhất quán. Bản sao loại dữ liệu thử nhanh có TTL; không chứa weights. Lưu/copy model bundle riêng nếu cần chuyển máy. Không sao chép riêng file `.sqlite3` khi đang chạy WAL.

```powershell
.venv\Scripts\python.exe scripts\backup_local.py backup --runtime runtime --output backups\feedback-2026-11-06.zip
.\scripts\stop-local.ps1
.venv\Scripts\python.exe scripts\backup_local.py restore --archive backups\feedback-2026-11-06.zip --runtime runtime-restored
.\scripts\start-local.ps1 -RuntimeDirectory "$PWD\runtime-restored"
```

Restore chỉ vào thư mục đích mới, không ghi đè dữ liệu có sẵn. Bản sao có toàn văn phản hồi: giữ trong nơi lưu trữ do bạn quản lý. Các job còn dang dở trong backup được recover/retry khi worker mở lại; cần bundle đúng model/version để tiếp tục. Runtime thử một câu có TTL 15 phút sau kết thúc. Worker cleanup định kỳ mỗi 30 giây kể cả khi hàng chờ luôn bận hoặc inference dài, thường xóa trong tối đa 35 giây sau TTL; tranh chấp khóa SQLite có thể làm chậm thêm. Job đang chờ/chạy được bảo vệ. Câu đã chủ động thêm vào bộ phản hồi bền được giữ lại độc lập với bản tạm.

## Kiểm thử và phát triển

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest tests\e2e -q
cd apps\web
npm.cmd run dev
```

Vite proxy `/api` tới API ở cổng 8765. Bản build do FastAPI phục vụ cùng origin; không cần CORS mở. Test doubles nằm riêng trong tests, chỉ kiểm hành vi phần mềm. Chúng không chứng minh inference của student ED đã fine-tune. Xem `VALIDATION_REPORT.md` để biết chính xác các lệnh và giới hạn đã kiểm trong phiên triển khai.
