# Báo cáo sửa webapp Codex · 12/11/2026

> Donut demo hiện dùng tỷ trọng đóng góp cụm từ, thay cho counts/net sentiment mô tả ở mốc lịch sử bên dưới. Bằng chứng cập nhật: [CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md](CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md).

> Cập nhật theo yêu cầu tiếp theo của người dùng: phần demo “Bộ phản hồi”/network nay chỉ theo **câu mới nhất**, bỏ dataset selector và lưu câu thủ công. Bằng chứng mới ở [LATEST_SENTENCE_FIX_2026-11-12.md](LATEST_SENTENCE_FIX_2026-11-12.md). Số liệu/ảnh bên dưới là mốc nghiệm thu trước thay đổi phạm vi này; bộ dữ liệu kiểm thử Codex đã được gỡ khỏi app.

## Kết quả và phạm vi

Đã sửa tiếp bản triển khai Gemini, giữ yêu cầu của Đạt: bảng bốn cột desktop, highlight hai chiều, thanh đo từng nhóm từ và Tổng đóng góp trong bảng; mobile đặt tổng sau các dòng. Prediction local vẫn hiển thị độc lập. Donut/topic/network/evidence cùng snapshot và nguồn nhãn. Các thay đổi được kiểm trên runtime riêng; không commit, push, deploy, train, thay weights/current pointer nguồn hoặc mở/migrate database live.

Đây là báo cáo nghiệm thu hiện hành thay cho các kết luận PASS của báo cáo Gemini và feasibility cũ. Review gốc được giữ nguyên. Contract thực tế: [WEBAPP_ATTRIBUTION_CONTRACT.md](WEBAPP_ATTRIBUTION_CONTRACT.md).

**Trạng thái bàn giao:** full E2E đã hoàn tất145/145, backend381/381. Sau một dòng CSS cho phép chữ nghiêng với font local, build,10 ca bố cục và E2E model thật đều qua; ảnh desktop/mobile cuối đã mở xem trực tiếp. Không còn finding F01–F12 hoặc contract gap đã biết chưa xử lý trong phạm vi kiểm. Giới hạn model/ước lượng được ghi riêng bên dưới.

## Ma trận F01–F12

