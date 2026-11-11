# Report sửa Sentence Demo và diễn giải kết quả — 11/11/2026

F01–F12, U01–U20 và các gap bổ sung đã được xử lý trong phạm vi code + doubles. Nghiệm thu cuối: **216 unit/API pass; 104 ca E2E phân biệt pass qua hai lượt; 0 ca chưa pass, 0 skip**. Style/layout teal đã duyệt được giữ. Model thật và 9router thật **chưa chạy**; không có kết luận về chất lượng ngữ nghĩa của chúng.

Evidence: [codex-sentence-demo-fix-7d1f0e4aaec5](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5).

Tiêu chí: [plan](F:/DPL_NEU-ESC/docs/SENTENCE_DEMO_UI_9ROUTER_GEMINI_PLAN_2026-11-11.md), [fix prompt](F:/DPL_NEU-ESC/docs/SENTENCE_DEMO_UI_9ROUTER_CODEX_FIX_PROMPT_2026-11-11.md) và [review gốc](C:/Users/Admin/AppData/Local/Temp/codex-sentence-review-f01d532ec67042fb896b78056ab9ac72/CODEX_REVIEW.md). [Report implementation cũ](F:/DPL_NEU-ESC/docs/SENTENCE_DEMO_UI_9ROUTER_IMPLEMENTATION_REPORT_2026-11-11.md) và hai thư mục evidence lịch sử được giữ nguyên.

## Baseline, phạm vi và bảo toàn

- Workspace: F:\DPL_NEU-ESC. Branch đầu/cuối: **webapp**. HEAD đầu/cuối: **36e4f8e1b905912f98b270ec1e675b3624a0cf3f**.
- Snapshot lúc 2026-11-11T09:43:06.033710+00:00: toàn bộ HEAD + staged + unstaged + non-ignored untracked hiện hữu; **242 file**, không có exclusion thực tế trong danh sách baseline. Không lấy riêng HEAD làm baseline.
- [baseline.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/baseline.json), [snapshot](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/snapshot), [staged.diff](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/staged.diff), [unstaged.diff](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/unstaged.diff).
- Không có AGENTS.md áp dụng trong repo hoặc F:\AGENTS.md. Đã đọc plan, review/probes, report implementation cũ, PRODUCT/DESIGN và mockup; dùng skill fk để kiểm context/design hiện hữu, không redesign.
- Delta: **19 file baseline được sửa + 9 file mới = 28 file**. [fix.delta.diff](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/fix.delta.diff) được tạo từ snapshot working tree, gồm cả file baseline vốn untracked và file mới.
- [preservation-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/preservation-verification.json) đối chiếu byte/hash của 242 bản snapshot, 223 file baseline ngoài scope và **60 artifact lịch sử** đã ghi nhận. Mockup, fonts/license, plan, prompt, report cũ và evidence lịch sử giữ nguyên. Branch/HEAD/staged state giữ nguyên; không có thay đổi ngoài allowlist.
- Git-ignored runtime/data/model/credentials, venv/node_modules/cache không thuộc snapshot và không được duyệt nội dung. Không tuyên bố kiểm hash file ignored ngoài danh sách đã ghi. Dist generated được đối chiếu riêng.
- Không commit/amend/push/deploy/đổi branch; không dừng server người dùng, không dùng runtime người dùng hoặc localhost:8765. Browser/API tests dùng runtime riêng, port ephemeral và chỉ cleanup process fixture của phiên test.

## Quyết định và kết quả từng finding

