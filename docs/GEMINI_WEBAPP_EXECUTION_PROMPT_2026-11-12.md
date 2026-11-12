# Prompt mở chat thực thi Gemini

Bạn đang triển khai webapp tại `F:\DPL_NEU-ESC` trên Windows/PowerShell. Hãy đọc và thực thi:

`F:\DPL_NEU-ESC\docs\GEMINI_WEBAPP_IMPLEMENTATION_HANDOFF_2026-11-12.md`

Đọc thêm phân tích ảnh:

`F:\DPL_NEU-ESC\docs\TEAMMATE_FEEDBACK_IMAGE_ANALYSIS_PLAN_2026-11-12.md`

Chuẩn UI mới nhất:

- `F:\DPL_NEU-ESC\design-previews\2026-11-12\index.html`
- `F:\DPL_NEU-ESC\design-previews\2026-11-12\styles.css`
- `F:\DPL_NEU-ESC\design-previews\2026-11-12\reference-table-desktop.png`
- `F:\DPL_NEU-ESC\design-previews\2026-11-12\analysis-mobile.png`

Mục tiêu quan trọng nhất: bám góp ý của teammate Đạt. Bỏ chữ thừa, ba nút câu mẫu, nhãn/khối lớp 1/2/3 và tích hợp LLM. Chỉ bỏ câu phụ “Văn bản gốc luôn được giữ nguyên”; giữ nguyên văn phản hồi và kết quả prediction local. Triển khai bảng bốn cột gần ảnh: Phản hồi / Từ quan trọng / Trọng số cảm xúc / Tổng đóng góp. Giữ header xanh, màu xanh đậm/đỏ nghiêng cho hướng tích cực/tiêu cực, các thanh đo nhỏ, highlight chọn qua lại với bảng và phần cách tính mở rộng. Với Neutral/Toxic, target/chú giải/màu phải theo quy tắc riêng trong handoff, không gọi tăng điểm Toxic là tích cực. Không đưa copy dài trở lại.

Hình 1 và 2 là P0 bắt buộc. Donut, thống kê topic và dẫn chứng là P1. Mạng đồng xuất hiện từ là P2. Làm theo thứ tự, không để biểu đồ phụ trì hoãn bảng bắt buộc. Tiếp tục tới khi phần đã được cho phép hoàn tất; nếu có blocker thật, nêu chính xác và hoàn thành phần độc lập.

Báo riêng P0/P1/P2 và có bằng chứng cho R01–R09. Không dùng “hoàn tất toàn bộ” khi phần bổ sung chưa làm; cũng không xem P0 đã đạt là thất bại chỉ vì P2 còn blocker.

Mọi số production phải có nguồn thật. Mockup chỉ chứa fixtures, không được copy làm kết quả dự đoán hoặc attribution. Kiểm chứng nhỏ thuật toán local trước: mapping raw tiếng Việt/BPE, prediction parity, phép cộng đóng góp và chi phí CPU. Shapley là phương án đề xuất, không phải mục tiêu nghiên cứu bắt buộc; không được cộng delta che từng từ để giả tổng attribution. Nếu cần đổi sang lexical scoring, phải trình bày khác biệt semantics thay vì âm thầm gọi nó là trọng số PhoBERT.

Trước khi phân công, chốt contract và các gate M0 trong handoff: snapshot server là chuẩn cho spans/hash, nhóm không chồng lấp, không tô phần từ model chưa đọc, baseline/tổng/target phân biệt, ngưỡng parity/additivity và ngân sách CPU được đo. Tổng cộng khớp không chứng minh giải thích đúng ngữ nghĩa. Cache phải kiểm lại nguồn; idempotency/cancel theo từng handle, xử lý request trả muộn và source expiry; attribution không làm thay đổi run prediction nguồn. Không bỏ qua các chi tiết này để chỉ hoàn thiện giao diện.

Được phép và nên dùng subagent nếu tăng chất lượng, theo ownership và các đợt trong handoff: root giữ contract/API/storage/worker integration; một worker engine/mapping; một worker UI; reviewer đọc-only kiểm kết quả. Không để nhiều agent cùng sửa shared files hoặc đồng thời chạy model nặng. Nói rõ với từng worker rằng họ không làm việc một mình và không được revert sửa đổi của người khác. Nếu không có công cụ subagent, làm tuần tự, không giả lập báo cáo reviewer.

Trước khi sửa, kiểm git status và hướng dẫn repo. Bảo toàn plan/mockup có thể đang untracked. Không đụng live database, model weights, user edits; không commit/push/deploy. Giữ framework và các route/luồng dataset, review, export hiện tại.

Hãy bắt đầu bằng khảo sát ngắn và kế hoạch thực thi, rồi thực sự triển khai. Không dừng ở đề xuất. Khi hoàn tất, bàn giao report theo R01–R09, build/tests, bằng chứng model thật, screenshots và URL webapp. Phân biệt rõ test doubles, các phần còn thiếu và giới hạn; không gọi mockup hoặc test bị skip là triển khai thành công.