| Finding | Trạng thái implementation | Thay đổi chính và file | Test/bằng chứng |
|---|---|---|---|
| F01 · target sai index | FIXED | `SentenceDemo.tsx`, `useAttribution.ts`, `services/attribution.py`, `storage/db.py`: resolve key profile case-insensitive, vector theo schema; Neutral/Toxic label score, Positive/Negative polarity; strict label ID | `test_attribution_engine.py::test_every_target_uses_profile_keys_and_schema_order`, `test_target_vector_order_is_schema_order_not_label_id`; API `test_every_schema_target`, `test_invalid_labels_rejected`; E2E bảy target NEU/UIT; checkpoint thật Neutral/Negative/Toxic |
| F02 · kết quả cũ ghi đè | FIXED | `useAttribution.ts` capture generation/source/target trước await; POST muộn vẫn cancel đúng handle cũ; UUID ổn định trên transport retry; `attributionValidation.ts` kiểm payload trước render | `test_attribution_regressions.py`: late POST/error/cache, clear/profile/unmount, double submit, cancel A giữ B; invalid identity/hash/spans/token order/NaN/aggregate |
| F03 · polling không kết thúc | FIXED | Terminal và HTTP404/410/409/422 dừng; network/5xx retry hữu hạn; GET recovery giữ handle; lỗi attribution giữ prediction; unsupported có lý do | E2E terminal/error request counts, GET recovery không tạo prediction/POST mới, cancel queued/running/completed và terminal retry UUID mới; ảnh loading/truncation/410 thật |
| F04 · sai prediction/model nguồn | FIXED | `registry.py` lưu identity ngay forward; `attribution_contract.py`, `db.py`, `worker.py` freeze/check identity mỗi batch/resume/publication/cache; coalition lưu cả hai vector; dữ liệu cũ thiếu provenance yêu cầu phân tích lại | API invariants + registry race tests: model/manifest/preprocessor đổi, mismatch hai head, NaN, source sửa/xóa/expiry, GET race, duplicate commit/restart; benchmark20 câu và browser thật |
| F05 · network/evidence khác snapshot | FIXED | `network_jobs.py`: normalized filters + signature; evidence server resolve bằng network ID và selection; conflict409 khi snapshot đổi; UI refetch/clear selection | API31 rows/4 trang, sửa wifi và node cũ409, run/review/source filters, subset item IDs và signature; E2E scope409/recovery và network keyboard |
| F06 · Unicode/span sai | FIXED | `attribution.py`: mapping NFD so khớp toàn raw grapheme, không đổi pipeline model; merge emoji/ZWJ fragments; partition đủ token, >24 group gộp liền kề; truncation unsupported | NFC/NFD “Ca\u0309m o\u031bn”, 👍🏽/👩‍💻, từ lặp, tab/CRLF, underscore, negation, punctuation, truncation;20 câu tokenizer/checkpoint thật kiểm IDs và hai head |
| F07 · markup/CSS/fidelity | FIXED | `SentenceDemo.css`, table/highlight/components thống nhất selectors; header/nav/button/SVG; bảng50/21/15/14 teal trắng; label-score header wrap theo tên nhãn | Root xem ảnh thật390/768/1440 và kiểm320/1920; polarity/Neutral/Toxic; full desktop/mobile; E2E route/nav và zero overflow |
| F08 · tổng mobile/meter aggregate | FIXED | Top6 abs(phi) rồi raw order; meter theo max groups gốc; aggregate chỉ số; mobile tổng cuối dynamic; raw pre-wrap | E2E1/6/9/16 groups mở/thu, raw snapshot; ảnh thật collapsed/expanded desktop390/1440,320/768/1920 |
| F09 · badge sai nguồn | FIXED | `SentenceDemo.tsx`: AI lấy `prediction.sentiment/topic`, effective lấy effective; không fallback im lặng | E2E review khác AI vẫn badge AI Negative; source switch/pagination; API network AI/effective/partial và report scope |
| F10 · network population/window/method | FIXED | Worker tính NLP từ snapshot có sentiment hợp lệ; window5 vị trí gốc trước stopword, distance<=4; connected components/layout sunflower deterministic;40 nodes120 edges; counts union IDs | `test_text_network.py`8 cases: window, câu/feedback boundaries, counts/limits, hash randomization, API import không NLP; network API5 cases + browser thật graph/evidence/mobile |
| F11 · LLM còn consumer | FIXED | Xóa `services/explanation.py` và provider-only tests; bỏ client API/types/help/state LLM; endpoint legacy410, kwargs cũ không khởi tạo provider; giữ same-origin và httpx có caller | API legacy410/provider trap/origin; guards nguồn và race/retry chuyển sang attribution; full suite không skip cả file; docs vận hành cập nhật |
| F12 · lệnh chạy không mở app | FIXED | Dùng `start-local.ps1`/`stop-local.ps1` đúng RuntimeDirectory; output stop command sửa theo runtime | Preview18765 health/schema4/worker heartbeat, request và browser thật; đã kiểm start idempotent, stop/restart process của phiên |

## Contract gaps đã đóng

| Gap | Trạng thái | Bằng chứng |
|---|---|---|
| UUID bắt buộc; cùng key không rebind source/payload kể cả cache hit | FIXED | `test_uuid_required`, lifecycle idempotency, publication cache-key conflict; E2E transport retry cùng UUID, terminal retry UUID mới |
| Hai handle/tab độc lập; cancel terminal trả status thực | FIXED | `test_cache_handle_idempotency_and_cancel_isolation`; running lease revoke/fence; browser late cancel completed giữ completed |
| Queue10/concurrency1, cache thành công100, TTL<=900 và source expiry | FIXED | queue-limit invariant; publication tạo103 handle và còn đúng100 reusable cache; handle đầu vẫn đọc; expiry không bị cache hit gia hạn; cache hết hạn không reuse |
| Compute60s từ claim đầu, không reset mỗi yield/resume | FIXED | `test_queue_limit_and_nonresetting_compute_deadline`; deadline hết ngay trong forward không commit batch; quick prediction preempts batch mà deadline giữ nguyên |
| Cleanup/source deletion/lease fencing; không lock xuyên inference | FIXED | cancel-running late batch, source edit/delete/expiry tại forward/publication; FK cleanup và backup loại dữ liệu quick; transaction chỉ snapshot/check/commit ngoài forward |
| Migration đã áp dụng không bị sửa | FIXED | Migration4 nối tiếp3; test v3→v4 + backup/restore giữ CSV bytes và durable rows, foreign_key_check; existing migration concurrency tests giữ nguyên |
| Checkpoint đủ IDs/groups/method/target/source; duplicate commit | FIXED | full signature; coalition unique mask, progress COUNT; restart/resume và duplicate batch regression; scalar/vector target crosscheck |
| Network filter identity ngoài scope token | FIXED | subset2/3 IDs, sort/dedup cùng signature/network ID; base có cùng scope token nhưng filter signature khác; node/edge/community evidence không lẫn row bị loại |

