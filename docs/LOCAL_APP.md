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

Script cài dependency API từ `requirements-api.lock.txt` (khóa cả dependency gián tiếp trên Windows/Python 3.10), ML/test từ các file `requirements-model.lock.txt`/`requirements-test.lock.txt` khi chọn, và frontend bằng `npm ci` với `package-lock.json`, rồi build assets cục bộ. Model chưa có thì vẫn dùng được nhập/lưu/rà soát thủ công/xuất CSV. Để nạp model thật, cài thêm runtime và bundle theo [MODEL_WORKFLOW.md](MODEL_WORKFLOW.md):

```powershell
.\scripts\setup-local.ps1 -WithModelRuntime -WithTests
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
4. Phân tích khi profile có bundle hợp lệ. Worker lưu tiến độ từng batch, hủy giữa batch, retry phần chưa xong; kết quả đã commit vẫn giữ khi restart.
5. Tìm/lọc, bấm biểu đồ để lọc, xem chi tiết và duyệt riêng cảm xúc/chủ đề. Sửa một task không xác nhận task còn lại. Nhãn AI gốc được giữ riêng. Khi xem run khác, sửa ghi chú giữ nguyên nhãn và prediction nguồn đã xác nhận; nút **Xác nhận dự đoán đang xem** chủ động chọn nguồn mới. Nếu bản duyệt thay đổi ở tab khác, bản nháp được giữ và nút Lưu bị khóa: đối chiếu bản server rồi chọn **Tải bản server, bỏ bản nháp** hoặc **Áp lại bản nháp trên bản server**, sau đó Lưu. Refetch không tự nâng revision của bản nháp.
6. Xuất toàn bộ hoặc đúng phần lọc. CSV UTF-8 BOM đọc được bằng Excel Windows, có AI/reference/review/run/version và warnings riêng. `selected_run_id` là run chọn cho bản xuất; `run_id`/model từng dòng chỉ có khi prediction khớp revision đó. `prediction_status` cho biết `processed`, `failed` hoặc `unprocessed`; văn bản mới sửa/thêm chưa phân tích không mang model provenance cũ. Chọn run lịch sử sẽ xuất đúng văn bản/revision của run đó. File đã tạo là snapshot, không thay đổi khi tiếp tục sửa.

Điểm mô hình là điểm softmax, chưa được hiệu chuẩn thành xác suất đúng. Hàng chờ rà soát dùng heuristic; không bảo đảm tìm đủ lỗi. Model chỉ đọc tối đa 128 token; chi tiết và file xuất đánh dấu truncation. Không dùng thống kê nhiều seed trong tab báo cáo để bảo đảm chất lượng từng câu mới.

## Lưu trữ và backup

`runtime/` được gitignore; chứa `workspace.sqlite3`, file exports, models và log vận hành. Migrations có version trong `services/storage/`. Không tự sửa schema SQLite bằng tay. Xóa bộ phản hồi chỉ xóa dữ liệu/file thuộc bộ đó; không xóa weights và reports dùng chung.

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