| ID | Trước sửa | Sau sửa và chứng cứ chính |
|---|---|---|
| F01 | Quick Item luôn bị 422 khi tạo sensitivity. | Quick source có marker server quick-analysis-v1, job completed, đúng một item/run và identity hợp lệ được hỗ trợ. Validator chung kiểm revision/hash, prediction/run/schema/model, vector/warnings/token count/TTL; vẫn từ chối temporary khác/nested sensitivity. Experiment không hết hạn muộn hơn source. Cleanup phụ thuộc trước source, worker fence ngăn output muộn; không migration/copy sang dataset bền. API quick-sensitivity 22 ca và UI long-URL/sensitivity kiểm success/cancel/retry/Unicode/stale/expiry, giữ source/review/provenance. |
| F02 | Provider nhận id/scores thiếu nghĩa nhãn. | Payload load canonical profile, mỗi id/key/name/score và tên top1, cả NEU/UIT; prompt result-explanation-v2. Provider-boundary tests đối chiếu NEU sentiment3=Toxic, UIT sentiment0=negative và toàn bộ vector. Không tạo mapping nhãn thứ hai. |
| F03 | Response A có thể phục hồi UI sau edit/clear/unmount hoặc ghi đè B. | Generation/identity sau await ở success/error/finally, synchronous pending refs chống same-tick submit/retry; cleanup request/timer. Accepted response muộn có best-effort job cancel. Gate tests thả late success/error, transport bỏ qua AbortSignal, A/B và envelope sai identity; context mới vẫn đúng. Client abort không được coi là upstream cancel. |
| F04 | Stale/expired source vẫn lấy cache hoặc success sau provider. | Validator trước cache, sau queue/slot, sau provider và trước trả từng subscriber. Digest gồm snapshot/prompt/policy/provider fingerprint, không secret thô. Cache/deadline không vượt source expiry; bounded cache/queue/concurrency, timeout gồm chờ slot, subscriber cancel độc lập. Không transaction qua network await. Gate revision/expiry/delete trả 409/410/404; stale cache bị chặn, retry không leak slot. |
| F05 | Summary run A lệch items run B hoặc effective review đổi. | Demo dùng revision_scope=current cho cả hai. Token cùng SQLite BEGIN snapshot với response, gồm revisions/reviews/predictions/runs/run_items/label_source. Items gửi token + expected run; không dùng run_id làm đổi sang historical. Scope đổi→409 SCOPE_CHANGED, reset selection/page, refresh summary. staleTime:0 buộc kiểm lại page cache. Test7 dòng thành5+2 đúng item ids; review cùng run, edit, runA/B, thêm dòng, effective/ai/dataset/profile. Historical API giữ cùng semantics cho aggregate/items. |
| F06 | UI rút gọn bỏ missing/partial/errors/Toxic. | Tái dùng TopicAttention; hiện eligible/filtered/missing/unprocessed/errors, empty/running/partial/failed/cancelled/interrupted, n<5 và Toxic riêng. Fixtures14/15 eligible; 1/3 eligible với2 missing sentiment,1error,2unprocessed; denominator0 là dấu gạch, không bịa0%. |
| F07 | Copy gọi top theo count là rate cao nhất. | Giữ count desc/eligible desc/topic id asc; copy “nhiều phản hồi tiêu cực nhất”. Fixture6/10=60% xếp trước2/2=100%; Toxic không cộng Negative. |
| F08 | Thiếu score thành0, thiếu signals bị coi clear. | Validator canonical length/finite/range/sum/argmax/label/schema/model và source identity. Task hỏng không bars/auto explanation; task hợp lệ giữ lại. Signals unavailable theo từng task. Invalid transition ẩn/abort explanation; repaired snapshot phục hồi qua cache. NaN/Infinity kiểm trực tiếp TypeScript, không claim JSON/network gửi NaN chuẩn. NEU đủ4/10, UIT đủ3/4. |
| F09 | Poll lỗi khóa màn/chờ vô hạn. | Tách initial/active/transient/terminal/not-found/expired.404/410 dừng interval/focus retry, có reset/phân tích lại;500/network có retry, giữ completed result hợp lệ. failed/cancelled/interrupted/completed_with_errors thiếu prediction không gọi explanation; retry hoàn tất snapshot mới và1upstream. Kiểm poll đầu/sau active/sau completed, cancel/retry và response muộn. |
| F10 | URL/token dài tràn, font nhỏ, hàng tương tác thiếu semantics. | Scoped wrapping/min-width cho user/provider/drill-down/sensitivity, không body overflow-x hidden. Body/prose16px, labels/cells>=14px kể cả mobile specificity. Buttons/keyboard/focus-visible/aria-live/reduced-motion. Copy “Phân bố điểm dự đoán”, giữ cảnh báo chưa hiệu chuẩn.5viewports và URL277ký tự+Unicode có assertions overflow/fonts và ảnh đã xem. Bảng sensitivity hẹp có vùng cuộn nội bộ. |
| F11 | No-hash vào workspace, hai luồng quick độc lập. | No-hash/# vào demo, #/demo demo, #/ workspace; giữ dataset/new/research/help/deep links. “Thử một câu” đi demo; QuickAnalysis chỉ compatibility export SentenceDemo, một implementation job/explanation. Explicit add chỉ lưu text, invalidation trúng demo queries; dataset phân tích riêng để tạo provenance mới. |
| F12 | Raw upstream body/exception có thể lộ; tải response không cap. | Stable codes/messages do app kiểm soát, không resp.text/raw URL/body/auth/exception. Reject URL userinfo/query/fragment. Stream cap64KiB, strict schema/length/empty/refusal/HTML, render text an toàn, không fallback mẫu. MockTransport marker riêng tư/secret không xuất hiện API/log; thiếu config không phá health/startup/classifier. |

