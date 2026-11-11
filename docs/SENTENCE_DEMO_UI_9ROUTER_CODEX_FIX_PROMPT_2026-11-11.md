# Prompt thực thi cho Codex: sửa UI demo và diễn giải 9router

Ngày soạn: 2026-11-11. Workspace: F:\DPL_NEU-ESC.

Bạn đang nhận **nhiệm vụ thực thi fix**, không chỉ review hoặc viết kế hoạch. Đọc tài liệu, xác nhận baseline, sửa các lỗi đã được tái hiện, bổ sung kiểm thử, chạy nghiệm thu và bàn giao evidence. Tiến hành các công việc đã được giao mà không cần hỏi lại xác nhận cho lựa chọn triển khai thông thường.

## 1. Mục tiêu và nguồn sự thật

Sửa toàn bộ F01-F12 trong review Codex, khép các thiếu sót bổ sung liên quan, đáp ứng kế hoạch UI đã duyệt. Giữ style/layout teal hiện tại; đây không phải yêu cầu thiết kế một UI mới.

Đọc trước khi sửa:

1. Plan gốc: F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_GEMINI_PLAN_2026-11-11.md
2. Review Codex: C:\Users\Admin\AppData\Local\Temp\codex-sentence-review-f01d532ec67042fb896b78056ab9ac72\CODEX_REVIEW.md
3. Evidence tái hiện của reviewer trong cùng thư mục:
   - backend-probes.json, frontend-probes.json, layer3-probes.json, edge-probes.json.
   - Các script *_probes.py, JSON/log/PNG tương ứng và dist-comparison.json.
4. Report implementation cũ: F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_IMPLEMENTATION_REPORT_2026-11-11.md
5. Evidence implementation cũ: C:\Users\Admin\AppData\Local\Temp\neu-esc-sentence-ui-20261111-evidence
6. Mockup đã duyệt: F:\DPL_NEU-ESC\design-previews\2026-11-11\sentence-demo-share.html và sentence-demo-v2.html/.css.
7. AGENTS.md áp dụng nếu có, PRODUCT.md, DESIGN.md và code/test liên quan.

Review Codex và plan là tiêu chí nghiệm thu; report implementation cũ có thông tin sai và **không phải bằng chứng rằng các tính năng đã hoàn tất**. Số dòng trong review là điểm bắt đầu tìm code, không phải vị trí cố định sau khi sửa.

Nếu Temp evidence đã bị dọn, đừng bịa đã đọc hoặc tái hiện nó. Prompt này tóm tắt đầy đủ findings; tiếp tục tái hiện từ code và ghi rõ tài liệu nào không còn khả dụng. Nếu không tìm được plan/mockup hoặc quyết định sản phẩm mâu thuẫn thật sự, hỏi ngắn gọn và vẫn tiếp tục phần độc lập.

### Baseline đang được giao

- Branch: webapp.
- HEAD tại thời điểm soạn: 36e4f8e1b905912f98b270ec1e675b3624a0cf3f.
- Implementation hiện chưa commit: có tracked changes và nhiều file untracked.
- Baseline của phiên fix là **toàn bộ HEAD + staged + unstaged + untracked ngay trước khi bạn sửa**, không phải riêng commit HEAD.
- Working tree bẩn là trạng thái chủ ý. Các file mới như SentenceDemo.tsx/.css, explanation.py, tests, fonts, mockup, plan/report và prompt này đều phải được ghi nhận trước khi sửa.
- Reviewer đã xác nhận 127 unit/API và 53 E2E pass, nhưng vẫn tái hiện được lỗi thật. Không dùng tổng số test xanh để tự kết luận closure.
- Số E2E baseline thực: test_regressions.py=9, test_sentence_demo.py=7, test_three_layer_demo.py=13, test_three_layer_review_fixes.py=20, test_workspace.py=4. Hai suite three_layer bị đảo số trong report cũ.

## 2. Quyền thực thi và giới hạn

Được sửa frontend, API/service/storage, tests và docs cần thiết để hoàn tất phạm vi này. Được refactor có giới hạn để dùng chung luồng phân tích và giữ semantics.