## Đối chiếu R01–R09 và hình của Đạt

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| R01 · bỏ chữ thừa/câu mẫu | ĐẠT | Không còn ba nút mẫu/câu phụ nguyên văn; vẫn giữ nội dung raw; redesign test và ảnh full page |
| R02 · bỏ khối lớp | ĐẠT | Không còn nhãn Lớp1/2/3 hoặc đổi tên để giữ các đoạn cũ |
| R03 · giữ prediction | ĐẠT | Sentiment/điểm/topic, phân bố sentiment và đầy đủ topic; lỗi attribution vẫn prediction; profile UIT không checkpoint báo unavailable |
| R04 · hình1 bảng bắt buộc | ĐẠT | Desktop4 cột50/21/15/14, header teal/trắng, weights/cụm căn hàng, tổng cột cuối; table thật polarity/Neutral/Toxic và số không bị sửa để giống fixture |
| R05 · hình2 highlight | ĐẠT | Click/keyboard hai chiều highlight↔dòng; đúng occurrence/spans/grapheme; root xem ảnh mobile và desktop |
| R06 · thanh nhỏ | ĐẠT | abs(phi)/max(abs(phi_all)); all0→0; aggregate không meter; dấu/legend theo target |
| R07 · bỏ LLM | ĐẠT | Production không provider/service/client/help9router; legacy410 và same-origin guards |
| R08 · donut/topic/evidence | ĐẠT | Counts/denominator thật, Toxic riêng, thiếu nhãn/partial/all-toxic; source/snapshot/pagination guards; topic click lọc Negative+topic; không đổi base donut denominator |
| R09 · network | ĐẠT | Snapshot worker async, window5 positions, counts/memberships/connected components công bố đúng; lazy query; keyboard node/cạnh/community và mobile picker; browser thật server evidence |

Hình1–2 đã đạt về cấu trúc, tương tác và dữ liệu model thật trong phạm vi kiểm. Đã trực tiếp xem ảnh chuẩn trong `design-previews/2026-11-12` và ảnh app thật; không dùng weights=0 của fixture để kết luận model đạt. Bảng label-score dùng tiêu đề “Trọng số / cho nhãn …” để tránh gọi tăng Toxic là tích cực. Bảng polarity giữ “Trọng số cảm xúc”.

Kiểm tích hợp phát hiện và sửa thêm network legend/picker/sidebar chồng trên mobile; thử độ nhạy có wrapper mở nhưng native details vẫn closed trong khi summary bị CSS ẩn. `SensitivityPanel` nay có chế độ embedded cho demo, còn workspace giữ native toggle. Font ô bảng độ nhạy giữ tối thiểu14px tại các viewport đã test. Review UI cuối bổ sung guard terminal và request epoch: GET polling cũ không được che completed vừa được khôi phục sau cancel; regression điều khiển các phản hồi500/404/failed về muộn.

## Kiểm thử thực thi

Evidence root: [`test-results/codex-fix-20261112`](../test-results/codex-fix-20261112/). Python dùng `.venv\Scripts\python.exe`3.10.11 đã có đầy đủ dependencies. Không cài lại/tải model.

Tổng hợp máy đọc được của health và các XML cuối: [final-evidence-summary.json](../test-results/codex-fix-20261112/final-evidence-summary.json).