Mapping **41 dòng F01–F12 + U01–U20 + G01–G09**, test nodes/assertions/evidence/limits: [closure-matrix.md](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/closure-matrix.md), [closure-matrix.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/closure-matrix.json). “Closed” nghĩa là kiểm bằng code/doubles, không phải nghiệm thu live.

Các gap bổ sung đã đóng: Help và tài liệu đủ4biến environment/PowerShell placeholder/URL có hoặc không /v1/restart+reload; nói đúng không có .env loader.503 giữ prediction, retry explanation không tạo classifier job. U04 bỏ nuốt AssertionError, dùng gate. StrictMode/refetch/same-text-new-job đo browser attempts tách upstream. UIT available dùng double riêng, unavailable có case riêng. Screenshot isolation sửa trước các lượt E2E mới, ảnh ở evidence mới. U12 kiểm packaging input không tin cậy và truncated local trước/sau provider text; không tuyên bố chống prompt injection ngữ nghĩa.

## File thay đổi so với working-tree baseline

Đường dẫn tương đối với F:\DPL_NEU-ESC; manifest có hash before/after từng file. api.ts, requirements, mockup/fonts và các file C1 không liệt kê giữ byte baseline.

Patch byte thực có thêm churn LF/CRLF trong một số file được sửa. [fix.normalized-review.diff](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/fix.normalized-review.diff) chỉ chuẩn hóa xuống dòng để đọc thay đổi thuận tiện; fix.delta.diff và snapshot vẫn là nguồn byte thật để đối chiếu/hoàn nguyên.

| Nhóm | 19 file baseline được sửa |
|---|---|
| UI/contracts | apps/web/src/App.tsx; QuickAnalysis.tsx; SentenceDemo.tsx; SentenceDemo.css; types.ts |
| Backend | services/api/main.py; services/explanation.py; services/storage/db.py; services/worker.py |
| API/unit tests | tests/api/test_explanation_endpoint.py; tests/api/test_sensitivity.py; tests/test_explanation.py |
| E2E/harness | tests/e2e/conftest.py; serve_test_app.py; test_regressions.py; test_sentence_demo.py; test_workspace.py |
| Product/design | PRODUCT.md; DESIGN.md |

9 file mới:

- apps/web/src/demoPrediction.ts
- services/demo_scope.py
- tests/api/test_demo_scope.py
- tests/api/test_explanation_closure.py
- tests/api/test_quick_sensitivity.py
- tests/test_explanation_transport_closure.py
- tests/e2e/test_demo_scope_closure.py
- docs/SENTENCE_DEMO_EXPLANATION_OPERATIONS.md
- docs/SENTENCE_DEMO_UI_9ROUTER_CODEX_FIX_REPORT_2026-11-11.md

Workspace/regression tests cần danh sách dataset đổi entry no-hash sang /#/. Quick modal selectors chuyển sang demo input/profile/add select; vẫn kiểm unavailable UIT, explicit text add, schema/provenance và dataset không có prediction sao chép, cùng review/import/export/restart. Không bỏ/skip/xfail case baseline. C1 suites13+20 giữ nội dung và assertions.

