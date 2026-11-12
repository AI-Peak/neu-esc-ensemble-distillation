# Review bản triển khai Gemini ngày 12/11/2026

Phạm vi: code đang thay đổi trong `F:\DPL_NEU-ESC`, báo cáo nghiệm thu của Gemini và log người dùng gửi. Đối chiếu với `GEMINI_WEBAPP_IMPLEMENTATION_HANDOFF_2026-11-12.md` và mockup đã duyệt. Đây là review, chưa sửa implementation.

**Kết luận:** đã có phần triển khai thực tế và bảng bốn cột, nhưng chưa đủ điều kiện đánh dấu toàn bộ P0/P1/P2 PASS. Có lỗi trong luồng sử dụng thường ngày, tính đúng nguồn attribution và đối chiếu dẫn chứng. Mức P1/P2 trong findings bên dưới chỉ độ nghiêm trọng của lỗi, không phải các giai đoạn sản phẩm cùng tên trong plan.

## Các lỗi cần sửa trước nghiệm thu

### F01 — P1: Target của NEU Neutral và Negative bị đảo

- Vị trí: `apps/web/src/SentenceDemo.tsx:329`.
- Code giả định ID 0 là Negative, ID 2 là Neutral. `services/profiles.json:2` quy định ID 0 là Neutral, ID 2 là Negative.
- Hậu quả: câu Neutral được giải thích theo polarity; câu Negative lại dùng label score. Màu/chú giải và ý nghĩa trọng số không đúng contract đã duyệt.
- Đã tái hiện bằng browser test với test server: prediction Neutral nhưng POST gửi `{kind: "polarity_margin"}`.
- Sửa bằng cách resolve sentiment key từ profile, so sánh không phân biệt hoa thường, rồi chọn target. Kiểm riêng cả bốn nhãn NEU và ba nhãn UIT.

### F02 — P1: Attribution của câu cũ có thể ghi đè câu mới

- Vị trí: `apps/web/src/SentenceDemo.tsx:373`.
- Sau `await createAttribution`, code ghi state/ref mà không kiểm generation hoặc source còn hiện hành; response completed cũng không được kiểm identity trước render.
- Đã tái hiện bằng cách giữ POST câu A, hoàn tất câu B rồi trả response A: textarea là “Học phí quá cao.” nhưng dòng từ trong bảng là “Nhân viên” của câu A.
- Cần generation ownership cho cả success/failure của POST, polling và retry; ID trả muộn của tác vụ bị bỏ phải được cancel. Kiểm source/target/hash/spans/số hữu hạn trước render.

### F03 — P1: Unsupported và lỗi polling làm giao diện loading mãi

- Vị trí: `apps/web/src/SentenceDemo.tsx:290`, `apps/web/src/SentenceDemo.tsx:303`.
- Polling chỉ dừng ở completed/failed/cancelled. Không xử lý unsupported hoặc query error 404/410/network error.
- Worker trả unsupported cho input bị truncation hoặc mapping không hỗ trợ, nên đây là đường chạy thực tế. Browser repro: trả unsupported, sau 3,5 giây có 4 GET, spinner vẫn hiện và lý do không xuất hiện.
- Cần dừng polling, hiện thông báo ngắn và recovery thích hợp; prediction vẫn được giữ. Không retry vô hạn nguồn đã hết hạn.

### F04 — P1: Worker không ràng buộc model/điểm attribution với prediction nguồn

- Vị trí: `services/worker.py:236`, `services/worker.py:298`; metadata nguồn được dựng lại tại `services/storage/db.py:1414`.
- Worker lấy bundle hiện hành rồi bỏ qua identity/manifest được trả về. Không so full-input scores với prediction nguồn. Coalition checkpoint chỉ gắn với job và mask, không có identity phương pháp/model để bảo vệ resume.
- `validate_quick_source` kiểm tính hợp lệ của bản prediction đã lưu; nó không chứng minh model vừa chạy coalition là model tạo prediction đó.
- Repro bằng registry double trong runtime tạm: đổi model_version sau prediction; attribution vẫn completed và báo phiên bản cũ. Target prediction là 0, target attribution là 52,006; residual vẫn 0. Đây là bằng chứng thiếu kiểm nguồn, không phải benchmark model thật.
- Cần freeze execution identity, kiểm trước mỗi batch/resume và publication, kiểm parity full-input với nguồn; không trộn coalition của các identity khác nhau. Cache cũng phải xét method/grouping/baseline/identity.

### F05 — P1: Network và dẫn chứng có thể thuộc hai snapshot khác nhau

- Vị trí: `apps/web/src/SentenceDemo.tsx:569`, `apps/web/src/SentenceDemo.tsx:595`.
- Membership lấy từ network cache 60 giây nhưng request dẫn chứng gửi scope token của summary. `network.scope_token` không được kiểm.
- Repro API isolated: graph có node “wifi”; sửa phản hồi thành câu không chứa wifi; dùng summary token mới với IDs cũ như UI vẫn nhận 200 và câu mới làm dẫn chứng cho wifi.
- Cần dẫn chứng được ràng buộc vào snapshot network, refresh khi scope đổi; không dùng token mới để hợp thức hóa membership cũ.