| Lượt | Kết quả thực tế | Artifact/giới hạn |
|---|---|---|
| Frontend production build cuối | PASS, `tsc -b && vite build` |94 modules; JS452.22kB/CSS71.00kB; assets `index-CTMzxdxw.js`, `index-BbuWcFEC.css`; [build.log](../test-results/codex-fix-20261112/build.log) |
| Backend full ngoài E2E cuối |381 passed,5 real_model deselected,89.94s |[`backend.xml`](../test-results/codex-fix-20261112/backend.xml), bao gồm regression network item_ids cuối |
| API network sau bổ sung subset |5 passed,7.08s |TestOnlyRegistry, runtime tạm; bao gồm regression subset mới |
| Full E2E lượt đầu |135 passed,7 failed,714.50s |Lượt hoàn tất, lỗi tests cũ và hai regression UI được sửa tiếp; không gọi lượt này PASS |
| Full E2E sau sửa giao diện/expectations |142 passed,615.19s |[`e2e-before-final-poll-guard.xml`](../test-results/codex-fix-20261112/e2e-before-final-poll-guard.xml); trước bổ sung guard poll/cancel cuối |
| Targeted7 sau sửa |6 passed,1 failed,33.86s |Lỗi còn lại là font cell sensitivity11.2px, đã sửa source14px; XML targeted giữ lịch sử |
| Targeted font sensitivity cuối |1 passed,9.71s |[`e2e-sensitivity.xml`](../test-results/codex-fix-20261112/e2e-sensitivity.xml);1440/1280/768/390/320 không overflow, font>=14px |
| Regression poll/cancel trên build cũ |2 failed,1 passed,23.42s |[`poll-guard-repro-before.xml`](../test-results/codex-fix-20261112/poll-guard-repro-before.xml);404/failed về muộn xóa bảng completed, fail đúng nguyên nhân |
| Regression poll/cancel sau sửa |3 passed,13.23s |[`poll-guard-after.xml`](../test-results/codex-fix-20261112/poll-guard-after.xml);completed/prediction giữ nguyên, không poll thêm |
| Full E2E sau guard poll/cancel |145 passed,624.82s |[`e2e.xml`](../test-results/codex-fix-20261112/e2e.xml), hoàn tất không ngắt; trước một dòng CSS font-synthesis cuối |
| Bố cục sau CSS chữ nghiêng cuối |10 passed,43.43s |[`e2e-final-font.xml`](../test-results/codex-fix-20261112/e2e-final-font.xml); redesign, mobile groups và long URL/sensitivity |
| Checkpoint benchmark offline |1 passed,38.88s, không skip |[`real-model-benchmark.json`](../test-results/codex-fix-20261112/real-model-benchmark.json) |
| E2E API+worker+browser model thật trên build cuối |1 passed,31.21s, không skip |[`real-browser.xml`](../test-results/codex-fix-20261112/real-browser.xml), [`real-browser-evidence.json`](../test-results/codex-fix-20261112/real-browser-evidence.json); page_errors=[] |

Các lần fail trước sửa không bị che bằng skip/xóa guards. Các tests LLM provider-only bị bỏ có chủ đích vì consumer đã xóa; nguồn/late callback/retry/invalid payload chuyển sang attribution. Test double prediction và coalition dùng cùng software score game, các negative test cố ý mismatch vẫn bị từ chối.

Lệnh tái kiểm:

```powershell
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest --ignore=tests/e2e -q --tb=short --junitxml=test-results/codex-fix-20261112/backend.xml
$env:SENTENCE_DEMO_SCREENSHOT_DIR='F:\DPL_NEU-ESC\test-results\codex-fix-20261112\test-double'
.\.venv\Scripts\python.exe -m pytest tests/e2e -q --tb=short --junitxml=test-results/codex-fix-20261112/e2e.xml

$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
$env:FEEDBACK_REAL_BUNDLE_TEMPLATE='F:\DPL_NEU-ESC\runtime\models'
$env:FEEDBACK_FIX_EVIDENCE='F:\DPL_NEU-ESC\test-results\codex-fix-20261112'
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_attribution_real_model.py -q -s

$env:FEEDBACK_FIX_APP_URL='http://127.0.0.1:18765'
$env:FEEDBACK_FIX_RUNTIME='F:\DPL_NEU-ESC\test-results\codex-fix-20261112\preview-runtime'
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_attribution_live_browser.py -q --tb=short --junitxml=test-results/codex-fix-20261112/real-browser.xml
```

Template model nguồn chỉ đọc và copy qua `_verify_and_copy_active_bundle`; không dùng làm writable runtime. Default pytest deselect real_model, nên kết quả benchmark/browser opt-in được báo riêng.

## Kiểm checkpoint thật và hiệu năng