## Nghiệm thu, toolchain và dist

CWD mọi lệnh: F:\DPL_NEU-ESC. Python executable F:\DPL_NEU-ESC\.venv\Scripts\python.exe, phiên bản 3.10.11; Node 22.17.0/npm 10.9.2; pytest 9.2.0; Playwright 1.63.0; httpx 0.28.1; FastAPI 0.162.0. Không cài/đổi dependencies. Runner xóa FEEDBACK_EXPLANATION_* khỏi environment test, dùng TestOnlyRegistry, DemoTestOnlyRegistry, VaryingTestOnlyRegistry, ControlledE2ERegistry, GatedControlledRegistry, E2EMockExplanationProvider, GateProvider và httpx.MockTransport.

[test-results.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/test-results.json) ghi exact argv/cwd/executable/exit/duration/counts/log/JUnit của từng root run. Duration process gồm startup; pytest stdout/JUnit có thể khác.

| Lượt cuối liên quan | Pass/fail/skip | Exit | Process / pytest stdout |
|---|---:|---:|---:|
| build-final-release-check | build thành công,88modules |0|16.063s |
| unit-api-acceptance |216/0/0|0|76.531s /72.89s |
| e2e-final-complete (dừng -x) |61/1/0|1|399.875s /397.85s |
| e2e-acceptance-remaining |43/0/0|0|417.219s /415.34s |
| E2E union so collect-only |**104distinct pass**,0unresolved,0skip|—|Hai lượt, không phải một full-suite command xanh |
| git-diff-check-final |không whitespace error; chỉ LF/CRLF warnings|0|0.156s |

Lỗi duy nhất ở E2E đầu là **test U13 đòi raw message API**, trong khi SensitivityPanel ánh xạ REVISION_CONFLICT sang thông báo local kiểm soát. Chỉ sửa assertion theo contract thực và thêm kiểm alert+nút reload; giữ kiểm source/prediction/overflow. Không sửa production source/dist giữa hai lượt. Lượt còn lại chạy lại U13 đó, U18x4, U12 mới và toàn bộ phần chưa chạy. Không chạy lại61ca đã xanh khi source không đổi.

[e2e-coverage-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/e2e-coverage-verification.json) so node ids của hai JUnit với pytest tests/e2e --collect-only:104/104, overlap0, missing0, unexpected0, unresolved0.

| Suite E2E | Baseline | Kết quả cuối phân biệt |
|---|---:|---:|
| test_sentence_demo.py |7|50|
| test_demo_scope_closure.py |mới|8|
| test_regressions.py |9|9|
| test_three_layer_demo.py |13|13|
| test_three_layer_review_fixes.py |20|20|
| test_workspace.py |4|4|
| Tổng |53|104|

Unit/API cuối: attention20; demo scope6; explanation closure30; explanation endpoint7; quick sensitivity22; review signals API6; durable sensitivity12; workspace API31; review signals unit6; sensitivity selection22; runtime isolation1; explanation unit22; transport closure31=216.

Lệnh thực của ba lượt pytest nghiệm thu:

~~~powershell
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/api tests/test_review_signals.py tests/test_sensitivity_selection.py tests/test_runtime_isolation.py tests/test_explanation.py tests/test_explanation_transport_closure.py -q --tb=short -p no:cacheprovider --junitxml=C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/unit-api-acceptance.xml
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e -x -q --tb=short -p no:cacheprovider --junitxml=C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/e2e-final-complete.xml
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_sentence_demo.py::test_u13_sensitivity_error_preserves_source_and_is_actionable tests/e2e/test_sentence_demo.py::test_u18_terminal_quick_job_retry_completes_one_snapshot_and_explanation tests/e2e/test_sentence_demo.py::test_u12_untrusted_input_packaging_and_local_truncation_survive_provider_text tests/e2e/test_three_layer_demo.py tests/e2e/test_three_layer_review_fixes.py tests/e2e/test_workspace.py -x -q --tb=short -p no:cacheprovider --junitxml=C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/e2e-acceptance-remaining.xml
~~~

