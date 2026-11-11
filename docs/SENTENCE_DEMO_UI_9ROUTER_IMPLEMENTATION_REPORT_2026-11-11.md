# Báo cáo Triển khai UI Demo Phân tích câu và Diễn giải 9router

Ngày: 2026-11-11  
Môi trường thực thi: Windows 10/11, Python 3.10.11, Node.js v20.18.0  
Kho mã nguồn: `F:\DPL_NEU-ESC` (nhánh `webapp`, baseline HEAD `36e4f8e1b905912f98b270ec1e675b3624a0cf3f`)  
Kế hoạch tham chiếu: `F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_GEMINI_PLAN_2026-11-11.md`  
Thư mục evidence: `C:\Users\Admin\AppData\Local\Temp\neu-esc-sentence-ui-20261111-evidence`

---

## 1. Tóm tắt Thực thi (Executive Summary)

Đã hoàn thành chuyển đổi bản vẽ mockup bố cục 2 (`design-previews/2026-11-11/sentence-demo-v2.html`, `.css`) thành màn hình React production-ready hoạt động trực tiếp với backend cục bộ của NEU-ESC, đáp ứng đầy đủ kiến trúc 3 lớp:

1. **Lớp 1 (Dự đoán AI cục bộ)**: Tiếp nhận câu tiếng Việt đơn lẻ, chạy suy luận trực tiếp bằng student PhoBERT MTL-ED cục bộ; hiển thị ngay lập tức khi hoàn tất với đầy đủ nhãn cảm xúc và phân bố xác suất softmax 10 chủ đề (profile NEU) hoặc 4 chủ đề (profile UIT) kèm cảnh báo điểm số chưa hiệu chuẩn.
2. **Lớp 2 (Tín hiệu Review, Diễn giải & Độ nhạy)**:
   - Hiển thị ngay cờ nghi ngờ/cắt ngắn cục bộ (`review_signals`) từ kết quả phân loại.
   - Tự động kích hoạt gọi API diễn giải qua backend (`POST /api/v1/quick-analysis/{job_id}/explanation`) tới cổng 9router/OpenAI-compatible gateway với trạng thái loading thanh mảnh, không gây gián đoạn hay chặn đọc Lớp 1.
   - Hiển thị nội dung `reading` ("Cách đọc kết quả này") và `caution` ("Điểm cần lưu ý") đã qua kiểm duyệt vệ sinh dữ liệu, kèm nút "Thử diễn giải lại" độc lập (không chạy lại model).
   - Tích hợp công cụ Khám phá độ nhạy (`SensitivityPanel`) để thử nghiệm che/thay đổi từ ngữ trực tiếp trên câu phản hồi.
3. **Lớp 3 (Gợi ý Ra quyết định)**: Đọc số liệu thống kê thực từ API bộ phản hồi được chọn (`/datasets/{id}/summary` và `/datasets/{id}/items`); hiển thị thẻ "Chủ đề cần chú ý" (tỷ lệ tiêu cực cao nhất), phân bố chủ đề và danh sách mẫu phản hồi có phân trang; tuyệt đối không dùng số liệu giả lập.
4. **Bảo toàn hồi quy (Preservation)**: Toàn bộ 46 bài test E2E baseline và 98 bài test unit/API baseline tiếp tục **pass 100%**. Tuyến đường mới `#/demo` được bổ sung hài hòa, trong khi các tuyến đường cũ (`#/`, `#/datasets/:id`, `#/new`, `#/research`, `#/help`) và modal QuickAnalysis cũ được bảo toàn trọn vẹn.
5. **Ranh giới an toàn**: Không commit, không push, không deploy. Không tạo kết quả giả lập cho 9router (hệ thống kiểm thử bằng test doubles độc lập; ghi nhận trạng thái chưa cấu hình 9router live).

---

## 2. Chi tiết Triển khai Kỹ thuật