- Không commit, amend, push, deploy hoặc đổi branch nếu chưa được yêu cầu.
- Không gọi model thật, không gọi 9router/API ngoài thật, không warmup inference. Chỉ dùng model/provider doubles, httpx.MockTransport và runtime test riêng.
- Không tìm key trong cấu hình ứng dụng khác; không xuất key/env nhạy cảm vào log/source/screenshot.
- Không đổi checkpoint/tokenizer/preprocessing/hệ nhãn/ngưỡng review policy/ranking để làm tests pass.
- Không sửa/xóa runtime dữ liệu người dùng hoặc dừng server đang được sử dụng, kể cả localhost:8765. Test dùng port riêng, chỉ dọn process do phiên này tạo.
- Không reset/checkout/revert toàn bộ file về HEAD. Bảo toàn sửa đổi có trước, mockup, reports và evidence lịch sử.
- Không mở audit toàn codebase hoặc thêm feature ngoài demo/closure.
- Không xóa, skip, xfail hay giảm assertion để có số pass đẹp. Có thể đổi entry route/selector theo UX mới nhưng phải giữ hành vi và mức kiểm chứng.
- Không gỡ tính năng độ nhạy, thanh %, diễn giải tự động hay lớp 3 để “fix” bằng cách làm chúng biến mất.
- Không tuyên bố diễn giải từ dịch vụ ngoài chạy local/offline.
- Nếu thấy thay đổi bất ngờ ngoài nhóm của bạn trong lúc làm, dừng phần xung đột và hỏi cách phối hợp; không ghi đè.

Có thể dùng subagent nếu môi trường hỗ trợ và giúp chất lượng. Không bắt buộc số agent; không giả báo có QA độc lập. Đề xuất:

| Vai trò | Ownership |
|---|---|
| Agent chính | Baseline, hợp đồng chung, App.tsx/api.ts/types.ts, tích hợp, docs/evidence |
| Backend | explanation.py và phần storage/API đã được phân công, tests backend |
| Frontend | SentenceDemo/component/hook/CSS; thay đổi shared files phải phối hợp agent chính |
| QA | Acceptance tests/negative controls và review sau tích hợp |

Trước giao việc chốt contract/ownership, thông báo đang cùng worktree, không revert edits của nhau. Một file chung chỉ có một owner tại một thời điểm. Agent chính chịu trách nhiệm nghiệm thu cuối trên toàn bộ thay đổi đã tích hợp; tests của từng agent riêng không thay thế nghiệm thu chung.

## 3. Yêu cầu sản phẩm phải giữ

- No-hash vào demo; #/demo là route demo; #/ vẫn mở danh sách dataset cũ.
- Demo không có sidebar; layout dọc: input toàn hàng, prediction, diễn giải/độ nhạy, thống kê dataset.
- Font Be Vietnam Pro local có license, body 16-18px, chú thích/nhãn tối thiểu 14px; không làm lại theme.
- Input tối đa 5.000 ký tự, câu mẫu chỉ điền text; chỉ submit mới tạo classifier job.
- Hiện đầy đủ thanh score thật: NEU 4 sentiment/10 topic, UIT 3 sentiment/4 topic. Không giấu nhãn dưới “xem thêm”.
- Lớp 1 và local signals xuất hiện ngay khi prediction hợp lệ hoàn tất; tự gọi diễn giải đúng một lần cho snapshot mới. Không đợi provider mới hiện prediction.
- Card nhãn “Diễn giải kết quả”, loading “Đang diễn giải…”, không progress % giả, không vendor branding nổi bật, không thêm expandable technical panel.
- Giữ thông báo ngắn “Phân loại chạy trên máy; câu và kết quả được gửi tới dịch vụ diễn giải.”
- Lỗi/missing config không làm mất prediction; retry explanation không tạo classifier job.
- Local signals/cảnh báo truncated lấy từ backend thật, tách khỏi nội dung provider; không gọi đây là suy luận nội bộ của classifier.
- Sensitivity chỉ chạy khi người dùng yêu cầu, giữ provenance/Unicode/stale/cancel/retry/TTL.
- Lớp 3 mặc định chưa chọn dataset; dữ liệu thật cùng profile, nguồn nhãn rõ, mẫu số đúng, Toxic riêng, drill-down có phân trang.
- Giữ quản lý dataset, review/conflict/provenance, import/export, research và help.

