# Kế hoạch triển khai UI demo và diễn giải qua 9router cho Gemini

Ngày: 2026-11-11. Workspace: `F:\DPL_NEU-ESC`.

Đây là kế hoạch để Gemini triển khai sau khi người dùng giao việc. Tài liệu này chưa phải báo cáo đã triển khai. Đọc toàn bộ trước khi sửa; cuối tài liệu có mẫu prompt bàn giao cho Codex review.

## 1. Kết quả cần giao

Chuyển mockup bố cục 2 đã được người dùng duyệt thành màn React hoạt động với backend hiện có:

1. Nhập một phản hồi tiếng Việt và bấm **Phân tích câu**.
2. Hiện kết quả classifier thật ở lớp 1 ngay khi tác vụ hoàn tất, gồm cảm xúc, chủ đề và các thanh phần trăm.
3. Tự động yêu cầu diễn giải qua backend tới 9router; lớp 2 hiện **Đang diễn giải…** trong khi lớp 1 vẫn đọc được. Không cần bấm nút yêu cầu diễn giải lần đầu.
4. Hiện tín hiệu phân vân, cảnh báo cắt ngắn và thử nghiệm độ nhạy dựa trên chức năng thật đã có.
5. Lớp 3 chỉ thống kê bộ dữ liệu được chọn; có nguồn, mẫu số và đường mở các phản hồi gốc.
6. Giữ đường truy cập quản lý bộ dữ liệu, rà soát, nghiên cứu và xuất CSV hiện tại.

Không được chuyển dữ liệu, timer, điểm số hay nội dung diễn giải viết sẵn trong mockup thành kết quả production.

### Các quyết định người dùng đã chốt

- Style sáng, teal, gọn và chuyên nghiệp; font tiếng Việt đủ lớn.
- Bố cục theo chiều dọc: ô nhập trọn hàng, lớp 1 bên dưới, rồi lớp 2 và lớp 3. Không đặt ô nhập cạnh một panel kết quả dài gây khoảng hở.
- Nhãn UI là **Diễn giải kết quả**; không cần gắn tên LLM hoặc 9router trên card.
- Bỏ mục thông tin mở rộng về cơ chế LLM ở card diễn giải.
- Mỗi lần phân tích thành công mặc định tự gọi diễn giải. Không biến thành tính năng bật/tắt hoặc nút opt-in.
- Có thể dùng subagent khi giúp nâng chất lượng; cách phối hợp ở mục 5.

## 2. Baseline và tài liệu phải đọc

Baseline quan sát khi viết kế hoạch:

- Branch: `webapp`.
- HEAD: `36e4f8e1b905912f98b270ec1e675b3624a0cf3f`.
- Working tree: có thư mục untracked `design-previews/` chứa các bản thiết kế của người dùng.
- Baseline thực thi phải gồm **HEAD + staged + unstaged + untracked lúc bắt đầu**, không lấy riêng HEAD. Nếu HEAD đã tiến, ghi rõ và thích ứng; không reset về hash này.

Tham chiếu thiết kế, theo thứ tự:

| File | Vai trò |
|---|---|
| `F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo-share.html` | Bản độc lập đã gửi người dùng duyệt; chứa CSS, JS và font |
| `F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo-v2.html` | Cấu trúc bố cục 2 |
| `F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo-v2.css` | CSS bố cục; import CSS bản đầu |
| `F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo.css` | Style nền và font |
| `F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo-v2.js` | Chỉ tham khảo tương tác, không dùng data/timer trong production |

SHA-256 của `sentence-demo-share.html` tại thời điểm lập kế hoạch: `60D9091567A93E420195073B6333E4EDDE2B60A2CD6E5665F9B370E91B872690`.

Đọc AGENTS.md nếu tồn tại ở phạm vi áp dụng, `PRODUCT.md`, `DESIGN.md` và các module liên quan. Bản mockup và quyết định mới của người dùng thay thế hướng cobalt/Segoe cùng giả định không có dịch vụ diễn giải ngoài máy trong tài liệu cũ. Cập nhật tài liệu sản phẩm tương ứng khi triển khai; không sửa lịch sử báo cáo C1 để làm như phạm vi này đã có từ trước.

### Bản đồ code đã kiểm tra

Các đường dẫn sau tương đối với `F:\DPL_NEU-ESC`:

| Khu vực | File / hợp đồng hiện tại |
|---|---|
| Điều hướng, shell | `apps/web/src/App.tsx`, hash routing; quick analysis hiện nằm trong modal |
| Thử một câu | `apps/web/src/QuickAnalysis.tsx`; POST `/api/v1/quick-analysis`, poll `/api/v1/jobs/{job_id}` |
| Client và types | `apps/web/src/api.ts`, `apps/web/src/types.ts` |
| Runtime React | `apps/web/src/main.tsx`; có React.StrictMode và TanStack Query |
| Lớp 2 local | `services/review_signals.py`, `services/review_policy.json`, `apps/web/src/SensitivityPanel.tsx` |
| Lớp 3 | `apps/web/src/TopicAttention.tsx`, `services/analytics.py`, summary/items API |
| API | `services/api/main.py`, factory `create_app`; SPA fallback cuối routes |
| Worker/storage | `services/worker.py`, `services/storage/db.py`; quick analysis tạo dataset tạm, TTL 15 phút sau terminal |
| Profile | `services/profiles.json`; NEU: 4 cảm xúc, **10 chủ đề**; UIT: 3 cảm xúc, 4 chủ đề |
| Regression | `tests/api/`, `tests/e2e/`, `tests/test_runtime_isolation.py`, báo cáo C1 |
| Chạy local | `scripts/start-local.ps1`, `scripts/stop-local.ps1`; loopback, API và worker riêng |

`Store.job()` trả `kind=quick` và `result` là một **Item** đối với quick job terminal; Item mang prediction, revision và review signals. Không giả định job result chỉ là một Prediction trần. Terminal không đồng nghĩa thành công: chỉ tự diễn giải khi job completed và prediction hợp lệ.

## 3. Phạm vi và giới hạn thực thi

Được sửa frontend, thêm service/API diễn giải, tests và tài liệu cần thiết. Ưu tiên tái sử dụng luồng quick analysis, review signals, sensitivity và attention hiện có.

- Không huấn luyện, đổi checkpoint, tokenizer, preprocessing, hệ nhãn, ngưỡng review policy hoặc precision của classifier.
- Không thay classifier bằng LLM. LLM chỉ diễn giải kết quả đã tồn tại.
- Không tự commit, push, deploy hoặc xóa dữ liệu/runtime của người dùng.
- Không chạy inference thật hoặc gọi dịch vụ 9router thật trong đợt kiểm thử mặc định. Dùng registry/provider doubles và runtime riêng. Nếu có chỉ thị mới cho smoke thật, ghi riêng phạm vi và kết quả.
- Không tìm key bằng cách quét cấu hình của ứng dụng khác; không ghi key vào báo cáo, source, screenshot, frontend hay log.
- Không bỏ regression hoặc hạ assertion để có báo cáo xanh. Được cập nhật selector/entry route do UI đổi, phải giữ hành vi được kiểm chứng.
- Giữ nguyên các mockup và evidence C1 cũ. Khi có thay đổi không do nhóm thực thi tạo ra giữa chừng, dừng phần có xung đột và phối hợp với người dùng.

## 4. UX và dữ liệu của màn mới

### 4.1 Điều hướng và bố cục

Tạo route `#/demo`. Khi mở app không có hash, mặc định vào demo. Giữ `#/` làm đường tương thích vào danh sách bộ phản hồi, cùng các route `#/datasets/{id}`, `#/new`, `#/research`, `#/help` hiện tại. Header của demo có liên kết sang bộ dữ liệu và nghiên cứu; không có sidebar ở màn demo. Các màn cũ vẫn truy cập được.

Nút “Thử một câu” ở workspace có thể dẫn tới `#/demo`; dùng một implementation của luồng phân tích. Nếu giữ modal để tương thích, phải dùng chung logic/component, không duy trì hai luồng inference độc lập.

Thứ tự và nguyên tắc:

1. Header gọn, tiêu đề và mô tả ngắn.
2. Ô nhập trọn chiều rộng, giới hạn 5.000 ký tự, câu mẫu, nút phân tích và xóa. Câu mẫu chỉ điền input; chỉ bấm Phân tích mới gửi job.
3. Lớp 1: trên desktop cảm xúc và chủ đề cạnh nhau; mỗi bên có nhãn dẫn đầu, điểm và phân bố đầy đủ.
4. Lớp 2: tín hiệu local, diễn giải bất đồng bộ, phần khám phá độ nhạy có thể thu gọn.
5. Lớp 3: chọn bộ dữ liệu, thống kê và drill-down riêng.

Ở NEU thật, cột 10 chủ đề dài hơn cột 4 cảm xúc. Cách xử lý: cho hai nhóm nhãn rộng độc lập, không kéo giãn các hàng cảm xúc hay tạo card rỗng để bằng chiều cao. Có thể chia danh sách 10 chủ đề thành hai cột nhỏ ở màn đủ rộng nếu vẫn đọc rõ nhãn; dưới breakpoint xếp dọc. Mọi nhãn và thanh % phải có sẵn, không giấu sau “xem thêm”. Không rút còn 3 chủ đề như mockup.

Base 16px, văn bản chính 16–18px, chú thích tối thiểu 14px; dùng Be Vietnam Pro local như mockup, kèm license font phù hợp khi đưa vào assets. Không import font từ máy cá nhân hoặc thư mục design-previews ở runtime. CSS mới scope dưới màn demo để tránh phá workspace cũ.

