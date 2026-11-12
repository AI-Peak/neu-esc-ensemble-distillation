# Prompt Codex: sửa bản webapp Gemini đã triển khai

Bạn đang tiếp tục dự án tại `F:\DPL_NEU-ESC`, Windows/PowerShell. Gemini đã triển khai giao diện và attribution nhưng review độc lập tìm thấy các lỗi F01–F12. Nhiệm vụ của bạn là **sửa implementation hiện có, kiểm chứng và bàn giao bản chạy được**, không chỉ review lại hoặc viết thêm plan.

Người dùng đã cho phép sửa các lỗi trong review, bổ sung kiểm thử cần thiết và dùng subagent nếu tăng chất lượng. Hãy chủ động thực hiện đến khi hoàn tất phạm vi; chỉ hỏi khi có quyết định sản phẩm hoặc thay đổi semantics chưa được cho phép. Không dừng ở đề xuất, không yêu cầu người dùng xác nhận lại từng mốc.

## 1. Đọc đúng nguồn và giữ đúng yêu cầu Đạt

Đọc trước khi sửa, theo thứ tự:

1. `docs/GEMINI_WEBAPP_CODE_REVIEW_2026-11-12.md`: findings F01–F12, bằng chứng tái hiện và giới hạn review.
2. `docs/GEMINI_WEBAPP_IMPLEMENTATION_HANDOFF_2026-11-12.md`: contract, công thức, lifecycle và yêu cầu R01–R09.
3. `design-previews/2026-11-12/reference-table-desktop.png`, `analysis-mobile.png`: mở ảnh để xem thực sự, không chỉ đọc tên file.
4. `design-previews/2026-11-12/index.html`, `styles.css`, `mockup.js`, `README.md`: tham chiếu thiết kế, dữ liệu chỉ là fixtures.
5. Code đang có, hướng dẫn repo/AGENTS nếu có, `PRODUCT.md`, `DESIGN.md`, `docs/LOCAL_APP.md`.
6. `docs/WEBAPP_ATTRIBUTION_CONTRACT.md`, `docs/ATTRIBUTION_FEASIBILITY_2026-11-12.md`, `docs/GEMINI_WEBAPP_IMPLEMENTATION_REPORT_2026-11-12.md`: đọc để tìm phần cần hiệu chỉnh. Không xem nhãn PASS trong các báo cáo này là bằng chứng đã nghiệm thu.

Nếu cần hiểu bốn ảnh gốc, tham khảo `docs/TEAMMATE_FEEDBACK_IMAGE_ANALYSIS_PLAN_2026-11-12.md`. Handoff mới hơn quyết định thiết kế; tài liệu phân tích cũ không được ghi đè lựa chọn đã chốt.

Yêu cầu người dùng/Đạt phải giữ:

- **Hình 1 quan trọng nhất:** bảng desktop bốn cột **Phản hồi / Từ quan trọng / Trọng số cảm xúc / Tổng đóng góp**, gần mockup, tỷ lệ tham chiếu 50/21/15/14.
- Header teal, chữ trắng; trọng số căn hàng với cụm từ; tổng trong cột cuối, không tách thành thẻ KPI mới.
- Giữ **các thanh đo nhỏ cho từng nhóm từ** và tên **Tổng đóng góp**. Dòng aggregate “Các từ còn lại” chỉ có số theo handoff đã chốt.
- Highlight từ/cụm và dòng bảng chọn qua lại; xanh đậm/đỏ nghiêng cho polarity, chú giải phù hợp cho target khác.
- Giữ prediction local: sentiment, điểm, topic, phân bố nhãn và chi tiết các topic của profile.
- Bỏ copy thừa, ba nút câu mẫu, nhãn/khối Lớp 1/2/3 và phương án LLM/9router.
- Chỉ xóa câu phụ “Văn bản gốc luôn được giữ nguyên”; vẫn giữ nguyên văn phản hồi. Không thêm lại các khối giải thích dài.
- Donut/topic/evidence và network đã có thì sửa cho đúng. Chúng không thay thế được bảng bắt buộc.
- Giữ Be Vietnam Pro, nhận diện teal, framework/route và các luồng dataset/import/review/export hiện có.

