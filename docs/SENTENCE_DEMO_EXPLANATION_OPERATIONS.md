# Vận hành diễn giải kết quả

Classifier chạy local; câu phản hồi và snapshot kết quả được gửi tới dịch vụ diễn giải ngoài khi phân tích thành công. Dịch vụ này là tùy chọn, không thay classifier. Không cấu hình vẫn khởi động API, đọc health, phân loại và quản lý dataset được.

Ứng dụng đọc environment khi tạo API/provider. Không có loader `.env`. Trong PowerShell dùng để khởi động API, thay mọi placeholder sau bằng thông tin gateway cung cấp:

```powershell
$env:FEEDBACK_EXPLANATION_BASE_URL = '<GATEWAY_BASE_URL>'
$env:FEEDBACK_EXPLANATION_API_KEY = '<API_KEY>'
$env:FEEDBACK_EXPLANATION_MODEL = '<MODEL_ID_FROM_GATEWAY>'
$env:FEEDBACK_EXPLANATION_TIMEOUT_SECONDS = '20'
```

Base URL `https://<gateway-host>` được nối `/v1/chat/completions`; URL `https://<gateway-host>/v1` được nối `/chat/completions`. URL đã kết thúc bằng `/chat/completions` cũng được giữ nguyên. Dùng URL và model id đúng tài khoản gateway, không đoán alias. Không đặt key trong `VITE_*`, frontend, source, screenshot hoặc log. Timeout mặc định 20 giây, khoảng cấu hình 1–120 giây, bao gồm cả thời gian chờ slot.

Sau khi đổi cấu hình, người vận hành cần khởi động lại API từ shell có các biến mới rồi reload trang. Một API đã chạy không tự nhận biến environment vừa đặt trong shell khác. `scripts/start-local.ps1` kế thừa environment từ shell gọi nó; nếu ứng dụng đang chạy thì script giữ tiến trình đó. Việc restart một phiên đang dùng cần do người vận hành chủ động thực hiện. Phiên sửa code ngày 11/11/2026 không dừng server người dùng hay gọi gateway/model thật.

Trong demo, “Thử lại diễn giải” giữ prediction và không tạo classifier job. Lỗi 503 có link tới `#/help` và nút thử lại; cấu hình chưa đúng sẽ tiếp tục báo chưa cấu hình. Lỗi upstream trả thông điệp kiểm soát: xác thực/response không hợp lệ là 502, quá tải 429, timeout 504. Không có diễn giải mẫu dự phòng.

Quick source được lưu tạm 15 phút sau terminal. Bản mới có marker nguồn do server tạo; kết quả tạm từ phiên bản cũ chưa có marker cần phân tích lại. Sensitivity không tự lưu câu sang dataset bền. Hết TTL/xóa nguồn làm kết quả phụ thuộc mất hiệu lực; 410 chỉ dùng khi storage còn biết thời hạn, dữ liệu đã xóa trả 404. Nút thêm câu chỉ lưu text explicit và cần phân tích riêng trong dataset để có provenance mới.

Cache diễn giải/coalescing nằm trong một API process, tối đa 100 kết quả và không vượt TTL nguồn; tối đa 2 upstream đang chạy, hàng chờ hữu hạn. Cache key gồm snapshot, prompt/policy và fingerprint cấu hình provider; không có secret thô trong key. Một HTTP subscriber hủy không đồng nghĩa upstream đã hủy hoặc làm hỏng subscriber còn lại. Không cam kết dedupe phân tán nhiều API process.

Lớp 3 dùng phạm vi phiên bản hiện tại và hiển thị run đã resolve. Summary/items cùng token đọc từ SQLite snapshot; thay run/revision/review làm token cũ bị từ chối và UI tải lại summary. Nhãn effective thay đổi cả khi run không đổi, nên chỉ pin run id chưa đủ. Thứ tự ưu tiên theo số phản hồi Negative; Toxic đếm riêng, không phải Negative. Điểm softmax và tín hiệu review chưa hiệu chuẩn; diễn giải không phải suy luận nội bộ hay bằng chứng nhân quả của classifier.

Kiểm thử mặc định dùng `TestOnlyRegistry`, các registry C1 và provider double/`httpx.MockTransport` trong runtime/port riêng. Kết quả này kiểm chứng hợp đồng phần mềm và cách đóng gói prompt; không chứng minh độ đúng ngữ nghĩa hoặc chống prompt injection của model ngoài.