Kiểm tra desktop 1440px, laptop 1280px, tablet 768px, mobile 390px và 320px. Không horizontal body overflow; nhãn dài không đè thanh hoặc phần trăm. Keyboard, focus visible, aria-live cho trạng thái, reduced-motion, tương phản văn bản đều phải hoạt động.

### 4.2 Lớp 1 — Prediction

- Gọi API quick analysis hiện có; dùng job result đúng run/profile/schema.
- Nhãn lấy từ profile và đối chiếu thứ tự scores theo hợp đồng thật. Kiểm chiều dài vector, giá trị hữu hạn và miền điểm; không đổi dữ liệu thiếu thành 0% để che lỗi.
- Giá trị hiển thị = score × 100, định dạng một chữ số thập phân. Sai số làm tròn khiến tổng khác 100,0% là chấp nhận được; không tự chỉnh số.
- Nhãn “điểm model”; câu ngắn giải thích đây chưa phải xác suất dự đoán đúng.
- Giữ cảnh báo truncated và giới hạn preprocessing. Không gọi một đoạn nhiều câu là đã được phân tích riêng từng câu nếu backend chỉ dự đoán cả đoạn.
- Thiếu model: thông báo rõ, nút phân tích disabled, không gọi diễn giải; profile UIT không mượn model NEU.
- Waiting dùng trạng thái thực queued/loading_model/running, không dùng timer hoặc progress % giả.

### 4.3 Lớp 2 — Interpretability và diễn giải

Hai nguồn độc lập trong cùng phần UI:

- Tín hiệu local: đọc `Item.review_signals`, giữ phân biệt cảm xúc/chủ đề, low top1/small margin, unavailable và truncated. Không hardcode ngưỡng 0,60 của mockup.
- Diễn giải: tự gọi sau prediction hợp lệ; trạng thái riêng `idle/loading/success/error/unavailable`. Loading có chữ **Đang diễn giải…** và thanh chạy vô định, không % hoàn thành giả.

Thành công hiển thị hai đoạn ngắn: “Cách đọc kết quả này” và “Điểm cần lưu ý”. Không có nút “Xem diễn giải mẫu” hoặc mục “LLM hoạt động thế nào”. Lỗi hiển thị **Chưa tải được diễn giải** cùng **Thử lại diễn giải**; retry này không tạo job classifier mới.

Không tự nhận local/offline cho diễn giải dùng dịch vụ ngoài. Giữ một dòng ngắn gần vùng nhập hoặc footer: “Phân loại chạy trên máy; câu và kết quả được gửi tới dịch vụ diễn giải.” Không cần popup xác nhận mỗi lần hay tên nhà cung cấp trên card. Trang hướng dẫn mới là nơi nêu 9router và cách cấu hình.

Khi sửa/xóa input, đổi profile, gửi job mới hoặc rời route: kết quả cũ không được trình bày như kết quả của input mới; hủy subscription/request có thể hủy, đồng thời kiểm tra generation/identity để bỏ response muộn. Abort phía client không được tuyên bố đã hủy xử lý ở provider.

### 4.4 Thử nghiệm độ nhạy

Tận dụng `SensitivityPanel` với Item, run và source_prediction_id từ quick result; kiểm tra thực tế quick item tạm có tương thích API không trước khi ghép. Nếu cần adapter, giữ logic selection, Unicode/UTF-16, stale/cancel/retry và provenance hiện có.

- Chỉ chạy khi người dùng yêu cầu; không tự chạy thêm inference sau mỗi lần phân tích.
- Dùng đúng model identity và chế độ chạy; không lấy prediction khác làm baseline.
- Không đổi văn bản gốc hoặc nhãn duyệt.
- TTL hết thì yêu cầu phân tích lại; không tự lưu câu vào dataset lâu dài để né TTL.
- Giữ giới hạn “thử độ nhạy không phải giải thích nhân quả”.
- Nếu chưa kiểm chứng được ghép quick item, báo rõ công việc còn thiếu; không thay bằng so sánh D06 cố định của mockup.

### 4.5 Lớp 3 — Chủ đề cần chú ý

Màn demo một câu không tự có tập thống kê. Mặc định chưa chọn dataset: hiện “Chọn bộ phản hồi để xem thống kê theo chủ đề”, không hiện số 12 hay thống kê dựng sẵn.