Phân biệt hai loại ưu tiên: P0/P1/P2 trong handoff là các phần sản phẩm; P1/P2 trong findings là mức độ lỗi. Hoàn tất sửa toàn bộ phạm vi đã được review, ưu tiên tính đúng của bảng trước.

## 2. Bảo toàn workspace và thiết lập kiểm thử

- Bắt đầu bằng `git status --short`, đọc staged/unstaged diff và các file untracked liên quan. Bản triển khai Gemini, mockup, plans và review đều là tài sản cần giữ. Không reset/checkout/revert về HEAD để làm lại.
- Kiểm hiện trạng trước mỗi sửa đổi; số dòng trong review chỉ là điểm định vị, có thể dịch chuyển. Nếu bug đã được sửa, chứng minh bằng test và không sửa lại vô ích.
- Không commit/push/deploy, không train/thay checkpoint, không ghi vào model weights hoặc current pointer nguồn. Không khởi động/migrate/cleanup live database chỉ để chạy test.
- Chạy API/worker/test trên runtime riêng trong temp hoặc `test-results` có ID phiên. Đặt `FEEDBACK_RUNTIME` trước import `services.api.main`, vì module tạo app ngay lúc import. Ưu tiên fixture isolation đã có.
- Test model thật dùng bản copy bundle đã kiểm hash; tái sử dụng helper `_verify_and_copy_active_bundle` trong `tests/inference/test_three_layer_real_model.py` hoặc tách helper an toàn. Không hardcode test chạy trực tiếp vào `F:/DPL_NEU-ESC/runtime/models`.
- Model chạy offline. Không cài lại môi trường hoặc tải model nếu môi trường local đã đủ. Không in secrets/raw private data vào log.
- Một owner chạy build/dist, browser test server và model benchmark tại một thời điểm. Không kill/restart process không thuộc phiên này.
- Migration 3 có thể đã được áp dụng dù file còn untracked. Nếu cần đổi schema, thêm migration tiếp theo, không sửa định nghĩa migration đã áp dụng. Kiểm nâng cấp từ DB cũ, backup/restore và dữ liệu bền còn nguyên.

## 3. Khởi động công việc và chia subagent

Root khảo sát ngắn, lập checklist F01–F12 và các contract gaps ở phần 8, rồi chốt interface/provenance/lifecycle trước khi giao việc. Chỉ làm lượng thiết kế cần thiết để sửa các lỗi, không xây một framework attribution/scheduler mới.

Được phép và nên dùng subagent khi có phần độc lập. Tối đa 2–3 subagent cùng lúc; nếu không có công cụ thì thực hiện tuần tự và nói rõ, không giả lập báo cáo reviewer.

| Owner | Phạm vi |
|---|---|
| Root | Contract chung; `services/api/main.py`, `services/storage/db.py`, `services/worker.py`, migration; `apps/web/src/types.ts`, `api.ts`; tích hợp, real-model validation, build và nghiệm thu |
| Worker engine | `services/attribution.py`, mapping/grouping; phần `services/inference/registry.py` đã phối hợp; engine/model tests được giao |
| Worker UI | `SentenceDemo.tsx/.css`, `AttributionTable.tsx`, `HighlightedFeedback.tsx`, frontend validators/hooks mới, E2E được giao |
| Reviewer độc lập khi trống slot | Đọc diff và test/bằng chứng, tìm lỗi còn lại; không tự sửa file của owner |

Sau khi bảng và attribution đạt, tái sử dụng worker engine cho `services/text_network.py`, worker UI cho `TermNetwork.tsx`/`SentimentDistribution.tsx` và phần evidence. Không giao hai worker cùng sửa `SentenceDemo.tsx` hoặc shared test fixtures.

Trong mọi task giao cho worker phải có câu: “Bạn không làm việc một mình; không revert thay đổi của người khác. Chỉ sửa trong ownership, phối hợp với root khi cần đổi contract/shared files. Báo file sửa, test đã/chưa chạy và giới hạn.”

Subagent không đồng thời chạy nhiều encoder. Root chịu trách nhiệm cuối cùng, phải kiểm tích hợp thay vì chỉ ghép kết luận PASS của các worker.

