# Đối chiếu từ ngữ trong phân tích câu

Hướng dẫn này thay thế cấu hình dịch vụ diễn giải ngoài kể từ 12/11/2026.
Ứng dụng dùng classifier local cho prediction và attribution. Không cần API key,
gateway hoặc cấu hình LLM. Những biến cấu hình diễn giải từ phiên bản cũ không
kích hoạt provider. Endpoint `/quick-analysis/{job_id}/explanation` giữ để tương thích
và luôn trả `410 EXPLANATION_DISABLED` sau kiểm tra Origin.

Prediction xuất hiện độc lập với bảng từ ngữ. Khi phần từ ngữ chạy, có thể hủy riêng
tác vụ đó; thao tác này không sửa prediction nguồn. Lỗi kết nối có thể thử đọc lại
trạng thái. Nguồn hết hạn cần phân tích lại câu. Unsupported nêu lý do ngắn và
không hiển thị tổng 0 như một kết quả hợp lệ.

Bảng hiển thị ước lượng permutation Shapley trên model nguồn. Positive/Negative
dùng cân bằng điểm tích cực/tiêu cực; Neutral/Toxic dùng điểm của đúng nhãn.
Chọn cụm từ hoặc dòng bảng để đối chiếu, mở **Cách tính tổng** để xem baseline,
đơn vị điểm phần trăm và giới hạn. Không xem trọng số như bằng chứng nhân quả.

Khởi động API cùng worker theo [LOCAL_APP.md](LOCAL_APP.md). Giao ước request,
vòng đời, giới hạn hàng đợi và kiểm nguồn ở
[WEBAPP_ATTRIBUTION_CONTRACT.md](WEBAPP_ATTRIBUTION_CONTRACT.md).