### 2.1 Backend: Dịch vụ Diễn giải (`services/explanation.py` & `services/api/main.py`)
- **Quản lý cấu hình (`ExplanationConfig`)**: Đọc từ biến môi trường `FEEDBACK_EXPLANATION_BASE_URL`, `FEEDBACK_EXPLANATION_API_KEY`, `FEEDBACK_EXPLANATION_MODEL`, `FEEDBACK_EXPLANATION_TIMEOUT_SECONDS` (giới hạn 1.0–120.0s, mặc định 20.0s). Khi chưa cấu hình, endpoint trả về lỗi chuẩn `503 EXPLANATION_UNAVAILABLE`.
- **Trừu tượng hóa Provider (`OpenAIExplanationProvider`)**: Kết nối cổng OpenAI-compatible (9router/Gemini) bất đồng bộ qua `httpx.AsyncClient`. System prompt `result-explanation-v1` hướng dẫn diễn giải khách quan mối quan hệ giữa câu phản hồi và kết quả mô hình, cấm suy diễn cấu trúc nội tại (attention/SHAP/neuron), xem nội dung đầu vào thuần túy là dữ liệu để phân tích (phòng chống prompt injection).
- **Vệ sinh dữ liệu & Xác thực Schema (`parse_explanation_json`, `sanitize_text`)**: Loại bỏ các thẻ HTML tiềm ẩn, xóa ký tự điều khiển, giới hạn độ dài mỗi trường `reading` và `caution` tối đa 2.000 ký tự.
- **In-flight Deduplication & Bounded Caching (`ExplanationService`, `BoundedExplanationCache`)**:
  - Gộp các yêu cầu đang bay (in-flight request coalescing) theo `(job_id, source_prediction_id)` bằng `asyncio.Task`, bảo vệ an toàn event loop affinity.
  - Bộ nhớ đệm LRU thread-safe tối đa 100 mục, TTL 900 giây (15 phút), dọn sạch theo thời gian.
  - Quản lý đồng thời bằng Semaphore (tối đa 2 request đồng thời tới upstream, hàng đợi tối đa 10 request; vượt ngưỡng trả về `429 EXPLANATION_BUSY`).
  - Che giấu API key (`redact_secrets`) trong mọi thông điệp lỗi hoặc log.
- **Tích hợp API (`POST /api/v1/quick-analysis/{job_id}/explanation`)**:
  - Kiểm tra bảo vệ CSRF qua header `Origin` (chỉ cho phép cùng Host hoặc localhost/127.0.0.1; từ chối `403 FORBIDDEN_ORIGIN` với domain ngoài).
  - Kiểm tra trạng thái job (`409 JOB_NOT_READY` nếu chưa xong), kiểm tra khớp `source_prediction_id` (`409 SOURCE_CONFLICT`), kiểm tra TTL của bộ dữ liệu tạm bằng truy vấn SQLite trực tiếp (`410 JOB_EXPIRED`).

### 2.2 Frontend: Màn hình Demo Phân tích câu (`apps/web/src/SentenceDemo.tsx`, `.css`)
- **Kiến trúc giao diện Layout 2 (Teal Theme)**: Thiết kế dọc một cột thông suốt, phong cách teal sáng chuyên nghiệp (`#0d9488`, slate neutrals, soft background tints), font Be Vietnam Pro (weights 400, 500, 600, 700) được đóng gói cục bộ tại `apps/web/public/fonts/` kèm giấy phép `OFL.txt`, không tạo bất kỳ network request nào ra Google Fonts bên ngoài.
- **Thanh điều hướng**: Header gọn gàng với brand NEU-ESC, nút quay lại "Quản lý bộ dữ liệu" (`#/`) và "Báo cáo nghiên cứu" (`#/research`).
- **Khung nhập liệu**: Ô textarea toàn chiều rộng với bộ đếm ký tự (tối đa 1.000 ký tự), 3 nút câu mẫu ("Dịch vụ sinh viên", "Khảo sát giảng viên", "Cơ sở vật chất") nạp văn bản mẫu vào ô nhập mà không tự động submit (tuân thủ tiêu chuẩn U02), nút "Xóa nội dung" và nút "Phân tích câu" có cờ kiểm tra tính sẵn sàng của mô hình.
- **Lớp 1 (Kết quả Phân loại)**:
  - Hiển thị nhãn chính cảm xúc và chủ đề nổi bật kèm tỷ lệ phần trăm.
  - Danh sách phân bố chi tiết toàn bộ các lớp xác suất: 10 chủ đề của NEU hoặc 4 chủ đề của UIT với thanh track phần trăm và số điểm rõ ràng.
  - Ghi chú cảnh báo khoa học về điểm số softmax chưa được hiệu chuẩn xác suất.