## 4. Sửa target, async và trạng thái UI: F01–F03

### F01 — Resolve nhãn từ profile, bỏ giả định sai về index

Nguồn đúng hiện tại là `services/profiles.json`:

- NEU: Neutral=0, Positive=1, Negative=2, Toxic=3.
- UIT: negative=0, neutral=1, positive=2.

Không thay một bộ magic numbers bằng một bộ khác. Resolve theo `key` chuẩn hóa hoa/thường trong profile; classifier score phải ánh xạ theo schema rõ ràng.

- Prediction Positive/Negative mặc định dùng `polarity_margin = 100 * (p_positive - p_negative)`.
- Prediction Neutral/Toxic dùng `label_score = 100 * p_predicted_label`.
- Polarity có chú giải nghiêng tích cực/tiêu cực và màu xanh/đỏ. Label score có chú giải tăng/giảm điểm nhãn, màu riêng xanh lam/nâu; tăng Toxic không được gọi là tích cực.
- Server kiểm target label ID có trong sentiment profile; từ chối -1, ngoài miền, bool, float, field lạ. Profile chưa có checkpoint vẫn unavailable, không fallback sang NEU.
- Backend cũng không hardcode index NEU cho UIT; mask/BOS/EOS/padding lấy theo tokenizer/model được hỗ trợ. Nếu một profile không hỗ trợ attribution, trả unsupported rõ và giữ prediction.

Nghiệm thu: test đủ bốn target NEU, ba target UIT ở mức schema/API/UI bằng double; bổ sung kiểm thử bằng checkpoint thật đã có qua isolated bundle fixture. Profile chưa có checkpoint chỉ kiểm bằng double và vẫn báo unavailable trong production. Kiểm request, số target và legend cùng khớp, không chỉ badge.

### F02 — Generation ownership và validation cho toàn bộ attribution

Tái hiện: giữ POST câu A, đổi/sửa/clear/profile sang B, hoàn tất B rồi trả response A hoặc lỗi A. Không được hiện từ/trọng số/error của A trong B.

- Mỗi phiên phân tích có generation/source/target identity rõ. Capture trước await, kiểm lại trước mọi state/ref update của POST, GET, cancel và retry, kể cả lỗi.
- Abort HTTP là tối ưu, không phải bằng chứng server đã hủy. POST cũ trả muộn vẫn phải nhận ID và best-effort cancel đúng handle cũ; không cancel B.
- Same-tick duplicate và StrictMode không tạo job thừa. Retry transport cùng thao tác giữ cùng Idempotency-Key; retry mới sau terminal failure/cancel có key mới. Không dùng `Date.now()` để thay key ở mọi lần retry cùng thao tác.
- Poll/query key và kết quả cache gắn đúng source/target. Callback cũ không làm mất loading hoặc unlock thao tác mới.
- Render đúng snapshot server `item.text`, không lấy textarea đang sửa hoặc pre-trim text gắn với spans post-trim.
- Validator trước render kiểm source IDs/revision/hash/model/schema/target, các số finite, raw slices/spans/UTF-16/grapheme, partition không chồng lấp và aggregate đúng tolerance. Payload sai phải thành attribution error; không fallback thành 0.
- Prediction hợp lệ vẫn hiển thị nếu attribution lỗi. Giữ các bảo vệ generation hiện có của submit/cancel/retry/save-to-dataset.

Nghiệm thu: response A về sau B, cache-hit POST trả muộn, failure A về sau B, clear/profile/unmount giữa POST, cancel pending, double click/StrictMode và payload sai identity. Có ít nhất một test ghi nhận cancel handle A và chứng minh B còn nguyên.

### F03 — Mọi terminal/error state có kết thúc và cách phục hồi