## Các lỗi còn lại ảnh hưởng tính đúng và yêu cầu đã chốt

### F06 — P2: Mapping Unicode báo exact dù khớp sai hoặc cắt grapheme

- Vị trí: `services/attribution.py:90`, `services/attribution.py:133`.
- Alignment chỉ kiểm đã tìm được điểm bắt đầu, không kiểm đã khớp hết từ. Với `"Ca\u0309m o\u031bn"` (dạng decomposed của “Cảm ơn”), tokenizer/underthesea thật cho token của cả cụm, nhưng group raw chỉ là “C”, vẫn báo exact.
- `"Tốt 👍🏽"` tạo group riêng cho 👍 và 🏽; emoji ZWJ cũng bị tách. Renderer bọc mỗi group thành button nên ký tự hiển thị bị phá vỡ.
- Cần mapping normalization về raw và kiểm boundary grapheme. Nếu chưa ánh xạ chắc chắn, trả unsupported có lý do thay vì số cho sai span.

### F07 — P2: Markup mới không khớp CSS, giao diện chưa đạt mockup

- Vị trí: `apps/web/src/SentenceDemo.tsx:681`, `apps/web/src/SentenceDemo.tsx:770`, `apps/web/src/SentenceDemo.css:192`, `apps/web/src/SentenceDemo.css:453`.
- Markup dùng `.app-header`, `.input-actions`, `.button-primary`; styles còn nhắm `.site-header`, `.submit-row .primary`. Kích thước SVG nút cũng không được áp dụng.
- Ảnh Gemini bàn giao `artifacts/screenshots_2026_11_12/r04_desktop_attribution_table.png` cho thấy menu dính chữ, nút Phân tích bị xuống nhiều dòng và icon hiển thị bất thường.
- Cần thống nhất selectors, kiểm lại ảnh toàn trang desktop/mobile; chỉ đếm đủ bốn header không chứng minh UI đã đạt.

### F08 — P2: Mobile và thanh tổng nhóm ẩn không đúng quy tắc bảng

- Vị trí: `apps/web/src/SentenceDemo.css:2786`, `apps/web/src/AttributionTable.tsx:238`.
- Mobile cố định tổng ở grid-row 10. Khi “Xem đủ” nhiều hơn tám nhóm, tổng nằm trước những nhóm còn lại.
- “Các từ còn lại” vẫn được vẽ meter dùng mẫu số max của từng nhóm rồi clamp 100%; tổng nhiều nhóm vì thế bị biểu diễn như một nhóm đơn. Handoff quy định dòng này chỉ hiện số, giữ meter cho các nhóm thực.
- Cần vị trí tổng theo số dòng thực tế và bỏ meter của aggregate ẩn.

### F09 — P2: Dẫn chứng dùng nhãn effective khi người dùng chọn nhãn AI

- Vị trí: `apps/web/src/SentenceDemo.tsx:1631`, `apps/web/src/SentenceDemo.tsx:1636`.
- Donut/API filter dùng `label_source=ai`, nhưng badge luôn render `row.effective`.
- Khi người duyệt đổi Negative thành Positive, click lát Negative trong chế độ AI có thể trả hàng hiển thị Positive. Chọn label từ prediction hoặc effective đúng với source hiện hành.

### F10 — P2: Network không đúng population, cửa sổ và thuật toán được công bố

- `services/api/main.py:351`: đưa cả phản hồi chưa có nhãn vào graph. Repro hai câu chưa chạy prediction: donut denominator=0, network source_item_count=2 và có 5 nodes. Contract yêu cầu cùng population có nhãn với donut hoặc công bố rõ khác biệt.
- `services/text_network.py:83`: bỏ stopwords trước khi tính cửa sổ. Repro “Wifi ở trong các phòng thì vẫn cứ bị chậm.” vẫn tạo cạnh wifi–chậm dù cách nhau 9 vị trí token gốc. Cần tính cửa sổ trên vị trí gốc.
- `apps/web/src/TermNetwork.tsx:272`: ghi Louvain/Modularity trong khi `services/text_network.py:123` chỉ chạy connected components. Không có tối ưu modularity/seed như báo cáo. Plan cho phép cách đơn giản, nhưng phải gọi đúng phương pháp.

### F11 — P2: R07 mới dừng gọi LLM trong demo, chưa dọn giao diện vận hành

- Vị trí: `apps/web/src/App.tsx:905`.
- Help vẫn hướng dẫn cấu hình 9router/API key, gửi phản hồi ra dịch vụ ngoài và bấm “Thử lại diễn giải”, dù chức năng này đã bị bỏ khỏi demo và endpoint mặc định trả 410.
- Còn client explanation và service cũ. Cần dọn luồng/help/config hiện hành cùng tests theo contract đã chọn; không sửa lịch sử nghiên cứu.

### F12 — P2: Lệnh chạy trong báo cáo không khởi động webapp