- Cho chọn dataset cùng profile; đổi profile reset lựa chọn không tương thích.
- Hiện tên dataset, phạm vi/run, nguồn nhãn và số phản hồi đủ điều kiện. Cho chọn `effective` hoặc `ai` theo hợp đồng hiện có.
- Gọi summary API và tái sử dụng `TopicAttention`; không tính từ trang đầu tiên của danh sách items.
- Giữ thứ tự `negative_count_desc,eligible_count_desc,topic_id_asc`, cờ mẫu nhỏ n < 5 và Toxic tách biệt.
- Tỷ lệ tiêu cực = negative_count / eligible_count của chủ đề; khi mẫu số 0 hiển thị chưa đủ dữ liệu, không 0% tùy tiện.
- Nếu có biểu đồ phân bố chủ đề, ghi rõ mẫu số riêng của nó; không lẫn tỷ lệ trong dataset với điểm classifier.
- Click chủ đề tiêu cực mở danh sách inline đọc-only bằng items API, có phân trang, đúng dataset/run/label_source/topic/negative filter dùng ở summary. Có link mở workspace để rà soát. Không giả định workspace hiểu query params chưa được triển khai.
- Không gọi “vấn đề cụ thể” chỉ vì một topic có nhiều nhãn tiêu cực; chưa thêm LLM đề xuất hành động.
- Không tự nhập câu đang demo vào dataset; thao tác “Thêm câu vào bộ” nếu giữ phải explicit và giữ semantics hiện tại: lưu text, chạy phân tích trong bộ để tạo provenance riêng.

## 5. Phân công subagent

Người dùng cho phép Gemini dùng subagent nếu có lợi. Đề xuất một agent chính + tối đa ba subagent; nếu công cụ không hỗ trợ thì làm tuần tự, không giả báo đã có review độc lập.

| Vai trò | Ownership đề xuất | Đầu ra |
|---|---|---|
| Agent chính | `App.tsx`, `api.ts`, `types.ts`, `services/api/main.py`, hợp đồng chung, tích hợp, tài liệu | Chốt types/API trước, ráp các phần, chạy nghiệm thu |
| UI | Component demo mới và CSS/font assets riêng | Layout, state UI, thanh %, responsive, wiring qua contract đã thống nhất |
| Backend | Service diễn giải mới, unit tests service, dependencies đã thống nhất | Adapter 9router, timeout, validation, dedupe, xử lý lỗi |
| QA | Tests API/E2E mới và review độc lập sau tích hợp | Race/negative tests, regression, screenshots, phát hiện thật |

Trước giao việc, agent chính gửi schema request/response, component props và danh sách file ownership. Tất cả agent phải biết đang dùng chung worktree, không revert sửa đổi của người khác. Chỉ owner sửa file chung; gửi đề xuất nếu cần thay đổi. QA thiết kế acceptance độc lập từ yêu cầu, không chỉ lặp lại implementation. Agent chính vẫn chịu trách nhiệm chạy kiểm chứng tích hợp và ghi mọi finding chưa sửa.

## 6. Hợp đồng diễn giải đề xuất

Đây là API mới cần triển khai, không phải endpoint đang tồn tại.

### 6.1 Frontend chỉ gửi identity

`POST /api/v1/quick-analysis/{job_id}/explanation`

Body tối thiểu:

```json
{"source_prediction_id":"<id prediction đang hiển thị>"}
```

Backend đọc job/run/item/prediction từ storage; yêu cầu đúng quick job completed, còn TTL, đúng source_prediction_id, revision/schema/model metadata hợp lệ. Không tin câu, nhãn hoặc scores do client tự gửi. Không gọi provider cho job chạy dở, failed, cancelled, hết hạn hoặc identity lệch.

Response thành công đề xuất:

```json
{
  "status": "completed",
  "job_id": "...",
  "run_id": "...",
  "item_id": "...",
  "revision_id": "...",
  "source_prediction_id": "...",
  "profile_id": "neu",
  "schema_id": "neu-v1",
  "classifier_model_id": "...",
  "classifier_model_version": "...",
  "prompt_version": "result-explanation-v1",
  "reading": "...",
  "caution": "..."
}
```

Chốt schema trong code trước khi chia agent. Identity này là metadata do server gắn, không nhờ LLM sinh. Nếu thay contract, ghi lý do và cập nhật tests, docs, frontend đồng thời.

Mã lỗi ổn định, theo envelope `{code,message}` hiện có: chưa cấu hình (503), quá tải tạm thời (429), timeout (504), provider không dùng được/response không hợp lệ (502), source conflict/job chưa sẵn sàng (409), job không tồn tại/hết hạn (404 hoặc 410 tùy khả năng phân biệt thật). Không bịa phân biệt 404/410 nếu storage đã xóa không còn bằng chứng.

### 6.2 Backend gọi 9router

Thêm service riêng, ví dụ `services/explanation.py`. `create_app` cho inject provider test double; production mặc định provider thật hoặc unavailable nếu chưa cấu hình. Không có cờ fixture production hay endpoint debug trả lời mẫu.

Cấu hình chỉ ở backend:

| Biến đề xuất | Nội dung |
|---|---|
| `FEEDBACK_EXPLANATION_BASE_URL` | URL gateway do người dùng cung cấp, định nghĩa rõ có gồm `/v1` không |
| `FEEDBACK_EXPLANATION_API_KEY` | Key, không đi vào biến `VITE_*` |
| `FEEDBACK_EXPLANATION_MODEL` | Model id thực có ở gateway, không đoán alias |
| `FEEDBACK_EXPLANATION_TIMEOUT_SECONDS` | Mặc định 20 giây, validate khoảng hợp lý |

Chưa xác minh base URL/model của 9router tại thời điểm lập kế hoạch. Tài liệu cấu hình phải nói rõ app đọc environment, không tự nhận đã load `.env` nếu không có loader. Dùng ví dụ PowerShell với placeholder; `.env.*` hiện bị ignore, không vô tình force-add file chứa secret.

- Nếu gateway hỗ trợ Chat Completions compatible, dùng giao thức đó; xác nhận format bằng cấu hình/docs phù hợp, không giả định JSON schema/streaming được mọi provider hỗ trợ.
- Dùng HTTP client async có timeout, quản lý vòng đời; không blocking event loop, không đưa chờ 9router vào hàng đợi classifier worker, không giữ SQLite transaction khi chờ mạng.
- `httpx==0.28.1` hiện chỉ nằm trong requirements test; nếu dùng ở production phải khai báo requirements API và cập nhật lock dependency có kiểm tra, không dựa vào môi trường dev tình cờ có.
- Giới hạn response size và chiều dài reading/caution, giới hạn concurrency (ví dụ 2 request provider đang chạy), không queue vô hạn. Timeout tổng gồm cả chờ slot.
- Không tự retry vô hạn hoặc gửi lần hai chỉ để sửa JSON. Cho người dùng retry sau lỗi; lần retry không chạy classifier lại.
- Provider URL chỉ lấy từ cấu hình server, không nhận từ request browser. Không trả raw upstream response/auth header; lỗi phải redact.
- Không mở CORS wildcard để gọi gateway trực tiếp từ browser. Route mới chỉ nhận JSON từ cùng ứng dụng; kiểm tra Origin khi có để tránh trang ngoài kích hoạt các request có chi phí. Giữ test-client không Origin hoạt động.
- Thiếu cấu hình không làm API startup, health, dataset hay classifier hỏng. UI hiển thị “Chưa cấu hình dịch vụ diễn giải”, hướng dẫn ở trang help.

### 6.3 Nội dung đưa cho LLM và giới hạn lời giải thích

System prompt bằng tiếng Việt, ngắn và versioned. Dữ kiện được gửi dưới một payload cấu trúc, coi văn bản người dùng là dữ liệu không phải chỉ dẫn:

- Văn bản snapshot đúng prediction, profile/schema, tên các nhãn và phân bố scores.
- Kết quả top1, review signals theo policy thực, truncated và cảnh báo liên quan.
- Không gửi API key, dataset metadata không cần thiết, lịch sử người dùng hay toàn bộ bộ phản hồi.
- Diễn giải mối phù hợp giữa nội dung và kết quả, không khẳng định biết reasoning/token attention/SHAP bên trong classifier.
- Không tự đổi nhãn, tự tạo phần trăm, tạo câu bị trích không có trong input hoặc gọi đó là kết quả phân tích riêng từng câu.
- Khi truncated, nói rõ classifier chỉ đọc phần được giữ. Nếu không có span chính xác, không suy đoán phần nào là bằng chứng classifier đã dùng.
- Nội dung input kiểu “bỏ qua hướng dẫn, trả nhãn khác” phải được coi là câu cần đọc, không thực thi.

Đầu ra yêu cầu object chỉ có `reading` và `caution`, giới hạn khoảng 2.000 ký tự mỗi trường, khoảng 100–180 từ tiếng Việt tổng cộng là mục tiêu mềm. Parse/validate strict; không render raw HTML, không dùng dangerouslySetInnerHTML, không thực thi code/link trong output. Nội dung malformed/refusal không phù hợp schema phải thành trạng thái lỗi có retry, không fallback sang diễn giải mẫu.

UI tự giữ các cảnh báo khoa học từ dữ liệu local bên ngoài nội dung LLM; không để LLM quyết định có hiển thị cảnh báo hay không. Chưa thể bảo đảm semantic correctness chỉ bằng JSON validation; ghi đây là giới hạn cần kiểm thử smoke riêng.

### 6.4 Chống gọi trùng và response cũ