- Dừng polling cho completed/failed/cancelled/unsupported. Xử lý 404/410/409/422 và lỗi mạng; không polling vô hạn một lỗi đã biết không phục hồi được.
- Unsupported nêu lý do ngắn: mapping/truncation/profile; không hiện tổng 0 như kết quả hợp lệ.
- 410/nguồn hết hạn hướng dẫn phân tích lại câu; lỗi mạng có thử lại hữu hạn phù hợp; không âm thầm tạo thêm prediction job khi chỉ cần phục hồi GET attribution.
- Retry thực sự hoạt động: reset dedup/attempt state thích hợp, không bị last-request ref chặn mãi. Cancel không để spinner hoặc progress cũ tồn tại.
- Progress không biết mẫu số thì dùng trạng thái đang chạy; không bịa phần trăm.

Nghiệm thu: đếm request sau unsupported/404/410 để chứng minh polling dừng, kiểm thông báo/retry và prediction còn nguyên; test cancel khi queued/running và completed nhận cancel muộn.

## 5. Sửa nguồn model, mapping và phép tính: F04, F06

### F04 — Attribution phải giải thích đúng prediction nguồn

Review đã tái hiện với test double: source target=0 nhưng attribution target=52,006, residual=0; đổi model_version vẫn báo completed với metadata version cũ. Cộng khớp nội bộ không đủ.

- Lưu provenance thực của prediction mới tại thời điểm inference: profile/schema/model/version, manifest/preprocessing identity và execution mode. Identity phải thuộc đúng model đã forward, không lấy bằng một lượt đọc riêng có thể race với đổi bundle.
- Freeze identity nguồn cho attribution; kiểm trước batch, khi resume và trước publication/cache hit. Không dựng `execution_identity` chỉ từ run rồi gọi đó là identity đã kiểm của model hiện hành.
- Với prediction cũ thiếu provenance cần thiết, có policy rõ: yêu cầu phân tích lại nếu không thể chứng minh identity. Không tự gán identity hiện tại cho dữ liệu cũ và tuyên bố đã xác minh.
- Checkpoint coalition gắn với full input IDs, grouping/method/baseline/target/seed/budget và model/preprocessing identity. Không trộn batch của phiên bản khác; cùng batch commit lại không đếm đôi.
- Full-input coalition phải đi qua cùng preprocessing, tokenizer, truncation, eval/dtype, attention-mask policy với prediction. Đối chiếu cả sentiment và topic vector, không chỉ một scalar có thể triệt tiêu sai số.
- Ngưỡng từ handoff: `max_abs_diff <= 1e-5` mỗi head; target polarity sai lệch suy ra <=0.002 điểm phần trăm, label score <=0.001. Cộng dồn float64; residual nội bộ cùng coalition outputs <=1e-6 điểm phần trăm. Không nới để test xanh.
- Đối chiếu đầy đủ target/schema/label và giá trị finite trước lưu completed. Invalid/mismatch không được chuyển thành 0 hay “Các từ còn lại”.
- Kiểm lại nguồn/revision/expiry trước cache lookup, sau tính và trong transaction publication; không giữ SQLite transaction/lock xuyên inference.
- Giữ một encoder resident, worker microbatch yield để prediction nhanh được xử lý giữa các batch. Không load torch/model nặng trong API.

Sửa test double để prediction và coalition forward cùng một hàm hợp lệ trong happy path; giữ double cố ý mismatch cho negative test. Không giảm validation để giữ test double vốn không nhất quán chạy qua.

Nghiệm thu: model/version/manifest/preprocessor đổi trước chạy hoặc giữa hai batch, worker restart/resume, source sửa/xóa/hết hạn, duplicate batch commit, cache identity khác, full input vector mismatch, NaN/Inf. Chứng minh source prediction run/count/export không bị attribution thay đổi.

### F06 — Mapping Unicode phải thực sự chính xác

