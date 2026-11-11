# Bộ dữ liệu minh họa ba lớp (`three_layer_feedback_vi.csv`)

- **Tệp dữ liệu:** [`three_layer_feedback_vi.csv`](file:///f:/DPL_NEU-ESC/data/demo/three_layer_feedback_vi.csv)
- **Mã hóa & định dạng:** CSV UTF-8, 24 dòng, gồm 3 cột `sample_id,text,illustrative` (`illustrative=true`).
- **Nguồn & quyền riêng tư:** Toàn bộ 24 câu là dữ liệu **do người viết tạo để minh họa cho demo** (không lấy từ sinh viên thật, không chứa tên thật, email hay mã sinh viên).
- **Không chứa kết quả model giả:** CSV cố ý không chứa cột nhãn dự đoán (`prediction`) hay điểm số (`scores`); mọi dự đoán và số liệu trình diễn phải được sinh trực tiếp từ lần chạy model thật trong ứng dụng.

## Bảng nhãn tham chiếu đề xuất của tác giả dữ liệu minh họa

> [!NOTE]
> Cột cảm xúc và chủ đề dưới đây là **nhãn tham chiếu đề xuất của tác giả dữ liệu minh họa**, **không** phải kết quả của mô hình AI và **không** được coi là ground truth tuyệt đối cho toàn bộ các câu pha trộn hoặc mỉa mai. Nếu import vào app dưới dạng nhãn tham chiếu, dùng nguồn `"Tác giả dữ liệu minh họa"`; app không bao giờ đưa nhãn tham chiếu vào đầu vào mô hình hoặc thay thế nhãn AI/nhãn người duyệt.

| ID | Cảm xúc tham chiếu (`neu-v1`) | Chủ đề tham chiếu (`neu-v1`) | Ghi chú vai trò minh họa |
|---|---|---|---|
| `D01` | Positive (`1`) | Academic (`2`) | Tích cực, nội dung học tập rõ ràng |
| `D02` | Negative (`2`) | Academic (`2`) | Phản hồi tiêu cực về lịch thi |
| `D03` | Neutral (`0`) | Academic (`2`) | Thông tin trung tính về bài tập |
| `D04` | Negative (`2`) | Academic (`2`) | Cảm xúc pha trộn (khen ích lợi, nặng bài tập) |
| `D05` | Negative (`2`) | Academic (`2`) | Cách diễn đạt mỉa mai; không hứa model phát hiện đúng |
| `D06` | Negative (`2`) | Service (`4`) | Vấn đề dịch vụ cổng đăng ký |
| `D07` | Positive (`1`) | Service (`4`) | Tích cực về nhân viên thư viện |
| `D08` | Negative (`2`) | Service (`4`) | Tiêu cực về thời gian phục vụ nhà ăn |
| `D09` | Neutral (`0`) | Service (`4`) | Thông tin trung tính về giờ mở cửa thư viện |
| `D10` | Negative (`2`) | Service (`4`) | Hai ý trong một phản hồi, giới hạn một chủ đề |
| `D11` | Positive (`1`) | Club & Events (`9`) | Sự kiện câu lạc bộ tích cực |
| `D12` | Negative (`2`) | Club & Events (`9`) | Sự kiện bắt đầu muộn, thiếu thông báo |
| `D13` | Neutral (`0`) | Club & Events (`9`) | Thông tin trung tính về lịch sinh hoạt |
| `D14` | Positive (`1`) | Club & Events (`9`) | Tích cực kèm hạn chế nhẹ |
| `D15` | Positive (`1`) | Jobs & Recruitment (`5`) | Thông tin thực tập tích cực |
| `D16` | Negative (`2`) | Jobs & Recruitment (`5`) | Lo ngại tin tuyển dụng; không tự kết luận lừa đảo |
| `D17` | Neutral (`0`) | Jobs & Recruitment (`5`) | Thông tin trung tính về tuyển dụng |
| `D18` | Neutral (`0`) | Help & Share (`8`) | Câu hỏi thủ tục hành chính |
| `D19` | Positive (`1`) | Help & Share (`8`) | Lời cảm ơn chia sẻ tài liệu |
| `D20` | Negative (`2`) | Help & Share (`8`) | Câu hỏi kèm băn khoăn/tiêu cực nhẹ |
| `D21` | Positive (`1`) | Personal Affairs (`6`) | Chủ đề ít mẫu |
| `D22` | Negative (`2`) | Social Affairs (`7`) | Chủ đề ít mẫu |
| `D23` | Neutral (`0`) | News (`1`) | Tin tức học bổng, ít mẫu |
| `D24` | Toxic (`3`) | Other (`3`) | Minh họa phân biệt `Toxic`, không nhắm vào người thật |

## Giới hạn cần nêu khi sử dụng

1. Trên hệ nhãn **NEU (`neu-v1`)**, nhãn **Ngôn từ độc hại (`Toxic`)** là lớp hiếm (~2,5% dữ liệu huấn luyện), luôn được tách riêng khỏi `Tiêu cực` và chỉ dùng để hỗ trợ người phụ trách rà soát.
2. Pipeline local dùng `underthesea 9.5.0` và độ dài tối đa 128 token (`equivalence=approximate`), nên điểm và nhãn trên văn bản thô có thể khác điều kiện benchmark đã tiền xử lý trong nghiên cứu.
3. Hệ nhãn **UIT (`uit-v1`)** hiện chưa có checkpoint được cài trong runtime; có thể nhập dữ liệu hoặc rà soát thủ công, không có dự đoán AI tự động.