## 4. Công việc cụ thể và tiêu chí đóng từng finding

### F01 — Quick-source sensitivity luôn 422

Hiện SentenceDemo truyền quick Item vào SensitivityPanel, còn services/storage/db.py:create_sensitivity_experiment từ chối temporary dataset.

Thực hiện:

- Đọc toàn bộ lifecycle tạo experiment, source identity, worker, retry, đọc kết quả và cleanup/foreign keys trước khi chọn cách mở rộng.
- Hỗ trợ **quick source hợp lệ** theo contract hiện có, không chỉ bỏ điều kiện temporary một cách rộng rãi.
- Phân biệt quick item với item nội bộ của sensitivity; không vô tình cho phép experiment lồng nhau.
- Validate source completed, prediction/run/schema/model identity, revision/current text hash, selection Unicode/UTF-16 và source TTL.
- Không chuyển quick text sang dataset bền ngầm; không mutate input/review hoặc copy prediction làm kết quả mới.
- Chốt lifetime khi source hết hạn giữa experiment hoặc retry: kết quả/response không được giả là source còn hợp lệ; không trả 500 do cascade cleanup; không để experiment/job chạy vô hạn hoặc làm hỏng worker.
- Bảo toàn hành vi source từ dataset bền và regression C1. Chỉ thêm migration nếu thực sự cần, với kiểm thử isolated.

Đóng khi:

- UI demo chọn cụm từ hợp lệ, tạo experiment, đọc so sánh thật từ double thành công.
- Test chứng minh đúng item/run/revision/source_prediction_id/model identity.
- Test stale, source hết hạn trước/sau request, cancel/retry, Unicode và không mutate source/review.
- Có test khẳng định vẫn từ chối loại temporary source không được hỗ trợ.

### F02 — Prompt thiếu bảng ý nghĩa nhãn

Hiện payload chỉ có profile id, label_id/scores; provider không biết mapping NEU/UIT.

Thực hiện:

- Load canonical profile/schema từ server, cung cấp id/key/name cho mỗi nhãn, tên top1 và toàn bộ scores gắn đúng nhãn.
- Kiểm tính tương thích snapshot/schema/vector trước gửi; không tin nhãn/scores client tự cung cấp.
- Giữ review signals, warnings/truncated cần thiết, bỏ metadata dư thừa.
- Không suy đoán mapping theo kinh nghiệm provider hoặc hardcode bảng thứ hai dễ lệch canonical profile.
- Nếu đổi nội dung prompt/contract ngữ nghĩa, bump prompt version phù hợp và đưa vào cache identity.

Đóng khi: tests inspect payload NEU lẫn UIT và đối chiếu canonical labels, thứ tự/điểm/top1 đúng; ví dụ NEU sentiment 3 là Toxic, UIT sentiment 0 là negative. Provider double phải kiểm payload nhận được, không chỉ trả chuỗi cố định.

### F03 — Submit race và cleanup context

Repro: giữ POST quick-analysis của A, sửa input thành B hoặc Xóa, thả response A; UI hiện kết quả A.

Thực hiện:

- Dùng cơ chế generation/identity nhất quán cho submit, poll, explanation và các callback async liên quan.
- Mọi sửa input/chọn câu mẫu/Xóa/đổi profile/job mới/rời route phải invalidate context phù hợp.
- Kiểm generation **sau await** ở cả success/error/finally; response cũ không được set job/result/error/busy của context mới.
- Chốt thao tác nào khóa lúc gửi/chạy. Nếu khóa input ngắn lúc submit, vẫn phải xử lý route unmount và response muộn; không chỉ vô hiệu hóa controls để né toàn bộ race.
- Quản lý request abort/subscription và timer cleanup khi unmount; không làm hỏng StrictMode.
- Nếu request đã tạo job rồi context bị bỏ, xử lý job mồ côi/best-effort cancel theo semantics hiện có; không tuyên bố client abort đồng nghĩa provider đã hủy.
- Không thay UI B bằng response A dù request A không hủy được ở transport.