- Tái hiện `"Ca\u0309m o\u031bn"`: không được gán token của cả “Cảm ơn” vào raw span chỉ chứa “C”.
- Tái hiện `"Tốt 👍🏽"` và `"Tốt 👩‍💻"`: không bọc các phần của một grapheme vào nhiều button độc lập.
- Bảo toàn raw text; nếu normalize để so khớp phải có mapping quay về raw. Kiểm đã consume đầy đủ từng token/cụm và coverage; không coi chỉ tìm được ký tự đầu là exact.
- Chuyển code point/UTF-16 đúng; boundary không cắt combining mark, surrogate pair, skin-tone emoji hoặc ZWJ cluster. Tận dụng helper grapheme/sensitivity đã có.
- Các groups tạo partition đúng tập token được giải thích; token cố định có policy rõ. Giữ negation/intensifier trong cụm khi chắc chắn. Không bỏ stopword/dấu câu âm thầm để ép phép cộng.
- IDs ghép từng nhóm phải khớp full-input tokenization của preprocessor thật. Không tự normalize input của model khác pipeline prediction chỉ để mapping dễ hơn.
- G=0, mapping không chắc, word bị truncation giữa BPE: trả unsupported phù hợp; không tô phần model chưa đọc. Không dùng unsupported như lối tránh hỗ trợ các câu tiếng Việt bình thường.

Nghiệm thu: NFC/NFD, từ lặp, nhiều whitespace/tab/CRLF, trim snapshot, underscore literal, emoji/ZWJ, dấu câu, phủ định, truncation; kiểm raw slices và token IDs bằng tokenizer thật khi có thể.

## 6. Sửa fidelity/responsive: F07–F08

- Thống nhất CSS với `.app-header/.header-inner/.input-actions/.button-primary` hoặc đổi markup có chủ đích. Dọn rules trùng/không dùng liên quan, không tiếp tục append hàng loạt override để che lỗi.
- Nút Phân tích có kích thước/spacing đúng, chữ không vỡ dòng bất thường; SVG có width/height/fill/stroke rõ. Navigation có khoảng cách và responsive đúng.
- Giữ bảng bốn cột, header teal, chữ trắng, alignment cụm/trọng số, tổng trong cột cuối, “Cách tính tổng” thu gọn mặc định. Không đổi sang dashboard KPI hoặc thêm copy dài.
- Top 6 nhóm theo abs contribution, sau đó sắp theo vị trí raw; mở đủ giữ thứ tự. Tổng luôn gồm toàn bộ groups đã tính.
- Meter của từng group: `abs(phi_i)/max(abs(phi_j))` trên các groups gốc. Toàn 0 thì thanh 0. Không dùng aggregate nhóm ẩn làm mẫu số và không vẽ meter cho aggregate đó.
- Mobile nguyên văn ở trên, từ/trọng số hai cột, tổng sau mọi dòng. Bỏ `grid-row:10` cố định; kiểm 1/6/9/15+ groups và mở/thu lại.
- Giữ whitespace bằng `pre-wrap`, text nodes an toàn; từ dài/URL không gây overflow.
- Keyboard/touch chọn highlight hai chiều, focus rõ; không chỉ dùng màu. Contrast theo handoff, reduced motion, trạng thái loading/error/empty đọc được.
- Không thay đổi số/dấu attribution để giống fixture. Màu và nội dung thật được phép khác ảnh, cấu trúc và tương tác phải đạt.

Nghiệm thu: chụp và trực tiếp xem ảnh 390/768/1440 px, kiểm nhanh 320/1920; đủ table collapsed/expanded, Negative/Neutral/Toxic, loading/unsupported/error. Không coi `to_be_visible` và đếm bốn header là kiểm chứng visual đầy đủ.

## 7. Sửa donut/network/evidence: F05, F09–F10

### Snapshot và nguồn nhãn

- Donut, topic ranking, network và evidence cùng dataset/profile/run/revision/label_source và normalized base filters. Scope token không thay thế filter identity.
- Network result có identity phiên bản/params/filter signature và source scope rõ. Dẫn chứng phải do server resolve từ network ID + selection type/ID + pagination hoặc cơ chế tương đương đã xác minh; không tin danh sách item IDs do client gửi là membership thật.
- Không lấy token summary mới ghép membership network cũ. Khi sửa câu, review nhãn, đổi run/source/filter: invalidate/refetch graph và selection phù hợp. API trả conflict khi snapshot cũ; UI refresh có thông báo ngắn.
- Test cụ thể: graph có “wifi”; sửa câu hết chứa wifi; click node cũ không được trả câu mới làm bằng chứng hợp lệ.
- Với `label_source=ai`, evidence badge lấy `prediction.sentiment/topic`; với effective thì lấy effective. Null/không có prediction xử lý đúng, không fallback sang nguồn khác âm thầm.
- Donut base denominator không đổi về 100% khi click một lát để lọc evidence. Reset pagination khi thay scope/filter; kiểm nhiều trang.
- Giữ net sentiment/counts/Toxic riêng theo handoff. Không biến softmax một câu thành tỷ lệ dataset.