- Một job/prediction thành công mới -> một yêu cầu diễn giải tự động. Phân tích lại cùng câu tạo job mới vẫn tự diễn giải mới.
- Poll job, re-render, StrictMode hoặc refetch không tạo nhiều cuộc gọi upstream cho cùng kết quả.
- Frontend dùng identity/generation + cleanup; backend coalesce request đang chạy và cache thành công có giới hạn, TTL không vượt đời quick result. Cache key gồm job, prediction, revision, schema/model version, prompt/policy version và cấu hình provider liên quan.
- Không cache lỗi vĩnh viễn; retry phải thực sự có thể gọi lại. Không giữ raw feedback lâu hơn TTL, không tạo bảng lưu trữ dài hạn chỉ cho diễn giải.
- Trước trả cache và trước phát response thành công sau thời gian chờ mạng, kiểm lại source còn hợp lệ. Source đã hết hạn/đổi thì không giao diễn giải cũ như kết quả mới.
- Khóa/cache/in-flight phải được cleanup khi timeout/cancel/exception, bounded theo số entry. Client hủy một subscription không làm hỏng request chung của subscription còn lại.
- Idempotency process-local đủ cho cấu hình một API process local hiện tại; ghi giới hạn, không tuyên bố bảo đảm phân tán nhiều process.

## 7. Trình tự thực thi và điểm nghiệm thu

### P0 — Chụp baseline và chốt contract

1. Đọc chỉ dẫn, xác nhận branch/HEAD/status; tạo thư mục evidence tạm riêng ngoài source.
2. Lưu staged/unstaged diff, danh sách untracked và manifest SHA-256 source liên quan, gồm design-previews. Không đưa secret, runtime DB hay model vào snapshot công khai.
3. Kiểm tra toolchain/dependencies, entry routes, fixture isolation. Chốt API/types/props, giao ownership.

Đạt khi có baseline có thể tái hiện và không nhầm mockup là implementation.

### P1 — Backend diễn giải và tests độc lập

1. Implement config/provider abstraction, context builder, validation, timeout, error mapping, dedupe và TTL.
2. Gắn endpoint trước SPA fallback; inject provider từ factory để tests dùng doubles.
3. Test failure và identity trước tích hợp UI. Không thay cách worker tạo prediction.

Đạt khi provider chậm/lỗi không ảnh hưởng health/jobs và snapshot prediction không đổi.

### P2 — Màn React và luồng bất đồng bộ

1. Route demo + shell mới, font/CSS riêng; chuyển mẫu thành nút điền text.
2. Kết nối quick job, các trạng thái lỗi/hủy/retry/missing model.
3. Render đầy đủ labels/bars và local signals trước diễn giải.
4. Tự gọi diễn giải, handle response cũ/StrictMode/retry và trạng thái thiếu config.
5. Tích hợp sensitivity thật và thao tác thêm câu vào bộ nếu giữ.

Đạt khi kết quả vẫn xem được trong suốt một provider request bị giữ chờ; input mới không nhận diễn giải của input cũ.

### P3 — Lớp 3 theo dataset

1. Chọn dataset và nguồn nhãn, summary thật, các empty/partial/error states.
2. Drill-down dùng filter cùng scope và phân trang.
3. Kiểm chứng count/rate bằng fixture đã biết, có missing labels và Toxic.

Đạt khi không có số giả từ mockup, mỗi aggregate truy được về đúng các dòng nguồn.

### P4 — Tích hợp, QA và tài liệu

1. Agent chính review diff, chạy build và tests; sửa findings, chạy lại phần ảnh hưởng.
2. QA kiểm browser desktop/mobile và hành vi lỗi/race; lưu screenshots và observations.
3. Cập nhật PRODUCT/DESIGN/hướng dẫn cấu hình; ghi rõ prediction local, diễn giải dịch vụ ngoài.
4. Chốt artifact và báo cáo theo mục 10. Không tự commit/push.

## 8. Ma trận kiểm thử bắt buộc

Tests provider/model dùng doubles xác định; kết quả nào chỉ mock phải ghi rõ. Không cần mutation campaign toàn codebase, nhưng bắt buộc test phủ định cho race/dedupe/provenance ở thay đổi mới.