Đóng khi: test bằng gate cho submit A/edit hoặc clear/unmount, explanation A/B, late failure và duplicate/retry; assert identity cuối và số job/provider calls, không dựa vào fixed sleep.

### F04 — Source validator và lifetime cache

Repro đã có: revision stale trước gọi; revision đổi trong provider; source hết TTL trong provider đều nhận 200 completed.

Thực hiện:

- Dùng validator chung kiểm đúng quick/completed, source prediction, current revision/hash, run/profile/schema/model và expiry.
- Validate trước trả cache, trước bắt đầu provider sau khi chờ slot nếu cần, và **sau await trước khi phát kết quả thành công/cache**.
- Cache entry không sống quá source expiry; source invalid không nhận result cũ qua cache.
- Cache/in-flight key đủ identity của snapshot, prompt/policy và cấu hình provider có ảnh hưởng; không lưu raw secret trong key/log.
- Giữ coalescing, bounded concurrency/queue/cache, timeout tổng kể cả chờ slot; không cache lỗi vĩnh viễn.
- Cleanup đúng slot/task/cache khi timeout/cancel/exception; cancel một subscriber không phá subscriber khác. Không giữ transaction khi chờ mạng.
- 404/410 phải phản ánh điều storage thực sự biết; không bịa phân biệt nếu source đã bị xóa.

Đóng khi: API tests có provider gate thay revision/expiry/delete trong lúc await; cached expired/stale request bị chặn; provider không gọi cho source invalid; cache TTL bị chặn bởi source expiry; coalescing/retry/timeout không deadlock hoặc leak slot.

### F05 — Summary và drill-down lệch scope

Repro: summary run A ghi 6/6 Negative, dataset edit + run B, click “Xem 6...” nhận 0 dòng từ run B.

Thực hiện:

- Chọn chiến lược nhất quán: pin snapshot/run cho **cả summary và items**, hoặc refresh/reset toàn bộ view khi source scope đổi.
- Không chỉ chèn resolved_run_id vào items trong khi summary vẫn ở revision_scope=current khác semantics.
- Đọc semantics của reviews/effective: cùng run chưa chắc đảm bảo cùng nhãn effective khi review đổi. Phải refresh/kiểm tra snapshot thích hợp trước trình bày aggregate và danh sách là một bộ.
- Query keys/request params bao gồm dataset, run/scope, label_source, topic, negative label và page liên quan.
- Thể hiện dataset/run/phạm vi/nguồn nhãn trên UI. Không âm thầm chuyển latest.
- Đổi dataset/source/run/profile reset selection/page không tương thích; pending/error không giữ danh sách cũ như dữ liệu mới.
- Quick-add/invalidation phải trúng query keys màn demo; không để summary cũ và dataset count mới lệch nhau.

Đóng khi: tái hiện A/B không còn count/list sai phạm vi; tests assert request parameters, response identity, count và các item id thực. Bao phủ pagination hơn 5 dòng, đổi effective/ai, dataset/profile và review thay đổi.

### F06 — Missing/partial/Toxic bị bỏ

Thực hiện:

- Tái dùng TopicAttention hoặc dùng adapter/shared logic có đầy đủ semantics của nó, không nhân bản một bản rút gọn mất cảnh báo.
- Hiển thị insufficient/empty, running, partial, failed/cancelled/interrupted và unprocessed/errors đúng dữ liệu.
- Phân biệt “chưa có đủ dữ liệu kết luận” với “không có nhãn Negative trong phạm vi”.
- Hiển thị eligible/filtered, missing topic/sentiment, mẫu nhỏ n<5 và Toxic riêng.
- Không cộng Toxic vào Negative, không dùng reference labels như effective, không biến denominator=0 thành tỷ lệ 0% tùy tiện.

Đóng khi: fixtures empty/unprocessed/missing labels/partial/errors/Toxic-only/mixed có assertions số cụ thể và trạng thái đúng; giữ C1 layer-3 warnings.

### F07 — Nhầm count ranking thành rate ranking

Giữ ranking negative_count_desc,eligible_count_desc,topic_id_asc. Copy phải diễn đạt “nhiều phản hồi tiêu cực nhất” khi chọn top theo count, không gọi tỷ lệ của nó là cao nhất.