### Network đúng dữ liệu, đúng phương pháp

- Mặc định network dùng cùng population có sentiment hợp lệ như donut theo source hiện hành. Dataset chưa phân tích có empty state, không tự dựng graph từ rows chưa có nhãn rồi so với denominator=0.
- Giữ vị trí token gốc trước khi bỏ stopwords. Chốt `window_size=5` là cửa sổ 5 vị trí token liên tiếp (khoảng cách chỉ số tối đa 4), trong cùng câu, không xuyên phản hồi. Version hóa rõ thay đổi semantics nếu implementation cũ dùng định nghĩa khác.
- Mỗi phản hồi chỉ góp một lần vào node/cạnh tương ứng; node/edge membership và counts khớp, community count là union IDs. Không lấy chỉ trang `/items` đầu tiên.
- Test “Wifi ở trong các phòng thì vẫn cứ bị chậm.” không có cạnh wifi–chậm dưới cửa sổ trên.
- Root chốt phương pháp grouping thực tế: có thể giữ connected components nếu gọi đúng tên và giải thích ngắn, hoặc triển khai community detection deterministic phù hợp. Không buộc thêm thư viện nặng chỉ để giữ chữ Louvain. Không khai Louvain/modularity/seed nếu code không dùng.
- Tie-breaking bằng thứ tự ổn định, không phụ thuộc hash random của set/dict. Cùng snapshot/params phải ra cùng nodes/edges/groups/layout.
- Giới hạn nodes/edges theo handoff, membership vẫn đúng. Không có quan hệ đủ dữ liệu thì empty state.
- NLP/tổng hợp nặng chạy trong worker với snapshot/job/cache bounded, không giữ transaction API khi tách từ cả dataset. Tải graph khi phần network được mở/đến viewport; tránh tự tính lại mọi lần fetch. Tận dụng cơ chế đã có, không viết lại scheduler.
- Desktop có keyboard path chọn node/cộng đồng; mobile có term picker/danh sách thay thế. Click node/cạnh/cộng đồng mở đúng evidence đã được server xác minh.

Nghiệm thu: dataset chưa có nhãn, partial labels, all-toxic, AI khác review, nhiều trang, snapshot thay đổi giữa graph và click, window trước lọc stopword, edge/community counts, deterministic output và graph keyboard/mobile.

## 8. Dọn LLM, vận hành và contract gaps: F11–F12

### F11 — Loại tích hợp LLM khỏi luồng hiện hành

- Dọn help trong `App.tsx`, client API/types/state, provider/service initialization, cấu hình/script/docs hiện hành liên quan 9router/explanation nếu không còn consumer.
- Endpoint cũ có thể bỏ hoặc trả 410 rõ ràng nếu cần compatibility; chọn và kiểm contract. Không để đường production vô tình bật lại provider chỉ vì truyền config cũ.
- Không xóa dependency dùng chung còn caller; không đọc/in secret env. Không sửa lịch sử báo cáo/nghiên cứu như thể tính năng chưa từng tồn tại.
- Giữ same-origin validation thích hợp cho POST attribution/cancel khi bỏ code explanation; không mở CORS rộng.
- Tests cũ về LLM được bỏ/đổi có chủ đích, nhưng các tình huống bảo vệ nguồn, late callbacks, retry, invalid payload phải chuyển thành regression tests của attribution. Không skip cả file để lấy suite xanh.

### F12 — Hướng dẫn chạy phải mở được app và worker

- `python -m services.api.main` hiện chỉ tạo app và thoát; không dùng nó làm bằng chứng khởi động server.
- Theo `scripts/start-local.ps1`/`stop-local.ps1` và `docs/LOCAL_APP.md`. Khi verify, truyền RuntimeDirectory riêng đã có bản copy bundle, chọn port rảnh; không chạm app/runtime live của người dùng.
- Kiểm API health, worker heartbeat, request thật và frontend tại URL trả về. Báo chính xác URL đã kiểm, không mặc định 8000. Không tự kill process đang chiếm port.
- Chỉ để lại dev server do phiên này sở hữu nếu cần cho người dùng xem kết quả; ghi cách dừng đúng runtime. Các test helpers tạm phải được cleanup.