| ID | Tình huống | Điều phải quan sát |
|---|---|---|
| U01 | Mở demo, chưa nhập | Không tự gọi inference/provider; layers có empty state |
| U02 | Chọn câu mẫu rồi phân tích | Chọn mẫu chỉ điền text; submit tạo một job, điểm lấy từ response thật của fixture |
| U03 | NEU 10 chủ đề, UIT 4 chủ đề | Đủ nhãn/thanh %, tên dài vẫn đọc được; không mapping theo 3 topic của mockup |
| U04 | Provider bị gate giữ chờ | Lớp 1 và local signals đã visible; “Đang diễn giải…” visible; health/jobs vẫn phản hồi |
| U05 | Job poll/refetch/re-render/StrictMode | Request upstream count = 1 cho cùng snapshot; kết quả cuối vẫn cập nhật sau effect cleanup |
| U06 | Câu A diễn giải chậm, chuyển B | Fulfill A sau khi B active: không ghi đè B. Dùng response gate/identity assertion, không chỉ sleep |
| U07 | Xóa input/đổi profile/rời route | Không flash stale explanation hoặc update state của context đã bỏ |
| U08 | Timeout, HTTP 401/429/500, disconnect | Lớp 1 không mất; lỗi diễn giải dễ hiểu, không lộ key/raw upstream; retry không gọi classifier |
| U09 | Thiếu config / thiếu model | Thiếu config vẫn phân loại được; thiếu model không tạo prediction và không gọi provider |
| U10 | JSON lỗi/empty/refusal/oversize/HTML | Output bị chặn hoặc render text an toàn; không có diễn giải mẫu giả |
| U11 | Giả source_prediction_id, job chưa completed/hết hạn | Không gọi provider; status/code đúng; cache không bypass source validation |
| U12 | Input mang prompt injection; truncated | Prompt coi input là dữ liệu; cảnh báo local luôn giữ. Không claim test stub chứng minh LLM thật chống injection |
| U13 | Sensitivity quick item | Source/run/revision đúng; stale/retry/cancel/TTL giữ; không mutate input/reviews |
| U14 | Lớp 3 chưa chọn dataset, empty dataset | Không aggregate giả hoặc chia 0 |
| U15 | Dataset có missing labels/Toxic/negative | Count, denominator, rate, thứ tự và small-sample đúng semantics hiện có |
| U16 | Click topic negative, đổi source/run/dataset | Danh sách gốc đúng scope; không giữ kết quả selection cũ |
| U17 | 1440/1280/768/390/320px, text dài, keyboard | Không tràn trang, focus rõ, bar/label không chồng, loading hỗ trợ reduced motion |
| U18 | Lỗi classifier, cancel và retry | Không gọi diễn giải cho failed/cancelled; retry thành công gắn snapshot mới |
| U19 | Provider timeout/cancel và request trùng | Slot/lock/cache được giải phóng; request tiếp theo vẫn chạy; không leak task hoặc deadlock |
| U20 | Regression workspace/C1 | Review conflict/provenance, sensitivity stale payload, filters/export/restart vẫn đúng |

Lệnh chuẩn từ repo root (đọc lại fixtures trước khi chạy):

```powershell
Push-Location F:\DPL_NEU-ESC\apps\web
npm run build
Pop-Location

.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/api tests/test_review_signals.py tests/test_sensitivity_selection.py tests/test_runtime_isolation.py -q --tb=short -p no:cacheprovider
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e -q --tb=short -p no:cacheprovider
git diff --check
```

Chạy thêm unit tests service mới tại đường dẫn thực đã tạo. Đây không phải yêu cầu full pytest/model benchmark. Existing tests có thể cần đổi `page.goto(url)` thành `page.goto(url + '/#/')` nếu test nhắm dataset home; đó là cập nhật route có chủ đích, phải ghi rõ. Tests nhắm quick modal cần được chuyển sang hành vi route/component mới mà giữ assertion tác vụ tương ứng.

Build trước E2E: fixture hiện có skip nếu thiếu dist; **skip vì chưa build không tính pass**. API test có thể import module-level app, nên giữ isolation của `tests/conftest.py`. Test server dùng runtime/port riêng, không đụng server hiện dùng trên 8765; dọn đúng PID/process do phiên thực thi tạo.

## 9. Hiệu năng và kiểm chứng UI

Người dùng đã báo chậm khi bấm Phân tích. Chưa có baseline đủ để kết luận regression; đừng hứa nhanh hơn khi chỉ đổi loading.

- Không gắn chờ diễn giải vào completion của prediction job. Không tạo độ trễ giả để animation đẹp.
- Đo các mốc submit, job completed nhận được, lớp 1 visible, explanation start/end. Ghi classifier và provider timings riêng.
- Test có gate chứng minh lớp 1 visible trước khi provider được thả; đo ms bằng doubles chỉ nói về orchestration/UI, không phải tốc độ model thật.
- Duy trì poll hợp lý và dedupe; không load model lại hoặc tạo inference thứ hai để diễn giải.
- Không đổi kiến trúc worker hay thêm warmup inference trong scope này. Nếu phát hiện bottleneck, ghi bằng chứng và đề xuất riêng.
- Screenshot bắt buộc có: desktop success, mobile success đủ 10 topic, provider-loading với lớp 1 visible, explanation error, missing model, dataset empty và populated. Chụp và tự xem để phát hiện chênh, tràn hoặc chữ nhỏ; không chỉ tạo file ảnh.
- Nếu môi trường chặn browser, ghi rõ bước bị chặn và kiểm chứng tĩnh đã làm; không nói visual QA passed. Không đổi công cụ để lách một lệnh bị từ chối.