Bundle NEU: `neu-phobert-mtl-ed-s42-e10-617f852a3fff`; model ID `neu-phobert-mtl-ed-s42`; schema `neu-v1`; CPU FP32 eval,4 threads, microbatch8, K8. Hardware string: `AMD64 Family 25 Model 80 Stepping 0, AuthenticAMD`; torch2.14.1+cpu. Benchmark chạy tuần tự, không encoder song song.20 câu tác giả viết, không lấy test split để chọn phương pháp; gồm mixed polarity, phủ định/cường độ, từ lặp, NFC/NFD, tab/CRLF, underscore, emoji/ZWJ và câu dài.

| Phép đo | Kết quả | Phạm vi |
|---|---|---|
| Cold bundle load |4.182s |Chỉ load bundle; không phải toàn cold-start UI |
|20 warm attribution, median/p95/max |0.832 /1.685 /7.010s |Compute-only `_calculate`: coalition inference+Shapley; không queue/API/poll hoặc mapping lặp trong worker |
| Groups/unique coalitions |6–23 /27–176 |Batch8, K8 |
| Max_abs_diff sentiment/topic |4.1723e-7 /5.3644e-7 |Mỗi head dưới1e-5, full IDs khớp preprocessor/tokenizer prediction |
| Residual cộng dồn lớn nhất |0 điểm phần trăm |Ngưỡng1e-6, không bù/clamp số |
| Warm prediction median/max |0.0654 /0.0888s |Forward path; không suy ra luôn dưới350ms ở UI |
| Browser từ submit đến prediction |1.464–1.513s |4 câu thật; gồm API/poll/render, worker đã warm |
| Browser đến bảng và tương tác kiểm |3.081–4.602s |Bao gồm chờ bảng và một số thao tác kiểm chọn/cách tính; không phải compute-only |

Hai seed42 và9173 trên3 câu: dấu của3 nhóm mạnh seed42 trùng3/3 cho cả3 câu; top3 overlap chỉ2/3,2/3,1/3. **Thứ hạng chưa ổn định**, dù dấu nhóm mạnh trong mẫu nhỏ này ổn định. K8 là Shapley ước lượng, additivity không biến thành exact Shapley hoặc nhân quả. Một từ tốt có thể đóng góp âm trong ngữ cảnh; không assert dấu theo trực giác hoặc sửa trọng số cho đẹp.

Trong20 câu benchmark, câu tác giả dự định Toxic không được model dự đoán Toxic. Browser dùng một câu tác giả viết khác và **thực sự nhận label3 Toxic**, target label_score3; Neutral label0 và Negative label2 cũng được kiểm. Positive có trong benchmark. UIT chưa có checkpoint production: schema/API/UI được kiểm qua doubles, production vẫn unavailable; chưa có bằng chứng encoder UIT thật và không tuyên bố có.

Warm p95 compute-only thấp hơn15s, giữ tự tính attribution sau prediction. Đây không phải SLA cho mọi máy/câu; deadline60s vẫn áp dụng.

Integrity cuối:13 files trong inventory nguồn và copy khớp SHA-256; pointer byte-identical, checkpoint khớp benchmark. [source-integrity.json](../test-results/codex-fix-20261112/source-integrity.json): checkpoint `036b62c7b24fbe10ba30562090908fe8c81d0ebe339a84ad9fb02a569b2e20b1`, manifest `5117b413d141d4e6b80a2805b9b5ff27b353d404d3a42bc95c29055e4f527b1d`.

## Ảnh nghiệm thu đã mở xem trực tiếp

Tất cả ảnh có prefix `real-` dưới đây dùng **checkpoint thật offline, API+worker trong preview-runtime**. Loading được giữ POST trong browser rồi tiếp tục request nguyên vẹn; lỗi410 được tạo bằng cách hết hạn riêng source quick của phiên khi GET đang giữ; prediction thật vẫn hiển thị và polling dừng. Không sửa source live. Network ở mốc ảnh lịch sử này dùng dataset4 câu tác giả viết đã chạy model thật; bằng chứng luồng câu mới nhất nằm trong báo cáo cập nhật ở đầu tài liệu.

Ảnh cuối xác nhận polarity âm hiển thị đỏ nghiêng. Cấu hình toàn cục trước đó chặn synthetic italic trong khi bundle font local chỉ có normal faces; demo cho phép `font-synthesis: style`, giữ Be Vietnam Pro và không tải font ngoài. JSON browser ghi family/synthesis/negative_style thực tế.