### Các gaps đã ghi trong review, phải xử lý cùng đợt

- Idempotency-Key hợp lệ bắt buộc cho tạo attribution; dùng UUID mới cho generation/target/attempt mới, giữ key trên transport retry. Same key khác payload/source trả 409, kể cả key từng được gắn với cache hit.
- Hai tab/handle độc lập không cancel lẫn nhau. P0 không cần coalesce in-flight; shared completed cache không cho phép sửa kết quả của handle khác. Cancel terminal trả trạng thái thực tế, không báo cancelled trong khi GET vẫn completed.
- Queue tối đa khởi điểm 10, concurrency attribution 1, cache thành công tối đa 100, TTL tối đa 900 giây và không vượt source expiry; version/config theo bằng chứng. Queue đầy trả 429 phù hợp, không bịa retry progress.
- Compute deadline mặc định 60 giây, bounded bởi source expiry; chốt rõ thời gian compute so với chờ queue, không reset deadline sau mỗi microbatch/resume.
- Cleanup, source deletion và lease fencing ngăn worker muộn tái công bố kết quả; không gia hạn nguồn do cache hit. Không giữ locks trong inference.

## 9. Kiểm thử và bằng chứng bắt buộc

Baseline của review, chỉ để tham khảo; chạy lại trạng thái hiện tại:

- Build frontend PASS.
- Pytest ngoài E2E: 370 passed, 3 failed, 4 real_model deselected. Ba failures là expectation explanation status và database version chưa cập nhật; không tự suy ra DB hỏng.
- Năm E2E redesign mới PASS trên TestOnlyRegistry; chưa bao phủ các race/target/unsupported nêu trên.
- Test model thật hiện có PASS nhưng chỉ một câu và một scalar polarity. Các ảnh bảng bàn giao có watermark test double, weights=0; không phải nghiệm thu end-to-end model thật.

### Chiến lược test

1. Tạo/reuse regression test tái hiện lỗi trước khi sửa; kiểm test fail đúng nguyên nhân. Không cần thêm test chỉ kiểm lại literal/style của implementation hoặc mọi thay đổi copy nhỏ.
2. Chạy tests liên quan sau mỗi phần sửa. Root tích hợp rồi chạy build và full suite thích hợp một lần; chỉ chạy lại khi có sửa mới/failure cần xác minh.
3. Cập nhật tests schema version ở `tests/api/test_sensitivity.py`, `tests/api/test_workspace.py`, backup/health và các nơi liên quan. Giữ assertion dữ liệu bền/export bytes/migration concurrency, không chỉ đổi số rồi bỏ phần kiểm còn lại.
4. Rà toàn bộ E2E cũ: loại expectation cho feature bị bỏ, chuyển bảo vệ còn giá trị sang attribution. Full suite kết thúc được; không coi một lượt dừng giữa chừng là pass.
5. Tests API phải kiểm source/identity/cancel/queue/TTL/resume thực sự, không chỉ happy-path completed.

Lệnh gợi ý từ repo root, điều chỉnh theo tests đã thêm và interpreter đã xác minh:

```powershell
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest tests/test_attribution_engine.py tests/api/test_attribution_lifecycle.py tests/api/test_network.py -q
.\.venv\Scripts\python.exe -m pytest --ignore=tests/e2e -q
.\.venv\Scripts\python.exe -m pytest tests/e2e -q
```