Build cuối: C:\Program Files\nodejs\npm.cmd run build --prefix apps/web, trước E2E. [dist-manifest.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/dist-manifest.json) so HTTP isolated TestServer với local dist: **8/8file match**, status200, gồm index, JS/CSS, fonts/license. dist-acceptance-http.log ghi lần đối chiếu cuối; hash source được kiểm lại khi finalize.

- assets/index-DYo4LLru.js SHA-256: 1fd19f1b67c4dbe1578ca38b54c9441fe6c6b4caf0f3cfcd56493f5c1f8cf844
- assets/index-DisE7Jup.css SHA-256: d2bc4d4e8db9a3f13dc83382023c830deb4a0c4697d22024e20a953f854cea4e

## Negative controls và lịch sử lỗi

Không sửa summary JSON để biến fail thành pass. Raw logs/JUnit đỏ/debug/focused/interrupted được giữ:

- Explanation trước fix: explanation/red.xml **9fail/2pass**. Assertions bắt thiếu mapping và source stale/expired. Shell harness sớm không lưu exit riêng; runs.json ghi null đúng thực tế. Focused acceptance cuối90pass; sau đó root216pass.
- Sensitivity: test boundary khôi phục422cũ làm quick-source regression fail (sensitivity/negative-control.log), không để mutant trong source. Focused cuối56pass. Một lượt fail do ISO datetime làm tròn0.4microsecond khi soTTL; test so cùng độ chính xác biểu diễn, không nới lifetime contract.
- Frontend: direct TypeScript NaN/Infinity normal exit0; accept-all mutant tại boundary exit1 (frontend/validator-negative-control.json). Không claim network JSON gửi NaN, không để mutant trong working tree.
- Scope API đầu5pass/1fail vì test dùng POST thay PUT review; sửa endpoint test rồi6pass. Browser scope đầu sai selector “Sau”; sau đó phát hiện **page cache stale thực**, sửa staleTime:0, focused/final scope8/8pass.
- Frontend initial28pass/3fail giữ nguyên; sửa fixtures/selectors/focus và gap refetch thực. Debug visibility event trên document không bubble, React Query nghe window; test cuối dispatch đúng window. Không dùng sleep để che staleTime.
- frontend/focused-final-interrupted.json và e2e-acceptance-interrupted.json ghi lượt ngắt/log buffered/JUnit chưa xong, không claim số pass. Root ngắt để sửa CSS specificity/font và gate concerns; không dùng làm nghiệm thu cuối.
- e2e-final-complete.xml giữ1failU13; e2e-acceptance-remaining.xml chứng minh assertion sửa pass trên cùng production/dist cuối.

## Observations, visual QA và người kiểm

[observations.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/observations.json) tập hợp raw paths, identity, gate order, counts và properties từ JUnit nghiệm thu. Frontend JSONL chứa nhiều lượt; index chọn occurrence cuối theo scenario/late_failure và ghi số dòng, không giả tất cả thuộc cùng run.

U04 cuối, monotonic seconds: submit 85022.625; completed GET 85023.906; provider start 85023.937; layer1 visible 85024.250; provider end 85025.203; explanation visible 85025.718. Một upstream. Layer1 hiện trước khi provider gate xong; submit→completed 1281ms và submit→layer1 1625ms là **software orchestration timings**, không phải tốc độ model. Job b43b1d8b-afde-45e6-8833-55983f124231, run c7c2670c-e57a-4f06-9f7d-14296876fcb3, prediction c96342b3-6e53-48d7-a7c7-ca1448b67558; item/revision trong raw/index.

U05/U06:3classifier jobs/3browser explanation attempts/3upstream cho ba snapshot mới, kể cả submit lại cùng text và StrictMode/refetch. A/B gate trả đủ identity; late success/failure không ghi đèB. U18retry4terminal state giữ cùng job/run, prediction mới,1classifier POST ban đầu/1upstream sau retry. failed/interrupted là isolated SQLite fixtures; completed_with_errors phát sinh thật từ double lỗi, cancelled qua cancel thật.