Đóng khi: fixture A=6/10=60%, B=2/2=100% vẫn xếp A trước theo count nhưng không nói 60% cao nhất; tie-break và mẫu nhỏ còn đúng.

### F08 — unavailable/malformed score bị che

Thực hiện:

- Tách rõ clear/flagged/unavailable, per-task; không có signals cũng không tự suy là clear.
- Validate vector theo canonical profile: đủ số nhãn, hữu hạn, miền hợp lệ, label_id hợp lệ và identity/schema phù hợp.
- Bỏ fallback ??0 cho điểm bị thiếu; không clamp để che invalid payload.
- Dữ liệu không hợp lệ hiển thị lỗi/không đủ dữ liệu rõ ràng; phần hợp lệ có thể còn xem được nhưng không gắn thông điệp tin cậy sai.
- Không gọi provider dựa trên prediction invalid. Khi dữ liệu sửa và trở lại hợp lệ, state có thể phục hồi đúng.
- Giữ low_top1/small_margin, unavailable và truncated; không hardcode threshold mockup.

Đóng khi: test absent/short/oversize/nonfinite/out-of-range/invalid label/schema, state unavailable từng task và missing signals. JSON không biểu diễn NaN chuẩn thì kiểm validator trực tiếp; không claim đã gửi NaN chuẩn qua network. Test valid NEU và UIT vẫn đủ thanh %, đúng giá trị một chữ số thập phân.

### F09 — Poll errors khóa màn

Thực hiện:

- Phân biệt initial pending, active job, transient poll failure, terminal job error, not found/expired.
- 404/410 dừng poll context mất, thông báo rõ và cho Xóa/phân tích lại/thoát.
- Network/500 có retry/recovery hợp lý; không dựng “đang chạy” vô hạn do !data.
- Lỗi sau khi đã có completed result không được tái khóa màn hoặc xóa nhầm kết quả hợp lệ.
- Cancel/retry còn hoạt động sau lỗi; reset/unmount và response retry muộn tuân F03.
- Failed/cancelled/interrupted không gọi explanation như successful prediction.

Đóng khi: tests lỗi lần poll đầu, lỗi sau active, lỗi sau terminal, phục hồi, cancel/retry/late response và 404; controls không kẹt, request count không poll vô hạn ở 404.

### F10 — Overflow và typography

Thực hiện:

- Wrap nội dung người dùng/provider/drill-down ở scope thích hợp: URL, token liền, chuỗi Unicode dài.
- Không dùng body overflow-x:hidden để che lỗi hoặc cắt mất text/thanh %.
- Test min-width/flex/grid khi nhãn dài và mở SensitivityPanel, populated/error/loading states.
- Giữ readable font: chú thích/nhãn tối thiểu 14px, body 16-18px, focus visible, keyboard, aria-live và reduced-motion.
- Các hàng drill-down tương tác phải dùng button/link phù hợp hoặc có keyboard semantics tương đương; không chỉ div onClick.
- Sửa copy “Phân bố minh họa” ở kết quả thật để người đọc không nhầm đây là dữ liệu mock; vẫn giữ cảnh báo score chưa hiệu chuẩn.

Đóng khi: kiểm thật ở 1440/1280/768/390/320px, câu thường và URL 224+ ký tự; scrollWidth không vượt viewport, không chồng/cắt nội dung; screenshots được tự xem, không chỉ tạo file.

### F11 — Routing và một luồng phân tích dùng chung

Thực hiện:

- No-hash mặc định vào #/demo theo semantics routing đã chốt; #/ vẫn vào workspace.
- Giữ dataset/new/research/help/deep links.
- Chọn chuyển “Thử một câu” sang demo, hoặc giữ modal với **cùng component/hook quản lý job**; không duy trì hai logic submit/poll/cancel/retry/explanation độc lập.
- Khuyến nghị một entry demo rõ ràng, giữ các khả năng quick-analysis cần thiết như lưu text explicit vào dataset.
- Cập nhật test entry/selector theo routing mới. Giữ assertion hành vi tương đương; không bảo vệ route cũ bằng cách bỏ yêu cầu route mới.