`pytest.ini` mặc định loại real_model. Sửa real-model tests sang isolated bundle fixture trước khi chạy opt-in:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:FEEDBACK_REAL_BUNDLE_TEMPLATE = 'F:\DPL_NEU-ESC\runtime\models'
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_attribution_real_model.py -q
```

Biến template chỉ được đọc để copy bundle; không dùng làm runtime ghi trực tiếp. Không coi test skip là model PASS. Nếu dependencies ở `.venv-modelcheck`, dùng interpreter đã kiểm chứng và ghi trong report.

### Model thật và visual acceptance

- Kiểm mapping/IDs và hai vector scores trên tập câu tác giả viết đa dạng, không dùng benchmark test split để chọn phương pháp đẹp.
- Bao gồm mixed praise/criticism, Neutral/Toxic, phủ định/cường độ, lặp từ, Unicode/emoji, câu dài. Nhãn semantic category do tác giả dự định không bảo đảm model dự đoán đúng category; test target theo prediction thực, không sửa nhãn/score để khớp câu chuyện.
- Không assert mọi lần từ “thân thiện” luôn dương hay “chậm” luôn âm. Kiểm tính đúng thuật toán/identity/partition và báo hạn chế nếu dấu khó hiểu.
- So ít nhất hai bộ permutation độc lập cho vài câu; báo ổn định/không ổn định của nhóm mạnh. K=8 là ước lượng Shapley, không gọi là exact Shapley chỉ vì cộng khớp.
- Đo ít nhất 20 lượt warm trên các câu khác nhau, báo median/p95/max, cold-start riêng, groups/coalitions/batch/hardware. Không suy “luôn <350ms” từ một phép đo batch.
- Nếu warm p95 vượt 15 giây sau tối ưu hữu hạn, chuyển sang nút tính theo yêu cầu như handoff đã cho phép; prediction vẫn xuất hiện ngay. Không mở rộng thành dự án tối ưu vô hạn.
- Có ít nhất một E2E thật: câu mới không nằm trong mockup → prediction → completed attribution → chọn highlight/dòng → mở cách tính → kiểm số và identity. Chụp desktop/mobile của UI thật và đọc ảnh.
- Screenshot trạng thái unsupported/error/loading và dữ liệu network nếu đã làm; ghi rõ ảnh nào dùng real model, ảnh nào dùng test double. Không trộn chúng trong cùng nhãn bằng chứng.

## 10. Hoàn tất và bàn giao

Trước khi tuyên bố xong:

- Root/reviewer kiểm lại F01–F12 và các gaps phần 8, đối chiếu cả R01–R09. Nếu finding không còn áp dụng phải có bằng chứng, không bỏ qua im lặng.
- Kiểm diff không có thay đổi ngoài scope, không làm mất user edits hoặc fixtures/mockup, không sửa model nguồn/live runtime. Không tự commit/push.
- Cập nhật `docs/WEBAPP_ATTRIBUTION_CONTRACT.md` theo implementation thật; cập nhật `PRODUCT.md`, `DESIGN.md`, `docs/LOCAL_APP.md` và hướng dẫn vận hành liên quan.
- Giữ review cũ làm mốc lịch sử. Báo cáo Gemini cũ thêm chỉ dẫn bị thay thế ở đầu thay vì tiếp tục để người đọc hiểu là nghiệm thu hiện tại.
- Tạo `docs/CODEX_WEBAPP_FIX_REPORT_2026-11-12.md` với bảng F01–F12 + contract gaps: FIXED/PARTIAL/BLOCKED, file/test/bằng chứng; bảng R01–R09; kết quả tests thật, screenshots, benchmark và URL đã kiểm.
- Bằng chứng model thật còn thiếu thì nói thiếu; không dùng test doubles, một scalar hay tổng residual=0 để thay cho toàn bộ nghiệm thu.
- Nếu gặp blocker thật, ghi trigger/nguyên nhân/bằng chứng và hoàn tất phần độc lập. Không dừng chỉ vì đã sửa vài lỗi hoặc phần giao diện đã trông ổn.

Final response bằng tiếng Việt: phần bắt buộc hình 1–2 đạt chưa, các lỗi còn lại, tests thực sự đã chạy, model thật đã kiểm đến đâu, link report/screenshots và URL mở app. Không báo “toàn bộ PASS” nếu còn thiếu bằng chứng hoặc lỗi đã biết.

**Bắt đầu ngay bằng khảo sát hiện trạng, checklist thực thi ngắn và tái hiện các lỗi ưu tiên; sau đó sửa code, kiểm thử và bàn giao.**