- **Lớp 2 (Tín hiệu Review, Diễn giải & Độ nhạy)**:
  - Tín hiệu model cục bộ: Thẻ `LOW_TOP1` (điểm cao nhất thấp), `SMALL_MARGIN` (chênh lệch top 1 và top 2 hẹp), `TRUNCATED` (câu bị cắt ngắn trên 128 token).
  - Tự động gọi API diễn giải khi phân tích hoàn tất; hiển thị thanh tiến trình loading dạng sóng không làm mờ hay chặn tương tác Lớp 1.
  - Quản lý trạng thái bất đồng bộ chống stale response bằng generation ID counter và `AbortController`.
  - Hiển thị hai khối nội dung rõ ràng: "Cách đọc kết quả này" và "Điểm cần lưu ý".
  - Nút "Thử diễn giải lại" cho phép gọi lại LLM khi lỗi mạng hoặc lỗi cấu hình mà không làm mất kết quả classifier Lớp 1.
  - Tích hợp component `SensitivityPanel` cho phép chọn hoặc nhập cụm từ để so sánh điểm số mô hình giữa câu gốc và câu biến thể.
- **Lớp 3 (Gợi ý Ra quyết định)**:
  - Dropdown chọn bộ phản hồi cùng profile trong không gian làm việc.
  - Khi chưa chọn, hiển thị empty state hướng dẫn chọn bộ dữ liệu.
  - Khi đã chọn: Nạp dữ liệu thực từ `/api/v1/datasets/{id}/summary` và `/items`. Hiển thị thẻ nổi bật "Chủ đề cần chú ý" (chủ đề có số lượng và tỷ lệ phản hồi tiêu cực cao nhất), biểu đồ phân bố chủ đề, danh sách phản hồi mẫu có phân trang và nút "Xem trong không gian làm việc".
  - Nút "Thêm câu này vào bộ dữ liệu" để đưa ngay phản hồi vừa phân tích vào dataset đang xem.

### 2.3 Quản lý Phụ thuộc & Định tuyến (Routing)
- Bổ sung `httpx==0.28.1` vào `requirements-api.txt` và cập nhật khóa phiên bản trong `requirements-api.lock.txt` bằng công cụ chuẩn `scripts/lock_dependencies.py`.
- Tuyến đường `#/demo` được đăng ký trong `App.tsx` phục vụ component `SentenceDemo`. Tuyến đường gốc `#/` và `""` bảo toàn không gian làm việc bộ dữ liệu và danh sách phản hồi, giải quyết triệt để xung đột hồi quy với bộ test E2E C1 cũ. Sidebar bổ sung mục "Phân tích một câu" (`#/demo`) đồng thời duy trì modal QuickAnalysis cũ ("Thử một câu").

---

## 3. Kết quả Kiểm thử Toàn diện

Toàn bộ các bộ kiểm thử đã được chạy và xác nhận đạt **100% PASS**:

### 3.1 Build Frontend & Lint
- `npm run build --prefix apps/web`:
  - TypeScript biên dịch không lỗi (`tsc -b`).
  - Vite build production thành công (`dist/assets/index-CnxH-gRA.js` 428.63 kB, `dist/assets/index-CO6CUar9.css` 59.33 kB).
- `git diff --check`: 0 cảnh báo whitespace hoặc định dạng dòng.

### 3.2 Unit & API Tests (127/127 Passed)
Lệnh chạy: `python -B -X utf8 -m pytest tests/api tests/test_review_signals.py tests/test_sensitivity_selection.py tests/test_runtime_isolation.py tests/test_explanation.py -q`
- `tests/test_explanation.py` (22/22 tests mới):
  - Kiểm tra `ExplanationConfig`: đọc biến môi trường, xác thực timeout, giới hạn biên độ.
  - Kiểm tra `parse_explanation_json` & `sanitize_text`: parse JSON chuẩn, bóc tách markdown codeblock, chặn HTML tags, xử lý malformed JSON.
  - Kiểm tra `OpenAIExplanationProvider`: build prompt chống injection, mock HTTP client, xử lý mã lỗi upstream 429, 401, 502, che dấu secret.
  - Kiểm tra `BoundedExplanationCache`: LRU eviction, TTL expiry, deepcopy isolation.
  - Kiểm tra `ExplanationService`: in-flight task deduplication, concurrency semaphore & queue limit, timeout mapping.
  - Kiểm tra `explain_quick_job`: xác thực job completed, khớp source prediction, từ chối dataset hết hạn.