Đóng khi: test no-hash, #/demo, #/, workspace links/reload/back-forward và flow từ nút “Thử một câu”; không tạo duplicate job/explanation, C1 và import/export vẫn pass.

### F12 — Không trả raw upstream error

Thực hiện:

- Loại raw resp.text, request body, auth headers, exception chứa URL/query/secret khỏi client error envelope và logs.
- Giữ stable codes/messages/status 401/403 upstream -> lỗi diễn giải thích hợp, 429/502/504/unavailable theo contract.
- Không chỉ dựa regex che một API key; response lỗi phải dùng thông điệp kiểm soát.
- Giới hạn tổng response size khi đọc upstream, không chỉ len(reading/caution) sau khi đã tải body vô hạn.
- Validate schema output, field length, empty/refusal/HTML và render text an toàn; không fallback diễn giải mẫu.
- API key server-only, không VITE_*; missing config không phá startup/health/classifier.

Đóng khi: MockTransport trả lỗi chứa marker text riêng tư/auth/query/secret dạng khác, tất cả không xuất hiện trong API response/log; oversized/malformed response bị chặn; timeout/queue/retry/health vẫn đúng.

## 5. Thiếu sót bổ sung cần khép trong cùng phiên

- Trang #/help và tài liệu vận hành phải hướng dẫn FEEDBACK_EXPLANATION_BASE_URL, FEEDBACK_EXPLANATION_API_KEY, FEEDBACK_EXPLANATION_MODEL, FEEDBACK_EXPLANATION_TIMEOUT_SECONDS; URL có/không /v1 rõ ràng.
- Ví dụ PowerShell dùng placeholder, không key/model alias giả định; nói đúng app đọc environment, không nhận đã load .env nếu không có loader.
- Nhánh 503 có cách retry explanation và hướng dẫn restart/reload cấu hình nếu cần; không hứa set env sau startup là provider tự cập nhật.
- Remove hoặc thay test U04 nuốt AssertionError bằng gate xác định. Không catch assertion rồi pass.
- Test StrictMode/re-render/refetch coalescing và stale A/B thực sự. Phân biệt số request browser với số upstream provider; điều cần đảm bảo là upstream không bị nhân đôi.
- Cùng câu được submit thành job mới vẫn auto explanation mới; retry explanation không tạo classifier job.
- Tên/screenshots của tests mới không được hardcode vào thư mục evidence implementation cũ. **Sửa isolation này trước khi chạy E2E mới**, dùng tmp_path/screenshot fixture hoặc evidence dir được truyền rõ ràng.
- UIT dùng model double available để kiểm đủ 3/4 nhãn; có test riêng unavailable. Không cần checkpoint UIT thật.
- Không tuyên bố prompt injection an toàn về mặt ngữ nghĩa chỉ vì test stub pass; chỉ kiểm prompt packaging và local warning preservation.
- Giữ lịch sử report/QA cũ. Tạo report correction/closure mới; nếu thêm correction vào report cũ thì append có ngày/link, không xóa hay viết lại kết quả lịch sử.

## 6. Trình tự và checkpoints

### P0: Snapshot và xác nhận tái hiện

1. Đọc chỉ dẫn, kiểm branch/HEAD/status, toolchain và fixtures.
2. Tạo evidence dir mới, ví dụ %TEMP%\codex-sentence-demo-fix-<unique-id>.
3. Lưu staged/unstaged diffs, danh sách/hash và bản sao nội dung cần thiết của tracked/untracked baseline, gồm source implementation và tests mới. Không chỉ snapshot HEAD.
4. Ghi hashes mockup, C1 files, review/plan/report; không đưa runtime DB, model, credentials vào snapshot.
5. Reproduce findings bằng tests/probes isolated. Các probe của review là tham khảo; chuyển thành regression test có assertion hành vi, không copy nguyên script có lỗi gọi endpoint đã ghi trong review.
6. Chốt API/types/lifetime/scope strategy và ownership nếu dùng subagent.

### P1: Backend contracts

Sửa F01/F02/F04/F12, thêm tests focused. Không giữ transaction qua provider await. Xác nhận durable sensitivity và worker không regression trước tích hợp UI.