- Vị trí: `docs/GEMINI_WEBAPP_IMPLEMENTATION_REPORT_2026-11-12.md:173`.
- `python -m services.api.main` chỉ tạo đối tượng app; module không gọi uvicorn hoặc chạy worker. Đã thử trong runtime tạm: process thoát mã 0 ngay, không mở server.
- Dùng quy trình đã có trong `docs/LOCAL_APP.md`, ví dụ `scripts/start-local.ps1`, hoặc ghi chính xác hai lệnh API/worker và URL tương ứng. Không khẳng định 8000 là URL đang chạy nếu chưa xác minh.

## Kiểm chứng đã thực hiện

| Kiểm chứng | Kết quả | Giới hạn |
|---|---|---|
| Frontend build | PASS | Không phát hiện lỗi async/semantics/UI bằng TypeScript build |
| Pytest ngoài E2E, không bật real_model | 370 passed, 3 failed, 4 deselected | Các lỗi còn lại ở explanation contract và schema migration version |
| Năm test redesign E2E mới | 5 passed trong 24,92 giây | Server dùng TestOnlyRegistry, không phải bằng chứng UI chạy checkpoint thật |
| Test attribution model thật hiện có | PASS | Chạy trên bản copy bundle đã kiểm hash trong temp; chỉ một câu, một scalar polarity |
| Repro browser target/unsupported/stale POST | Tái hiện được F01/F02/F03 | Điều khiển phản hồi API để kiểm race và terminal state |
| Repro worker model/score mismatch | Tái hiện được F04 | Registry double; xác nhận thiếu validation, không đo độ chính xác model |
| Repro NFD/emoji | Tái hiện được F06 | Tokenizer và underthesea thật; không cần encoder |
| Repro network snapshot/population/window | Tái hiện được F05/F10 | Runtime tạm, không đụng dữ liệu live |

Ba test backend thất bại:

- `tests/api/test_explanation_endpoint.py:83`: còn kỳ vọng 503 trong khi implementation đổi thành 410.
- `tests/api/test_sensitivity.py:634`: còn kỳ vọng database version 2 thay vì 3.
- `tests/api/test_workspace.py:281`: còn kỳ vọng database version 2 thay vì 3.

Đây chủ yếu là tests chưa đồng bộ contract, không tự suy ra database bị hỏng. Tuy nhiên bộ regression chưa xanh nên chưa thể báo nghiệm thu toàn bộ. Đã thử suite E2E cũ rộng hơn và thấy nhiều lỗi; dừng lượt đó do còn nhiều expectation của luồng LLM đã bỏ, nên không báo một tổng kết E2E đầy đủ cho lượt bị dừng.

## Những kết luận trong báo cáo cần hiệu chỉnh

- Ảnh bảng R04 đang hiển thị `TEST-DOUBLE-NOT-A-MODEL` và tất cả trọng số bằng 0; không phải ảnh kiểm chứng đóng góp model thật như người đọc có thể suy ra từ phần mô tả kết quả.
- `tests/inference/test_attribution_real_model.py:65` kiểm scalar polarity, không kiểm hai vector sentiment/topic theo gate M0. Không thể so trực tiếp tolerance scalar điểm phần trăm với tolerance probability vector rồi kết luận gate đầy đủ đã đạt.
- Báo cáo feasibility trình bày 10 câu, chưa đáp ứng yêu cầu ít nhất 20 lượt warm; chưa đủ bằng chứng tái lập cho stability và khẳng định thời gian quick prediction “luôn <350ms”.
- Residual cộng khớp không xác nhận đúng model nguồn, đúng span, đúng target hay độ ổn định Shapley. F01/F04/F06 là các ví dụ cụ thể.
- Không đánh dấu R07/R09 hoàn tất khi help LLM còn nguyên và phương pháp network được ghi khác code.

Các điểm kỹ thuật cần giữ trong danh sách sửa: kiểm target label ID thuộc profile (API hiện nhận -1); queue/deadline/cache limits theo contract; identity khi resume; inference hardcode NEU indices và special token IDs nên phải xử lý đúng hoặc báo unsupported rõ cho UIT; network không chạy NLP nặng trong transaction API; keyboard path cho node desktop.

## Thứ tự xử lý đề nghị cho Gemini

1. Sửa F01–F04 và F06; thêm regression test đúng các tình huống đã tái hiện. Kiểm thật ít nhất một luồng input mới → prediction → attribution → highlight, bao gồm Negative/Neutral/Toxic.
2. Sửa F07–F08; chụp và xem ảnh desktop/mobile với trọng số thật, kiểm mở đủ nhóm và trạng thái unsupported/error.
3. Sửa F05, F09–F10; kiểm chỉnh sửa dữ liệu/nhãn khi graph đang cache, counts/membership và source labels.
4. Dọn F11, sửa F12, cập nhật các tests cũ có chủ đích. Chạy lại suite thích hợp rồi viết lại report với PASS/PARTIAL/BLOCKED và bằng chứng thực tế.

Giữ bố cục bốn cột, thanh đo nhỏ cho từng nhóm, tổng đóng góp và yêu cầu bỏ copy/lớp/LLM của Đạt. Không thay số hoặc hardcode dấu từ để làm ảnh đẹp hay làm test xanh.