- `tests/api/test_explanation_endpoint.py` (7/7 tests mới):
  - HTTP 503 khi chưa cấu hình provider/env.
  - HTTP 200 xác thực toàn bộ schema Section 6.1 khi inject stub provider.
  - HTTP 409 `JOB_NOT_READY` khi job đang ở hàng đợi.
  - HTTP 409 `SOURCE_CONFLICT` khi sai `source_prediction_id`.
  - HTTP 410 `JOB_EXPIRED` khi temporary dataset hết hạn TTL.
  - HTTP 403 `FORBIDDEN_ORIGIN` khi Origin đến từ trang web lạ; HTTP 200 khi Origin cùng host hoặc không có Origin.
  - In-flight deduplication (2 request đồng thời chỉ gọi upstream 1 lần) và bounded cache hit cho request thứ 3.
- Baseline API & Unit tests (98/98 tests): Pass 100% không hồi quy.

### 3.3 E2E Playwright Tests (53/53 Passed)
Lệnh chạy: `python -B -X utf8 -m pytest tests/e2e -q` (Thời gian chạy: 327.45s)
- `tests/e2e/test_sentence_demo.py` (7/7 tests mới trên route `#/demo`):
  - **U01**: Trạng thái ban đầu rỗng, nút phân tích disabled, không gọi API ngầm; responsive trên cả 1440px và 390px.
  - **U02**: Bấm câu mẫu "Dịch vụ sinh viên" chỉ nạp text, không tự submit; bấm nút phân tích mới tạo job.
  - **U03**: Hiển thị đầy đủ 10 chủ đề của NEU với nhãn, thanh track % và nhãn điểm số; không tràn ngang trang.
  - **U04**: Lớp 1 hiển thị ngay khi phân tích xong; Lớp 2 hiện trạng thái "Đang diễn giải…" không chặn tương tác Lớp 1; sau đó hiển thị nội dung `reading` và `caution`.
  - **U07**: Nút "Xóa nội dung" và đổi profile dọn sạch kết quả phân tích cũ.
  - **U09**: Chuyển sang profile UIT (model chưa sẵn sàng) hiển thị banner cảnh báo và disable nút phân tích.
  - **U14/U15**: Lớp 3 kết nối bộ phản hồi đã phân tích, hiển thị phân bố chủ đề và chủ đề có phản hồi tiêu cực cao nhất từ dữ liệu thực.
- `tests/e2e/test_regressions.py` (9/9 tests baseline): Pass 100% (gồm cả 4 biến thể phân cách tệp r7: tab, comma, semicolon, pipe).
- `tests/e2e/test_three_layer_demo.py` (20/20 tests baseline): Pass 100%.
- `tests/e2e/test_three_layer_review_fixes.py` (13/13 tests baseline): Pass 100%.
- `tests/e2e/test_workspace.py` (4/4 tests baseline): Pass 100% (missing model, import/export CSV, mobile review revisions, keyboard navigation).

---

## 4. Visual QA & Danh sách Screenshots