### P2: Frontend state/routing

Sửa F03/F08/F09/F11; dùng chung logic cần thiết; thêm tests race có gate, stale identities, retry/cancel và unavailable.

### P3: Layer 3 và responsive

Sửa F05-F07/F10; fixtures có counts biết trước, snapshots/runs/reviews khác nhau, labels thiếu/Toxic; kiểm keyboard, long-text và viewports.

### P4: Nghiệm thu và bàn giao

1. Tự review diff chỉ của phiên fix, đọc negative tests như reviewer.
2. Build cuối trước E2E, hash dist được phục vụ.
3. Chạy unit/API và toàn bộ E2E liên quan theo plan; sửa findings, chạy lại các phần bị ảnh hưởng. Nếu code sửa sau lượt nghiệm thu, không dùng kết quả cũ cho code mới.
4. Xem screenshots thực tế và kiểm trạng thái lỗi/loading/success.
5. Verify preservation và lập report/matrix F01-F12 + U01-U20.
6. Bàn giao prompt review ngắn đã điền thông tin thực ở cuối. Dừng trước commit/push/deploy/live API.

## 7. Testing và chứng cứ bắt buộc

Tối thiểu coverage theo F01-F12 và ma trận U01-U20 trong plan. Không cần đặt 20 tên test cho đủ số; một test có thể chứng minh nhiều yêu cầu, nhưng phải map assertion/evidence rõ ràng.

Lệnh dự kiến từ F:\DPL_NEU-ESC (xác nhận Python đúng môi trường, không cài/đổi toolchain tùy tiện):

~~~powershell
npm run build --prefix apps/web

python -B -X utf8 -m pytest tests/api tests/test_review_signals.py tests/test_sensitivity_selection.py tests/test_runtime_isolation.py tests/test_explanation.py -q --tb=short -p no:cacheprovider

python -B -X utf8 -m pytest tests/e2e -q --tb=short -p no:cacheprovider

git diff --check
~~~

Nếu có tests mới ở module khác, thêm chúng vào lệnh. Nếu môi trường chuẩn dùng .venv\Scripts\python.exe, dùng đúng executable đó và ghi lại. Không chạy full model benchmark hoặc inference thật.

- E2E phải build trước; skip vì thiếu dist không tính pass.
- Tests default API import vẫn dùng tests/conftest.py runtime isolation.
- Browser/HTTP fixtures không được trỏ tới runtime hoặc port người dùng.
- Negative assertions phải làm test fail nếu bug quay lại. Chạy red trước fix khi khả thi; tối thiểu dùng targeted control/mutation tại test boundary cho các gate/provenance quan trọng để chứng minh assertion không rỗng. Không mở mutation campaign toàn codebase hoặc để mutant trong working tree.
- Log lần thất bại và lần thành công tách biệt, giải thích lỗi harness nếu có. Không sửa summary JSON để biến fail thành pass.
- Record số pass/fail/skip theo kết quả thực, không hardcode 127/53 hoặc 180 cho phiên mới.
- Đo submit, completed nhận được, layer1 visible, explanation start/end và upstream counts bằng doubles; không gọi đây là tốc độ model thật.
- Không rerun suite vô cớ sau khi đã xanh và không còn thay đổi/concern mới.

## 8. Artifacts phải bàn giao

Report mới dự kiến:
F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_CODEX_FIX_REPORT_2026-11-11.md

Dùng ngày thực thi nếu đã sang ngày khác. Không ghi đè một report đã có từ phiên khác; đặt tên phân biệt nếu cần.

Evidence ngoài source, đường dẫn tuyệt đối trong report, tối thiểu:

| Artifact | Nội dung |
|---|---|
| baseline.json + snapshot | Branch/HEAD, staged/unstaged/untracked, SHA-256 và nội dung baseline có thể so sánh |
| fix.delta.diff | Chỉ delta phiên fix so với working-tree snapshot, gồm file untracked bị sửa và file mới; không gộp toàn implementation trước đó |
| manifest-after.json | Hash mọi file sửa/tạo, binary/fonts nếu có; ghi rõ phạm vi và exclusions |
| preservation-verification.json | So before/after; baseline ngoài scope và staged state được bảo toàn; mockup/evidence lịch sử giữ nguyên |
| test-results.json + raw logs/JUnit | Exact command/cwd/executable/exit code/duration/pass/fail/skip, log path, final acceptance run |
| observations.json | Gate order, request counts, job/run/item/revision/prediction identities, expiry/cancel/error observations thực |
| dist-manifest.json | Hash build cuối và dist thực được test server phục vụ, kết quả đối chiếu |
| screenshots/ | Desktop/mobile success đầy đủ labels, provider loading + prediction, error/missing config/model, sensitivity success/error, layer3 empty/partial/Toxic/drill-down, long text |
| qa-review.md | Findings cuối và trạng thái; nêu tự review hay agent độc lập, không bịa |
| closure-matrix | F01-F12 và các gap bổ sung: changed files, tests, evidence, pass/open; U01-U20 mapped |

Hash report sau khi report hoàn tất; không tạo self-hash vòng lặp cho manifest. Không đưa secret vào snapshots/logs. Không ghi đè artifact gốc trong hai thư mục Temp của implementation và reviewer.

Report ghi:

- Hành vi trước/sau và quyết định về quick-source TTL, cache identity, layer3 scope, routing/shared flow.
- Danh sách file thay đổi có chủ đích so với baseline phiên fix.
- Các test route/selector baseline đã đổi và assertion hành vi được giữ.
- Số test đúng từng suite, các lỗi phát hiện/sửa, findings còn mở.
- Ba trạng thái tách biệt: code + doubles; visual QA; model/9router thật **chưa chạy**.
- Deviations/limitations còn tồn tại, không tự gọi production-ready nếu còn finding.
- Cách hoàn nguyên chỉ delta fix bằng snapshot có chọn lọc, không reset hard hoặc xóa implementation baseline.

Nếu chưa đóng được finding, tiếp tục các phần độc lập; cuối cùng ghi rõ open và lý do. Không tự xóa yêu cầu hay báo hoàn tất toàn bộ chỉ vì các test hiện có pass.

## 9. Prompt bàn giao ngắn phải xuất ở cuối final

Ngoài tóm tắt kết quả, xuất một code block khoảng 15-25 dòng, **điền mọi placeholder bằng dữ kiện thật**, để người dùng mang về chat reviewer. Không chỉ dẫn lại mẫu này chưa điền.

~~~text
Review fix UI demo + diễn giải 9router tại F:\DPL_NEU-ESC.
Plan: F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_GEMINI_PLAN_2026-11-11.md
Fix prompt: F:\DPL_NEU-ESC\docs\SENTENCE_DEMO_UI_9ROUTER_CODEX_FIX_PROMPT_2026-11-11.md
Review gốc: C:\Users\Admin\AppData\Local\Temp\codex-sentence-review-f01d532ec67042fb896b78056ab9ac72\CODEX_REVIEW.md
Fix report: <đường dẫn report mới>
Evidence mới: <đường dẫn tuyệt đối>
Branch/HEAD đầu-cuối: <giá trị thực>
Baseline: HEAD + staged + unstaged + untracked; snapshot/manifest: <path>.
Scope: chỉ delta phiên fix và file mới trong manifest; delta: <path>.
F01-F03: <kết quả thực>.
F04-F07: <kết quả thực>.
F08-F12: <kết quả thực>.
Gaps bổ sung và U01-U20: <path matrix + trạng thái>.
Tests: <commands hoặc log path, pass/fail/skip thực, duration>.
Dist E2E khớp build cuối: <manifest và kết quả>.
Visual QA: <viewports/trạng thái đã xem, screenshots path>.
Preservation: <path và kết quả>; subagent/QA: <thực tế>.
Model/9router thật: chưa gọi; dùng <tên doubles/transport thực>.
Còn mở/khác plan: <liệt kê, hoặc không có nếu đã kiểm chứng>.
Ưu tiên review: quick sensitivity/TTL, prompt labels, submit/stale/dedupe, scope lớp 3, raw errors, C1 và evidence.
Chỉ review; không sửa, commit/push/deploy hoặc chạy model/API thật.
~~~