| Nội dung | Ảnh |
|---|---|
| Hình1 polarity desktop/mobile |[1440](../test-results/codex-fix-20261112/real-polarity-1440.png), [390](../test-results/codex-fix-20261112/real-polarity-390.png) |
| Neutral collapsed5 widths |[320](../test-results/codex-fix-20261112/real-table-320-collapsed.png), [390](../test-results/codex-fix-20261112/real-table-390-collapsed.png), [768](../test-results/codex-fix-20261112/real-table-768-collapsed.png), [1440](../test-results/codex-fix-20261112/real-table-1440-collapsed.png), [1920](../test-results/codex-fix-20261112/real-table-1920-collapsed.png) |
| Hình2 mở đủ/selection |[Desktop](../test-results/codex-fix-20261112/real-table-1440-expanded.png), [mobile tổng cuối](../test-results/codex-fix-20261112/real-table-390-expanded.png) |
| Negative/Toxic thực |[Negative](../test-results/codex-fix-20261112/real-negative.png), [Toxic label3](../test-results/codex-fix-20261112/real-intended-toxic.png) |
| Header/prediction/button/full page |[Desktop](../test-results/codex-fix-20261112/real-page-desktop.png), [mobile](../test-results/codex-fix-20261112/real-page-mobile.png) |
| Loading/unsupported/error |[Loading](../test-results/codex-fix-20261112/real-prediction-loading-attribution.png), [truncation](../test-results/codex-fix-20261112/real-unsupported-truncation.png), [source410](../test-results/codex-fix-20261112/real-source-expired-error.png) |
| Network/evidence thật |[Desktop](../test-results/codex-fix-20261112/real-network-desktop.png), [390](../test-results/codex-fix-20261112/real-network-mobile.png), [320](../test-results/codex-fix-20261112/real-network-320.png), [server evidence](../test-results/codex-fix-20261112/real-network-evidence.png) |

Ảnh E2E trong `test-double/` và `artifacts/screenshots_2026_11_12/` dùng **TestOnlyRegistry/software fixtures**, chỉ chứng minh lifecycle/layout/regression; không gộp vào bằng chứng checkpoint thật. Mockup trong `design-previews/2026-11-12/` là chuẩn bố cục, không phải inference.

## Chạy và dừng bản kiểm

URL đã kiểm: [http://127.0.0.1:18765/#/demo](http://127.0.0.1:18765/#/demo). Runtime riêng: `F:\DPL_NEU-ESC\test-results\codex-fix-20261112\preview-runtime`. API+worker thuộc phiên này, schema4, heartbeat alive. Bundle nguồn không được dùng làm runtime ghi. Theo yêu cầu cập nhật, nhập và phân tích câu mới để xem bảng, donut/network/evidence của đúng câu đó; bộ **Kiểm chứng Codex · model thật** và bộ chọn dataset trong demo đã được gỡ.

```powershell
.\scripts\start-local.ps1 -Port 18765 -RuntimeDirectory 'F:\DPL_NEU-ESC\test-results\codex-fix-20261112\preview-runtime'
.\scripts\stop-local.ps1 -RuntimeDirectory 'F:\DPL_NEU-ESC\test-results\codex-fix-20261112\preview-runtime'
```

Start/stop chỉ quản lý process ghi trong runtime này. Các test helpers tạm dùng fixture teardown. Không kill process/cổng khác của người dùng. `python -m services.api.main` không phải lệnh chạy server.

## Giới hạn còn lại

Không có checkpoint UIT nên chưa kiểm model UIT thật. K8 có biến động thứ hạng giữa permutation seeds; masked baseline khác phân phối ngôn ngữ tự nhiên. Mapping/truncation không chắc trả unsupported và giữ prediction; không tô phần model chưa đọc. Bộ20 câu là kiểm tính đúng kỹ thuật và đo hữu hạn, không đánh giá accuracy/fairness hoặc SLA sản phẩm. Scope/refetch/late callbacks có regression doubles để điều khiển timing; không nhầm với benchmark model thật.

Phân công: root contract/API/storage/worker/migration/shared interfaces/build/model/browser/integration; engine mapping/registry/network; UI components/hooks/validation/responsive; operations dọn LLM/docs và tests vận hành. Review cuối chỉ đọc không thấy blocker backend mới; engine reviewer cũng là tác giả một phần engine/network, không được trình bày là độc lập hoàn toàn. Root xác minh tích hợp trực tiếp và đọc ảnh thật.