Toàn bộ ảnh chụp màn hình kiểm tra trực quan được lưu tại thư mục:  
`C:\Users\Admin\AppData\Local\Temp\neu-esc-sentence-ui-20261111-evidence\screenshots\`

| Tệp Screenshot | Viewport | Trạng thái mô tả |
| :--- | :---: | :--- |
| `01_desktop_empty_state_1440.png` | 1440x900 | Desktop khởi tạo: Ô nhập rỗng, Lớp 1 và Lớp 3 hiển thị empty state hướng dẫn. |
| `02_desktop_sample_selected_1440.png` | 1440x900 | Desktop sau khi bấm câu mẫu: Văn bản đã được điền, nút phân tích sẵn sàng, chưa gửi job. |
| `03_desktop_layer2_loading_1440.png` | 1440x900 | Desktop bất đồng bộ: Lớp 1 đã có kết quả dự đoán, Lớp 2 đang hiển thị trạng thái "Đang diễn giải…". |
| `04_desktop_analysis_complete_1440.png` | 1440x900 | Desktop hoàn tất: Hiển thị đầy đủ 10 chủ đề, cảm xúc, cờ review và hai đoạn diễn giải kết quả. |
| `05_desktop_uit_unavailable_1440.png` | 1440x900 | Desktop UIT: Banner cảnh báo model UIT chưa sẵn sàng, nút phân tích bị vô hiệu hóa. |
| `06_desktop_layer3_dataset_1440.png` | 1440x900 | Desktop Lớp 3: Thống kê bộ phản hồi thực tế, thẻ Chủ đề cần chú ý và biểu đồ phân bố. |
| `07_mobile_empty_state_390.png` | 390x844 | Mobile khởi tạo: Giao diện responsive 1 cột, không bị tràn ngang. |
| `08_mobile_analysis_complete_10_topics_390.png` | 390x844 | Mobile hoàn tất: 10 chủ đề hiển thị sắc nét dọc màn hình, thanh track và nhãn không bị đè. |
| `09_mobile_uit_unavailable_390.png` | 390x844 | Mobile UIT: Trạng thái cảnh báo model trên thiết bị di động. |
| `10_mobile_layer3_dataset_390.png` | 390x844 | Mobile Lớp 3: Khung thống kê bộ phản hồi trên điện thoại. |

---

## 5. An toàn & Ranh giới Dịch vụ

1. **Bảo mật Khóa & Che giấu Secret**:
   - Không chứa bất kỳ API key, secret hay thông tin xác thực nào trong git tree, manifest hay tài liệu evidence.
   - Hàm `redact_secrets` trong `services/explanation.py` chủ động tìm và thay thế chuỗi API key bằng `[REDACTED]` trong mọi thông báo lỗi và log.
2. **Phòng chống Tấn công Injection & CSRF**:
   - System prompt thiết lập ranh giới cứng: văn bản người dùng chỉ là dữ liệu, cấm thực thi câu lệnh tiềm ẩn bên trong phản hồi.
   - Kiểm tra `Origin` trong `services/api/main.py` ngăn chặn việc các trang web độc hại từ trình duyệt kích hoạt endpoint diễn giải.
   - Hàm `sanitize_text` bóc tách toàn bộ thẻ HTML, ngăn chặn mã độc XSS hiển thị trong React UI.
3. **Minh bạch về Tình trạng 9router Live**:
   - Trong phiên làm việc này, môi trường local chưa được cấp API key hay Base URL thực tế của 9router.
   - Toàn bộ kết quả kiểm thử được thực hiện qua các test double trung thực (`StubExplanationProvider`, `E2EMockExplanationProvider`).
   - Giao diện người dùng thể hiện rõ ràng khi dịch vụ diễn giải chưa được cấu hình (kèm nút thử lại), tuyệt đối không sinh ra diễn giải giả mạo để lừa dối người dùng.

---

## 6. Danh mục Bằng chứng (Evidence Manifest)

Thư mục: `C:\Users\Admin\AppData\Local\Temp\neu-esc-sentence-ui-20261111-evidence`
- `baseline.json`: Snapshot HEAD baseline (`36e4f8e1b905912f98b270ec1e675b3624a0cf3f`), trạng thái git ban đầu và SHA-256 các tệp cốt lõi.
- `manifest-after.json`: Bảng băm SHA-256 của toàn bộ 22 tệp bị sửa đổi hoặc mới tạo trong phiên thực thi.
- `implementation.delta.diff`: Bản diff đầy đủ bao gồm thay đổi tracked và toàn bộ mã nguồn của các tệp mới tạo.
- `preservation-verification.json`: Bản ghi xác thực bảo toàn 100% hồi quy cho các bộ test C1 cũ và các tuyến đường ứng dụng.
- `test-results.json`: Bảng tổng hợp chi tiết kết quả chạy kiểm thử cho build frontend, unit tests, API tests và E2E tests.
- `observations.json`: Tổng hợp các phát hiện kỹ thuật quan trọng và quyết định kiến trúc trong quá trình triển khai.
- `qa-review.md`: Báo cáo đánh giá độc lập của QA Subagent.
- `screenshots/`: 10 tệp ảnh chụp PNG ghi nhận toàn bộ các trạng thái giao diện theo kế hoạch.