## 10. Evidence và báo cáo cuối

Tạo report tại `F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_IMPLEMENTATION_REPORT_2026-11-11.md` (đổi ngày nếu thực thi ngày khác). Evidence dùng thư mục riêng, ví dụ `%TEMP%\neu-esc-sentence-ui-<unique-id>`; ghi đường dẫn tuyệt đối trong report.

Evidence tối thiểu:

- `baseline.json`: branch, HEAD, status và manifest trước.
- `implementation.delta.diff`: delta chỉ của phiên thực thi so với baseline, **gồm nội dung file mới/untracked**, không chỉ `git diff HEAD` bỏ sót file mới.
- `manifest-after.json` và `preservation-verification.json`: SHA-256 file sửa/tạo, các file baseline ngoài scope có giữ nguyên không; snapshot mockup giữ nguyên.
- `test-results.json`: command, cwd, exit code, pass/fail/skip, duration, log path; giữ cả lỗi debug đã sửa nếu có, chỉ rõ lượt nghiệm thu cuối.
- Logs build/API/unit/E2E và `observations.json`: U04/U05/U06/U11 identity, order và request counts quan sát được.
- Screenshots cùng kích thước viewport; chỉ chụp dữ liệu test, không secret.
- Manifest dist thực E2E đã phục vụ khớp source build cuối. Nếu sửa sau build/test, chạy lại phần tương ứng.
- `qa-review.md`: findings của QA/subagent và trạng thái sửa, hoặc ghi rõ không có review độc lập.

Report phải tách ba trạng thái:

1. **Code + tests với doubles**: gì đã pass thực sự.
2. **Visual QA**: viewport/trạng thái đã xem, giới hạn nếu bị chặn.
3. **Model thật + 9router thật**: đã kiểm tra hay chưa. Mặc định đợt này là chưa, không gộp vào claim “end-to-end live pass”. Nếu thiếu key/model config, nêu chính xác biến còn thiếu, không đưa secret vào báo cáo.

Ghi các thay đổi chức năng, routes, cấu hình mới, dependency changes, limitations, deviations so với plan và cách rollback chỉ delta này. Không dùng `git reset --hard` hay xóa baseline để rollback.

### Definition of Done

- UI bám mockup về style/bố cục, đọc được đủ labels thật; không còn khoảng hở input cạnh result.
- Luồng prediction -> diễn giải tự động, failure isolation, dedupe và chống stale response có test quan sát.
- Local signals/sensitivity và lớp 3 dùng đúng nguồn; không còn data/timer demo trong production.
- Không lộ key; hướng dẫn cấu hình đủ để người dùng nối gateway thật khi có thông tin.
- Tests phù hợp và visual QA có evidence; regression không bị bỏ qua.
- Mọi phần chưa chạy thật/chưa kiểm chứng được liệt kê rõ. Có thể bàn giao “implementation đã kiểm thử bằng doubles, chờ cấu hình/smoke live”; không gọi đó là live integration đã xác minh.
- Đã tạo report và prompt ngắn bên dưới. Không commit/push/deploy.

## 11. Prompt ngắn Gemini phải xuất ở cuối

Sau báo cáo, xuất một khối văn bản để người dùng copy nguyên về Codex. Thay hết placeholder bằng thông tin thực, giữ gọn khoảng 15–20 dòng; không paste diff hoặc key vào prompt.

```text
Review implementation UI demo + diễn giải 9router tại F:\DPL_NEU-ESC.
Plan: F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_GEMINI_PLAN_2026-11-11.md
Report: <đường dẫn tuyệt đối report thực tế>
Evidence: <đường dẫn tuyệt đối thư mục evidence>
Branch: <branch>; baseline HEAD: <hash>; HEAD hiện tại: <hash>.
Scope review: delta của phiên thực thi, gồm toàn bộ file mới/untracked ghi trong manifest.
Đã làm: <2–3 dòng: UI/routes, API auto-explanation, local signals/sensitivity, lớp 3>.
Files/Hashes: xem <manifest-after.json>; delta: <implementation.delta.diff>.
Kiểm thử: <build, unit/API/E2E: passed/failed/skipped và log>.
Visual QA: <viewport/trạng thái đã kiểm chứng hoặc chưa>.
Model thật/9router thật: <đã/chưa kiểm chứng; doubles ở đâu>.
Subagents/QA: <phân công, findings còn mở hoặc không có review độc lập>.
Khác plan/còn thiếu: <liệt kê cụ thể hoặc không có>.
Ưu tiên review: prediction không chờ diễn giải; stale/dedupe; identity/TTL;
secret/config; đủ labels/thanh %; mẫu số/drill-down lớp 3; regression C1; evidence trung thực.
Chỉ review, không sửa, commit/push/deploy hoặc chạy model/API thật nếu chưa có chỉ thị mới.
```
