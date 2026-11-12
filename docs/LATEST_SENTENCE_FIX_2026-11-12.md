# Sửa thống kê và mạng từ theo câu mới nhất · 12/11/2026

> Cập nhật tiếp: phần donut đếm nhãn trong báo cáo lịch sử này đã được thay bằng tỷ trọng contribution của chính văn bản. Xem [CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md](CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md). Scope summary/network/evidence vẫn theo quick source mới nhất.

## Yêu cầu và nguyên nhân

Người dùng thấy mục “Bộ phản hồi” và “Mạng từ” không đổi khi nhập câu mới. Nguyên nhân: prediction/attribution đọc quick-analysis của câu nhập, còn summary/network/evidence đọc một durable dataset khác được tự chọn từ danh sách. “Kiểm chứng Codex · model thật” là fixture do lượt kiểm E2E trước tạo, không phải dữ liệu người dùng nhập.

Người dùng đã chọn rõ **chỉ câu mới nhất**, không cộng dồn. Luồng hiện hành được đổi như sau:

- `SentenceDemo.tsx` lấy scope từ `item.dataset_id` và `currentRunId` của quick prediction mới nhất hợp lệ. Summary kiểm dataset/run/source/total1; network dùng cùng run, evidence gắn cùng snapshot. Query keys tách từng nguồn; response A đến sau B không làm đổi B.
- Không tự chọn dataset bền. Bỏ dataset selector và hai nút chọn nguồn nhãn của dataset trong demo; câu quick dùng nhãn AI nguồn. Mục và navigation đổi thành **Câu vừa phân tích**.
- Bỏ toàn bộ khối **Lưu câu vào bộ phản hồi**, cùng handler/state/API mutation liên quan trong demo. Workspace nhập/review/export nhiều câu giữ nguyên.
- Nhập/sửa/xóa/chuyển profile hoặc gửi câu mới bỏ scope trước. Khi chưa có prediction hợp lệ, thống kê/network không hiện dữ liệu của câu cũ.
- Donut đếm nhãn của đúng1 câu: nhãn được dự đoán chiếm100% theo số câu; không dùng điểm softmax làm tỷ lệ thống kê. Điểm softmax của model vẫn ở phần prediction trên cùng.
- Đã gỡ5 dataset fixture đúng tên và đúng4 văn bản do lượt kiểm trước tạo trong **preview-runtime của phiên**, qua API xóa dataset. Trước khi xóa đã kiểm runtime và nội dung từng bộ; bản ghi lưu tại `test-results/latest-sentence-fix-20261112/removed-codex-fixtures.json`. Không sửa các dataset khác, model hay database live.
- Test model thật nay dùng quick source tạm, không tạo dataset “Kiểm chứng Codex” bền nữa.

## Kiểm thử

| Kiểm | Kết quả |
|---|---|
| `npm --prefix apps/web run build` | PASS; TypeScript/Vite; JS `index-C9HtFjJn.js` 449.038 kB, CSS `index-XjAdAfYw.css` 69.884 kB. [HTTP asset check](../test-results/latest-sentence-fix-20261112/served-build.json) khớp byte với build local |
|4 file E2E liên quan lần đầu |58 passed,2 failed; hai failures test harness: click tâm lỗ donut và query network thiếu frozen run_id; đã sửa thao tác/params, giữ assertions dữ liệu |
| R08/R09 chạy lại |2 passed; [XML](../test-results/latest-sentence-fix-20261112/overview-network.xml) |
| Full E2E lần đầu |145 passed, 1 failed, 683.90s; [XML](../test-results/latest-sentence-fix-20261112/e2e-before-wait-fix.xml). Một timeout mặc định 5 giây khi chờ prediction B, đã chẩn đoán và sửa test wait |
| File scope sau sửa test wait |9 passed, 25.27s; [XML](../test-results/latest-sentence-fix-20261112/scope-wait.xml) |
| Full E2E cuối |146 passed, 638.23s, không skip; [XML](../test-results/latest-sentence-fix-20261112/e2e.xml) |
| Browser + checkpoint thật offline |1 passed, 38.12s, không skip; [XML](../test-results/latest-sentence-fix-20261112/real-browser.xml), [identity/dữ liệu](../test-results/latest-sentence-fix-20261112/real-browser-evidence.json); không lỗi JavaScript |

Regression mới kiểm: A→B thay scope; summary A trả muộn; donut1/1 và topic thuộc B; graph B không giữ từ “wifi” chỉ có trong A; node/cạnh/community membership chỉ item B; keyboard chọn node/cộng đồng mở đúng server evidence B; clear/profile reset; summary/network/items của dataset bền không bị đọc vào demo, dữ liệu bền không bị thay đổi bởi thao tác phân tích nhanh. Multirow/review/pagination/stale409 vẫn kiểm ở API workspace thay vì buộc giao diện demo giữ selector đã bỏ.

Ca timeout trong lượt full đầu không có lỗi nguồn: DB test riêng cho thấy job B đã `completed` sau 4,592547 giây; UI còn chờ lượt polling kế tiếp (chu kỳ 1 giây). Test scope này không đặt SLA 5 giây, nên chờ prediction B tối đa 20 giây, vẫn giữ toàn bộ assertions về A trả muộn, nhãn/văn bản/count của B và dataset bền. [Chẩn đoán](../test-results/latest-sentence-fix-20261112/e2e-wait-diagnosis.json) lưu thời điểm job; không dùng timeout để bỏ qua assertion dữ liệu.

Lệnh tái kiểm dùng môi trường có sẵn, không cài lại dependencies:

```powershell
npm --prefix apps/web run build
$env:SENTENCE_DEMO_SCREENSHOT_DIR='F:\DPL_NEU-ESC\test-results\latest-sentence-fix-20261112\test-double'
.\.venv\Scripts\python.exe -m pytest tests/e2e -q --tb=short --junitxml=test-results/latest-sentence-fix-20261112/e2e.xml
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:FEEDBACK_FIX_APP_URL='http://127.0.0.1:18765'
$env:FEEDBACK_FIX_RUNTIME='F:\DPL_NEU-ESC\test-results\codex-fix-20261112\preview-runtime'
$env:FEEDBACK_FIX_EVIDENCE='F:\DPL_NEU-ESC\test-results\latest-sentence-fix-20261112'
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_attribution_live_browser.py -q --tb=short --junitxml=test-results/latest-sentence-fix-20261112/real-browser.xml
```

## Bằng chứng giao diện

Các ảnh có prefix `real-` dùng checkpoint NEU thật offline, API và worker trong runtime riêng. Đã trực tiếp mở xem ảnh desktop/mobile của toàn trang và mạng từ. Bảng bốn cột, highlight hai chiều và Tổng đóng góp theo yêu cầu của Đạt được giữ; mobile đặt tổng sau các dòng.

| Nội dung | Ảnh |
|---|---|
| Toàn trang, không còn selector/lưu câu |[Desktop](../test-results/latest-sentence-fix-20261112/real-page-desktop.png), [mobile](../test-results/latest-sentence-fix-20261112/real-page-mobile.png) |
| Mạng từ chỉ câu thư viện mới nhất |[Desktop](../test-results/latest-sentence-fix-20261112/real-network-desktop.png), [390 px](../test-results/latest-sentence-fix-20261112/real-network-mobile.png), [320 px](../test-results/latest-sentence-fix-20261112/real-network-320.png) |
| Dẫn chứng server đúng câu mới nhất |[Dẫn chứng](../test-results/latest-sentence-fix-20261112/real-network-evidence.png) |
| Bảng trọng số và trạng thái |[Polarity](../test-results/latest-sentence-fix-20261112/real-polarity-1440.png), [mobile mở đủ](../test-results/latest-sentence-fix-20261112/real-table-390-expanded.png), [Toxic](../test-results/latest-sentence-fix-20261112/real-intended-toxic.png), [loading](../test-results/latest-sentence-fix-20261112/real-prediction-loading-attribution.png), [unsupported](../test-results/latest-sentence-fix-20261112/real-unsupported-truncation.png), [hết hạn](../test-results/latest-sentence-fix-20261112/real-source-expired-error.png) |

Ảnh trong `test-double/` dùng TestOnlyRegistry để điều khiển race/layout; không được dùng làm bằng chứng model thật. Các giới hạn checkpoint UIT và độ ổn định thứ hạng K=8 trong [báo cáo trước](CODEX_WEBAPP_FIX_REPORT_2026-11-12.md) vẫn áp dụng; lượt sửa này không đổi backend hay thuật toán attribution.

Health cuối xác nhận đúng preview-runtime, schema 4 và worker alive; API không còn fixture Codex. SHA-256 của 13 file model nguồn và bản copy, manifest và current pointer vẫn khớp mốc trước sửa. [health-integrity.json](../test-results/latest-sentence-fix-20261112/health-integrity.json) lưu kết quả kiểm. Bằng chứng model thật có 5 lượt phân tích; graph cuối có 7 từ, 15 liên kết, source/scope đều đúng 1 câu.

Tổng hợp kết quả máy đọc được: [final-evidence-summary.json](../test-results/latest-sentence-fix-20261112/final-evidence-summary.json). Kiểm cuối `git diff --check` đạt; mọi link bằng chứng trong tài liệu này có file đích. Giữ nguyên các thay đổi có sẵn trong workspace, không commit/push/deploy.

## Test case người dùng có thể thử

| Bước | Thao tác | Kết quả cần thấy |
|---|---|---|
|1|Nhập `Wifi phòng học rất chậm, máy tính thường xuyên treo.` rồi Phân tích|Prediction/bảng, thống kê1/1, network và dẫn chứng đều thuộc câu này |
|2|Thay bằng `Thư viện rộng rãi, phòng đọc yên tĩnh và bàn ghế sạch sẽ.` rồi Phân tích|Dẫn chứng chỉ còn câu thư viện; graph không giữ node wifi từ bước1; vẫn1/1, không cộng thành2 |
|3|Chọn node hoặc cộng đồng rồi mở dẫn chứng|Chỉ đúng câu mới nhất, count1; không ra4 câu fixture cũ |
|4|Bấm Xóa hoặc đổi hệ nhãn|Bỏ biểu đồ/network/evidence cũ; không tự hiện bộ dữ liệu khác |
|5|Reload app khi chưa phân tích|Không có “Kiểm chứng Codex”, bộ chọn dataset hoặc khối lưu câu; hiện hướng dẫn nhập câu |

Nhãn model thực tế có thể khác ý nghĩa người viết dự định; kiểm scope/nguồn và sự cập nhật, không ép model ra một nhãn định sẵn.

App: [http://127.0.0.1:18765/#/demo](http://127.0.0.1:18765/#/demo). Dữ liệu kiểm trong `F:\DPL_NEU-ESC\test-results\latest-sentence-fix-20261112`; runtime app vẫn là `test-results/codex-fix-20261112/preview-runtime`. Không commit/push/deploy, không thay model.