[visual-qa.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/visual-qa.json) ghi **19ảnh root đã mở xem**, hash/dimensions/state; [screenshots](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/screenshots) có toàn bộ ảnh. Đã xem1440/1280/768/390/320px: NEU4/10, UIT3/4, loading với prediction,503/retry, unavailable model, sensitivity success/source conflict, lớp3empty/unprocessed/partial/Toxic/ranking/scope reset, U12truncated. URL dài wrap; không thấy chồng/cắt. DOM assertions kiểm scrollWidth và computed font thật trên served build. Bảng sensitivity hẹp cuộn trong vùng riêng, trang không tràn ngang.

Phân công thực tế: root baseline/contracts/routing/API scope/integration/docs/acceptance/visual; agent frontend demo/validator/CSS/tests; agent sensitivity lifecycle/storage/worker/tests; agent explanation service/transport/tests. Owner tự review phần của mình. Có **cross-review chỉ đọc code**: sensitivity kiểm scope/explanation, explanation kiểm frontend; artifacts sensitivity/qa-cross-review.md và explanation/qa-cross-frontend.md. Không có QA toàn app hoặc browser run độc lập.

Cross-review findings đã chốt: malformed warnings/token count không còn KeyError; deadline cappedTTL; font mobile>=14px; U04 timing/identity đúng; U18retry4states; gate A/B đủ envelope; bỏ duplicate toast. Các review cũ có “pending” phản ánh thời điểm đọc; kết quả root cuối và [qa-review.md](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/qa-review.md) là disposition sau tích hợp.

## Giới hạn, correction lịch sử và hoàn nguyên

- Không còn finding chức năng F01–F12/gap bổ sung đã biết chưa xử lý trong phạm vi doubles. **Chưa nghiệm thu live/production**: không inference/warmup/model/9router/API ngoài thật; không kết luận chất lượng classifier/explanation hoặc chống injection ngữ nghĩa.
- Quick result cũ thiếu marker cần phân tích lại. Cache/coalescing process-local, không dedupe phân tán. Scope token bảo thủ: thay dữ liệu liên quan trong dataset có thể buộc refresh.
- failed/interrupted là fixture tổng hợp trong DB test riêng; labels/text doubles có thể tùy ý về ngữ nghĩa. Ảnh/timings không chứng minh chất lượng model.
- Checkpoint/tokenizer/preprocessing/canonical labels/review policy/ranking thresholds không đổi. Không migration.
- Report implementation cũ giữ nguyên lịch sử. Report này sửa claim cũ: baseline three_layer_demo=13, three_layer_review_fixes=20; quick sensitivity trước fix thật sự422; prompt trước fix thiếu nghĩa nhãn; no-hash trước fix vào workspace; tổng test xanh cũ không chứng minh closure. Diễn giải ngoài không chạy local/offline; privacy copy đã sửa.
- Hoàn nguyên chọn lọc: theo manifest-after.json, kiểm current hash còn bằng after hash rồi phục hồi byte snapshot cho19file sửa. Chỉ xóa9file mới nếu hash còn khớp và xác định muốn bỏ chúng. Nếu có edit sau bàn giao, merge chọn lọc/3-way. Có thể preview git apply --reverse --check với fix.delta.diff trước khi cân nhắc apply. Không reset hard/checkout/revert toàn file vềHEAD hay xóa implementation baseline.
- [manifest-after.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/manifest-after.json) hash report sau khi hoàn tất và ghi delta before/after, không self-hash vòng lặp. [preservation-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-sentence-demo-fix-7d1f0e4aaec5/preservation-verification.json) ghi kiểm cuối, không thay evidence lịch sử.
- Finalizer đã chạy exit 0: all_pass=true, 28 file đúng allowlist, 223 file baseline ngoài scope giữ nguyên, 60 artifact lịch sử giữ nguyên, không binary/font change, source/dist khớp. Kiểm process cuối không thấy Python/Node test server hoặc helper còn chạy với command line của phiên này; không kill process người dùng.
