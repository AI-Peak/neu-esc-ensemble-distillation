# Gemini handoff: sửa ba lỗi sau review Demo Webapp Ba lớp

Ngày: 2026-11-10, Asia/Saigon.

Đây là kế hoạch thực thi cho **chat Gemini mới**, dựa trên review độc lập đã đọc code, chạy tests và tái hiện lỗi bằng Playwright. Lượt viết tài liệu này chỉ tạo bàn giao; chưa sửa implementation.

## 1. Nhiệm vụ và phạm vi

Làm việc tại `F:\DPL_NEU-ESC`, Windows/PowerShell. Sửa dứt điểm ba finding:

| ID | Mức độ | Vấn đề | File chính |
|---|---|---|---|
| R1 | P1 | Nháp rà soát tự chuyển sang revision văn bản mới sau conflict/refetch, có thể lưu nhãn của văn bản cũ lên văn bản mới mà không đối chiếu | `apps/web/src/ItemDetail.tsx` |
| R2 | P2 | Lỗi polling xóa ID job sensitivity chưa kết thúc; đóng panel không gửi cancel | `apps/web/src/SensitivityPanel.tsx` |
| R3 | P2 | Retry trả thành công sau khi panel đóng/đổi ngữ cảnh bị bỏ qua mà không cancel job vừa xếp lại | `apps/web/src/SensitivityPanel.tsx` |

Mục tiêu là sửa implementation, bổ sung regression tests có khả năng bắt lỗi trên bản cũ, chạy kiểm chứng và bàn giao delta chưa commit. Không chỉ trình bày lại kế hoạch.

Tài liệu nền:

- `docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md`: kiến trúc, contracts và giới hạn của tính năng ba lớp.
- `PRODUCT.md`, `DESIGN.md`: ngữ cảnh sản phẩm và hệ giao diện hiện có.
- `docs/LOCAL_APP.md`, `docs/VALIDATION_REPORT.md`, `docs/THREE_LAYER_DEMO_RUNBOOK.md`.

**Ưu tiên khi có mâu thuẫn:** các hành vi R1-R3 và tiêu chí nghiệm thu trong tài liệu này thay thế assertion/hướng dẫn cũ cho chính ba lỗi đó. Giữ các contracts khác. Đặc biệt, yêu cầu “giữ nháp khi đổi revision” nghĩa là giữ nội dung nháp để đối chiếu, không phải tự cho phép lưu nháp lên revision mới.

## 2. Baseline đã quan sát

Branch `webapp`, HEAD:

```text
a0cebad8d625c68ca4df755de27a249e2b8ba134
```

Implementation ba lớp nằm trong **delta chưa commit**, gồm cả file tracked sửa đổi và file untracked. Chỉ checkout HEAD sẽ không có đủ implementation cần sửa. Không reset, clean, stash hoặc ghi đè delta hiện tại. Nếu dùng checkout/worktree riêng, phải mang đúng trạng thái working tree, kể cả các file untracked cần thiết.

SHA-256 của các file trọng tâm lúc chuẩn bị bàn giao:

```text
e4ec1d0b80f6551cb11b280c3b2f446e1a4282bbf4033c73b055cf4a4ea4f0f9  apps/web/src/ItemDetail.tsx
8c3e444a72f4279ba906661568e779e2fefa74c243e2815c28aaf2d9f73cecf7  apps/web/src/SensitivityPanel.tsx
c13aefa1729b284c0b7c4b736fa2dcba7db7425822eb9aa456cf02ca72ac129c  tests/e2e/test_three_layer_demo.py
2d85876dc32ff7eed8527f21e1665d181c384ab267b93e19b4ec0c32fee2b0fa  tests/e2e/conftest.py
d5c22aed13c04a0cad4248386a60016f4bab178b2c8e0c9a5ec006a30ac8d3e7  tests/conftest.py
```

Hash là mốc so sánh, không phải lý do khôi phục file. Nếu khác, đọc delta mới và thích nghi trước khi sửa. Line numbers trong tài liệu là vị trí ở baseline, hãy định vị lại bằng tên hàm.

Reviewer đã chạy trên bản này:

- Default suite: **272 passed, 3 deselected**, 302.53 giây.
- Real-model suite: **3 passed, 272 deselected**, 142.44 giây.
- TypeScript và Vite build thành công; build vào thư mục tạm có hash khớp `apps/web/dist` hiện có.
- `git diff --check` thành công.
- Ba repro ngoài suite đều xác nhận lỗi; các script repro được chạy tạm, chưa thêm vào repository.

Đây là bằng chứng trước sửa. Không ghi lại các con số này như kết quả nghiệm thu sau sửa. Tests đang xanh vẫn thiếu ba hành vi cần bảo vệ.

## 3. Giới hạn thực thi và bảo toàn dữ liệu

Được sửa frontend, tests liên quan và tài liệu kiểm chứng. Dự kiến không cần đổi API, database, worker hoặc inference.

Giữ nguyên:

- `demo/model.pt`, production `runtime/models/**`, active pointer, manifest, tokenizer và model configuration.
- Production `runtime/workspace.sqlite3`, WAL/SHM, dữ liệu nguồn, nhãn, review history, exports, jobs và dịch vụ đang phục vụ người dùng.
- Label schemas, review policy/thresholds, công thức attention, `effective`/`ai`, semantics `needs_review`, pipeline PhoBERT/ViSoBERT.
- Backend optimistic concurrency, source prediction validation, cancel/lease/attempt fencing, TTL, quota và idempotency.

Không train, tải weights, activate/import model production, deploy, commit hoặc push. Không cài framework agent hay dependency mới chỉ để sửa ba lỗi. Không chạy setup/start/stop production như bước mặc định.

Test server phải dùng runtime tạm và cổng loopback riêng. **Import `services.api.main` tạo default app/Store ngay khi import**: đặt `FEEDBACK_RUNTIME` sang thư mục tạm trước import nếu viết script độc lập. Pytest đã có isolation trong `tests/conftest.py`; giữ nguyên cơ chế đó. Test doubles chỉ nằm trong test code.

Browser tests đọc `apps/web/dist`, không trực tiếp đọc TSX. Build đúng source trước kiểm thử và không build đè khi browser suite đang chạy. Có thể build `dist` để nghiệm thu trong checkout dùng cho sửa lỗi; nếu app production đang dùng chính `dist` này, dùng checkout kiểm thử tách biệt với đầy đủ working tree để tránh thay assets đang phục vụ. Không thêm cơ chế deploy/runtime mới để giải quyết việc kiểm thử.

Chỉ một lượt kiểm thử model thật hoặc workload inference nặng tại một thời điểm. Không chạy `pytest-xdist`. Dừng đúng test process do mình tạo; không kill tất cả Python/Node.

## 4. R1: revision của nháp phải được giữ đến khi người dùng đối chiếu

### 4.1. Repro đã xác nhận

1. Tạo dataset NEU có câu `Dich vu rat tot.`; không cần model thật hoặc prediction.
2. Mở item ở current view, revision 1.
3. Chọn trạng thái cảm xúc `corrected`, nhãn `Positive` (ID 1), ghi chú `Draft for original positive text`; chưa lưu.
4. Từ API/tab khác, PATCH text thành `Dich vu rat te.` với `expected_revision=1`, tạo revision 2.
5. Ở dialog cũ, bấm `Lưu cảm xúc`.
6. Server trả `409 REVISION_CONFLICT`. Catch gọi refresh; effect tự đổi revision nền của nháp và xóa error/conflict.
7. Không còn cảnh báo; bấm `Lưu cảm xúc` lần nữa trả 200.

Bằng chứng quan sát:

```text
FIRST_SAVE 409 REVISION_CONFLICT
CONFLICT_BOXES_AFTER_409 0
ERROR_NOTICES_AFTER_409 []
SAVE_ENABLED_AFTER_409 True
SECOND_SAVE 200
SAVED text="Dich vu rat te.", revision=2,
      status="corrected", label_id=1,
      note="Draft for original positive text", source_prediction_id=null
```

Rủi ro: nhãn duyệt ảnh hưởng `effective`, attention và CSV. Backend đã từ chối request cũ đúng cách, nhưng frontend tự thay điều kiện optimistic concurrency cho lần bấm tiếp theo.

### 4.2. Điểm cần sửa

Trong `ItemDetail.tsx`:

- Khoảng dòng 158-165: nhánh dirty tự gán `base_revision_id = item.revision_id`, `base_revision = 0`.
- Khoảng dòng 181-186: revision đổi xóa error và toàn bộ conflict.
- `hasConflict`: revision khác có thể không được coi là conflict khi cả hai review revision đều bằng 0.
- `resolveConflict`: hiện chủ yếu xử lý review conflict trong cùng input revision.
- `saveReview`: gửi `expected_revision: item.revision`; chỉ gắn conflict explicit cho `REVIEW_CONFLICT`.
- UI nút resolve đang khóa dựa trên review revision bằng nhau; điều này không đủ cho input revision conflict.

### 4.3. Contract sau sửa

1. Khi input revision đổi, nháp dirty giữ nguyên status, label, note, source prediction và revision nền cũ cho đến khi người dùng đối chiếu. Task không dirty nhận review của revision mới bình thường.
2. Nếu `draft.base_revision_id !== item.revision_id`, task dirty phải có conflict, **kể cả review revision cũ và mới đều là 0**. Không tự rebase qua render, effect, refetch, reload từ sensitivity, focus hoặc polling.
3. Hiện cảnh báo bền: văn bản nguồn đã đổi, nháp thuộc revision cũ. Cho biết revision cũ/mới; giúp đối chiếu nội dung cũ/mới bằng snapshot đã giữ hoặc revision history hiện có. Không hiển thị lỗi này như chỉ có người khác sửa nhãn.
4. Khóa lưu task đang conflict và `Lưu và câu tiếp theo`. Có guard trong handler, không chỉ `disabled`. Task khác không conflict vẫn có thể lưu riêng theo semantics hiện có.
5. `409 REVISION_CONFLICT` phải giữ nháp và trạng thái cần đối chiếu. Nếu refetch lỗi/chưa có server snapshot mới, tiếp tục chặn lưu và cho retry tải. Không xóa cảnh báo chỉ vì đã gọi refresh.
6. Hai hành động resolve rõ ràng, riêng từng task:
   - **Dùng bản hiện tại, bỏ nháp:** nạp review server của input revision hiện tại, `dirty=false`, bỏ conflict của task đó.
   - **Áp nháp lên văn bản hiện tại:** người dùng chủ động xác nhận đã đối chiếu; cập nhật revision nền và review revision từ snapshot server hiện tại, giữ nội dung nháp, `dirty=true`. Hành động này chưa ghi review; người dùng bấm Lưu sau đó.
7. Không vô hiệu hóa nút resolve chỉ vì review revision hai phía bằng nhau. Phân biệt input revision conflict với review revision conflict; chỉ cho resolve khi đã có snapshot thích hợp.
8. Nếu server đổi thêm lần nữa sau resolve, API lại trả 409 và UI lại yêu cầu đối chiếu. Không retry ghi tự động với revision mới nhất.
9. Historical run có `item.stale=true` vẫn không được duyệt như hiện nay. Sửa R1 không mở khóa ghi vào revision lịch sử.

### 4.4. Provenance khi áp nháp qua input revision khác

Không thể đem `source_prediction_id` của revision 1 sang revision 2 và gọi nó là xác nhận AI cho revision 2.

Chốt hành vi tối thiểu cho lần sửa này:

- Dirty `confirmed`: giữ nguyên trong lúc conflict để đối chiếu. Khi người dùng chọn áp nháp sang revision mới, chuyển thành `corrected`, giữ label/note, đặt `source_prediction_id=null`. Copy của nút/thông báo phải giải thích đây là **nhãn tự chọn**, không còn xác nhận prediction cũ.
- Dirty `corrected`: giữ label/note, đặt `source_prediction_id=null` khi áp qua input revision khác, kể cả trước đó có gắn prediction.
- Dirty `unreviewed`: giữ note theo hành vi hiện có, `label_id` rỗng/null phù hợp form, `source_prediction_id=null`.
- Nếu muốn xác nhận prediction của revision mới, người dùng phải dùng nút `Xác nhận dự đoán đang xem` sau khi giải quyết conflict.
- **Không đổi provenance khi chỉ có review conflict trên cùng input revision** hoặc khi xem prediction khác của cùng revision: hành vi giữ nguồn xác nhận cũ phải tiếp tục đúng.

Có thể bổ sung trường local cho số input revision/text snapshot nếu cần; không cần đổi API. Tránh để handler `change` hoặc `confirmDisplayed` âm thầm xóa conflict nguồn. Không đổi `key` của `DetailContent` về revision ID vì sẽ làm mất nháp.

### 4.5. Test cũ đang bảo vệ hành vi sai

`tests/e2e/test_three_layer_demo.py::test_t08_current_view_revision_conflict_reload_keeps_review_draft`, khoảng dòng 2762:

- Test hiện tại đúng ở phần giữ label/note và reset task không dirty.
- Nhưng đang assert không có conflict cảm xúc rồi lưu nháp trực tiếp lên revision 2.
- **Phải đổi phần này**: assert nháp còn nguyên, cảnh báo input revision conflict có mặt, lưu bị khóa; sau hành động áp nháp explicit mới lưu được.
- Không xóa/skip test, không bỏ assert giữ nháp. Việc sửa expectation là thay đổi contract có chủ đích theo R1, phải ghi trong báo cáo.

## 5. R2: lỗi đọc trạng thái không có nghĩa job đã kết thúc

### 5.1. Repro đã xác nhận

1. Dùng controlled test server/runtime tạm; tạo vài sensitivity jobs chậm trước job đang xem để giữ job đó ở `queued`.
2. POST tạo job của panel thành công; UI đã biết `job_id`.
3. Chặn GET `/api/v1/sensitivity-experiments/{id}` và trả 500 cho initial GET cùng lần retry.
4. Chờ ErrorNotice rồi đóng `<details>` sensitivity.
5. Theo dõi request cancel và đọc job qua client kiểm thử độc lập.

```text
AFTER_POLL_ERROR_CLOSE
cancel_requests=0, status="queued", cancel_requested=false
```

Nguyên nhân: effect khoảng dòng 646-648 của `SensitivityPanel.tsx` xóa `activeJobIdRef.current` khi `experimentQuery.isError`. `isJobActive` cũng coi error là không active. Cleanup sau đó không còn ID để hủy.

### 5.2. Contract sau sửa

1. Tách trạng thái **không đọc được job** với **đã biết job terminal/không còn tồn tại**. Network error/5xx không xác nhận terminal.
2. Giữ ID của job đã tạo/đang theo dõi khi lỗi polling; vẫn cancel best-effort khi đóng panel, đổi selection, đổi item/run/revision hoặc unmount.
3. Chỉ bỏ ID khi đã có bằng chứng job terminal, response 404/NOT_FOUND xác thực từ endpoint, hoặc đã bàn giao yêu cầu cancel trong cleanup phù hợp. Không suy ra completed/cancelled từ transport error.
4. Vẫn hiện ErrorNotice và nút thử tải lại; retry/backoff có giới hạn như hiện tại. Không tạo vòng polling liên tục để tránh phải xử lý error.
5. Khi chưa biết terminal, panel giữ khả năng **Hủy thử nghiệm** theo ID đã biết. Chặn tạo job thay thế trực tiếp trên cùng selection/ngữ cảnh chỉ vì GET lỗi. Đổi selection vẫn reset và gửi cancel cũ; POST mới do người dùng bấm phải tuân quota backend nếu cancel chưa hoàn tất.
6. Response terminal thật hoặc 404 thật mở lại đường tạo thử nghiệm mới; không để nút chạy bị khóa vĩnh viễn.
7. Cleanup không cần đợi cancel trả về và không hứa hủy thành công khi offline. Dù cancel thất bại, UI mới không nhận kết quả cũ. Nếu người dùng chủ động bấm Hủy khi panel còn mở, lỗi cancel phải hiển thị và có thể thử lại.
8. Không hủy job đã biết terminal chỉ do một lần refetch sau đó gặp lỗi. Xem cả trạng thái cache và các thao tác retry mới hơn; kết quả terminal cũ không được lấn át một retry đang chờ.

Chỉ giữ ref mà không sửa các nút/status liên quan sẽ chưa đáp ứng trọn contract này.

## 6. R3: retry đến muộn phải được cleanup như create đến muộn

### 6.1. Repro đã xác nhận

1. Tạo sensitivity experiment `failed` bằng controlled registry (ví dụ marker `[PAIR_INVALID]`).
2. Bấm `Thử lại thử nghiệm`; giữ request `/jobs/{job_id}/retry` trong route Playwright.
3. Đóng panel trước khi cho request đi tiếp.
4. Thả request; server trả 200 và đưa job về queue/running.

```text
AFTER_DELAYED_RETRY_CLOSE
retry_http=200, cancel_requests=0, status="running", cancel_requested=false
```

Nguyên nhân: `handleRetryExperiment`, khoảng dòng 931-932, `await retryJob()` rồi `if (reqGen !== generationRef.current) return;`. Khác với `handleSubmit`, nhánh stale này không cancel.

### 6.2. Contract sau sửa

1. Nếu retry thành công nhưng generation không còn đúng, gửi cancel best-effort cho **job của retry đó**, rồi bỏ response. Không gắn result, lỗi, ref hoặc query data vào panel mới.
2. Không chỉ cancel lúc bắt đầu retry/đóng panel: request retry đến sau cancel có thể xếp job lại. Phải có cleanup sau response thành công đến muộn; request không có response vẫn là giới hạn best-effort được nêu rõ.
3. Cùng một xử lý cho đóng details, đóng dialog, đổi item, đổi selection hoặc đổi source context.
4. Nếu generation còn đúng, retry bình thường tiếp tục polling và hiển thị tiến độ/kết quả. **Không tự hủy retry hợp lệ**.
5. Giữ chống double-click/in-flight: một ý định retry chỉ gửi một request; nút chạy thử mới không được cạnh tranh với retry đang chờ của cùng panel. Không dùng generation để vô tình bỏ rơi job.
6. Không lấy `activeJobIdRef.current` của panel mới làm mục tiêu cancel response cũ. Capture target/response job ID trong closure của request.
7. Backend vẫn kiểm identity, source revision, quota và trạng thái retryable. Không nới guard hoặc tạo endpoint mới.

R2 và R3 cùng sửa một component, phải do cùng một owner phụ trách.

## 7. Ma trận regression tests

Ưu tiên Playwright tích hợp với API/worker ở runtime tạm; các lỗi đều nằm ở state, request timing và vòng đời component. Dùng fixtures/helper hiện có, không cài test framework mới. Có thể tách một file test mới nếu hợp lý, nhưng tránh copy toàn bộ controlled registry/server.

### R1

| Ca | Thiết lập và thao tác | Assertion bắt buộc |
|---|---|---|
| R1-A | Nháp corrected ở rev1; API sửa text rev2; lưu trả 409; refresh | Nháp còn nguyên; cảnh báo revision nguồn bền; không có review mới ở rev2; lưu task/save-next khóa; không auto PUT lần hai |
| R1-B | Background refetch hoặc sensitivity reload đưa rev2 về trước khi bấm lưu | Vẫn conflict dù chưa nhận 409; không tự rebase; giữ task độc lập |
| R1-C | Review revision hai phía đều 0, input revision khác nhau | Cảnh báo và nút resolve dùng được khi snapshot mới đã có; không bị kẹt “Đang tải bản server mới” |
| R1-D | Chọn áp nháp explicit, rồi lưu | Resolve không gửi PUT; lần Lưu gửi revision input/review hiện tại; label/note đúng; chỉ task đó thay đổi |
| R1-E | Chọn bỏ nháp | Nạp review server của revision mới; dirty/conflict hết cho task đó; không tự lưu |
| R1-F | Nháp confirmed gắn prediction rev1, source sang rev2 | Trước resolve giữ nháp; áp qua rev2 chuyển corrected/null provenance; không còn xác nhận prediction rev1 |
| R1-G | Cùng input revision nhưng review đổi ở tab khác; sửa note của confirmed | Conflict cũ vẫn đúng; áp nháp giữ nguồn prediction hợp lệ cùng revision |
| R1-H | Rev3 xuất hiện sau khi vừa resolve rev2, hoặc refetch sau 409 thất bại | Tiếp tục chặn ghi stale; không mất nháp/cảnh báo; resolve chỉ với snapshot thích hợp |

Giữ coverage historical stale, undo/restore, hai task dirty, save-next, export và pending signals hiện có. Kiểm tra trạng thái lưu bền bằng API/history, không chỉ text trên UI.

### R2

| Ca | Thiết lập và thao tác | Assertion bắt buộc |
|---|---|---|
| R2-A | POST thành công; GET 500 qua hết retry; đóng details | App phát POST cancel đúng ID; queued job thành cancelled hoặc running job có cancel_requested rồi terminal; không có result cũ |
| R2-B | Tương tự với lỗi network; đổi selection hoặc item/unmount | Cancel được phát sau khi đã biết ID; không đính kết quả vào context mới |
| R2-C | Poll lỗi nhưng panel còn mở | ErrorNotice và thao tác retry đọc/cancel còn dùng được; không tự tạo job mới; cancel lỗi hiển thị và thử lại được |
| R2-D | Đọc lại thành công sau error; nhận terminal hoặc 404 thật | Không tiếp tục coi job active vô hạn; mở được tạo mới; không phát cancel thừa cho terminal đã biết |

### R3

| Ca | Thiết lập và thao tác | Assertion bắt buộc |
|---|---|---|
| R3-A | Job failed; giữ retry POST; đóng details; thả retry thành công | Có cancel đúng job sau retry; không attach kết quả cũ |
| R3-B | Như trên nhưng đổi selection hoặc item/unmount | Panel mới không bị sửa; job mới của panel khác không bị hủy nhầm |
| R3-C | Server đã nhận retry, nhưng response bị giữ đến sau cleanup | Response đến muộn vẫn được xử lý an toàn; không dựa vào thứ tự cancel trước retry |
| R3-D | Retry trong cùng generation, kể cả double-click nhanh | Một retry request; không self-cancel; có progress/terminal; không bị kết quả terminal cache cũ làm mất tracking |
| R3-E | Retry bị từ chối do model/source đổi, 404 hoặc lỗi mạng | Error còn đúng; không attach job không tồn tại; không reset nháp rà soát; không vòng retry tự động |

**Thiết kế race test:**

- Dùng route giữ request/response và signal/event kiểm thử để chốt thứ tự. Không phụ thuộc việc máy “đủ chậm”.
- Bảo đảm job chưa terminal tại thời điểm kiểm cleanup: dùng controlled worker/registry gate trong test, hoặc backlog có handshake. Marker `[SLOW_PAIR]` hiện có chỉ là công cụ hỗ trợ, không dùng vài giây sleep làm bằng chứng duy nhất.
- Sau thao tác UI, assert request cancel do app phát; đọc API độc lập để xác nhận tác động. Không gọi `client.post(.../cancel)` trước assertion rồi kết luận app đã hủy.
- Teardown vẫn được hủy/dọn test jobs sau khi hoàn thành assertion; phân biệt với hành vi đang kiểm.
- Không hạ assertion, skip hoặc mở rộng danh sách bỏ qua console errors để làm suite xanh. Chỉ whitelist các lỗi được fault injection có chủ đích.
- Thêm ca negative control: bình thường không conflict và retry cùng generation không bị hủy. Không chỉ chứng minh “luôn khóa lưu”/“luôn cancel” làm test pass.

## 8. Phân công nếu Gemini có native subagents

Với scope nhỏ này, khuyến nghị **Gemini chính + một subagent QA/Review**. Không cần huy động lại cả nhóm Backend/Frontend/QA của lần triển khai ba lớp.

| Vai trò | Ownership | Trách nhiệm |
|---|---|---|
| Gemini chính | `ItemDetail.tsx`, `SensitivityPanel.tsx`; styles/helper local nếu thực sự cần; tài liệu báo cáo | Chốt contract, sửa R1-R3, build, tích hợp, kiểm chứng cuối |
| QA/Review | `tests/**` liên quan và evidence kiểm thử | Viết regression từ mục 7, chứng minh lỗi trên baseline, review production code read-only, kiểm tra bản tích hợp |

Một writer mỗi file. Hai bên đều biết có người khác làm trong cùng codebase, không revert edit của nhau. Nếu cần đổi ownership, owner cũ dừng, bàn giao file/hash rồi owner mới sửa. QA không sửa implementation để tự đóng finding mình review. Điều phối không sửa tests khi QA còn sở hữu chúng.

Trình tự phối hợp:

1. Chính chụp baseline và giao contract đầy đủ; QA đọc code và xây repro/tests.
2. QA chứng minh từng regression fail trên baseline vì đúng bug; sau đó bàn giao điểm kiểm thử. Chính có thể thiết kế sửa trong lúc này, nhưng không thay build đang dùng để chứng minh baseline.
3. Chính sửa implementation; QA hoàn thiện các ca còn lại mà không sửa cùng file.
4. Chốt source ổn định, build một lần, chạy tests theo thứ tự mục 9.
5. QA review diff thực tế cuối cùng và các negative controls; chính xử lý finding, kiểm lại phần bị tác động.

Nếu không có native subagents, thực thi tuần tự đầy đủ và ghi rõ không có reviewer độc lập. Không giả lập delegation, không tự gọi API bên ngoài hoặc cài framework. Không spawn lồng nhau. Không cần hỏi lại người dùng về các quyết định kỹ thuật đã chốt trong tài liệu này.

## 9. Các bước thực thi và lệnh kiểm chứng

### F0. Chụp baseline

- Đọc `AGENTS.md` nếu có, tài liệu này và file trọng tâm. Kiểm `git status`, branch, HEAD, runtime/build đang dùng.
- Lưu danh sách tracked/untracked, diff hiện hữu và hash source/build vào audit root riêng. Để phân biệt patch sửa lỗi với delta ba lớp đã có, giữ bản sao trước sửa của các file sẽ chạm; không chỉ dựa vào `git diff HEAD`.
- Dùng dependency hiện có. Nếu thiếu môi trường, chẩn đoán trước; không chạy lại setup production để tiện test.
- Không cần chạy lại full baseline suite chỉ để lặp các số lịch sử; ưu tiên regression fail có ý nghĩa.

```powershell
Set-Location -LiteralPath 'F:\DPL_NEU-ESC'
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
```

### F1. Regression đỏ trước sửa

- Viết các ca bắt R1, R2, R3, build baseline nếu cần.
- Lưu lệnh, assertion thất bại và nguyên nhân. Chứng minh red bằng hành vi app/API, không dùng test chỉ tìm chuỗi trong source.
- Đánh dấu test cũ mục 4.5 cần thay contract; không giữ kỳ vọng tự lưu xuyên revision chỉ để tránh test fail.

### F2. Sửa production code

- Sửa R1 trước vì ảnh hưởng nhãn bền; sau đó R2/R3 cùng một lượt rà soát vòng đời sensitivity.
- Đặt tên state/helper theo ý nghĩa: revision nháp gốc, conflict nguồn, job chưa biết terminal. Không bắt buộc phải viết state machine lớn.
- Giữ giao diện hiện có, thêm thông báo/nút resolve đúng ngữ cảnh. Keyboard và mobile phải dùng được; không thêm modal xác nhận cho mọi lần lưu thông thường.
- Các guard trong handler phải khớp `disabled`/status trên UI. Xem kỹ effect có thể ghi đè ref mới bằng cache cũ khi retry.

### F3. Build và targeted tests

Các lệnh chạy tuần tự. Mỗi lệnh phải kiểm exit code; không chạy bước sau khi bước trước fail.

```powershell
Set-Location -LiteralPath 'F:\DPL_NEU-ESC\apps\web'
npm.cmd run build

Set-Location -LiteralPath 'F:\DPL_NEU-ESC'
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_three_layer_demo.py -q
.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_regressions.py tests/e2e/test_workspace.py -q
```

Nếu regression được tách file mới, thêm file đó vào lệnh targeted; không bỏ các suites trên. Trong quá trình sửa có thể dùng node IDs hoặc `-k` để kiểm nhanh. Khi targeted đã xanh và source ổn định, không lặp lại vô cớ.

### F4. Kiểm chứng bản tích hợp cuối

```powershell
Set-Location -LiteralPath 'F:\DPL_NEU-ESC'
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -B -X utf8 -m pytest -m real_model -q
git diff --check
```

- Default suite và real-model suite chạy tuần tự, trên runtime tạm theo fixtures. Real-model tests phải dùng weights local; không sửa/reimport production bundle.
- Có thể số test tăng so với 272; báo số thực tế, không sửa collection để khớp số cũ.
- Nếu test bắt buộc fail/skip do môi trường, ghi rõ chưa nghiệm thu ở phần đó, không suy diễn từ kết quả reviewer trước sửa.
- Chụp và xem ảnh của conflict nguồn, thao tác áp nháp, polling error với cancel còn dùng được ở desktop/mobile; kiểm keyboard focus, nhãn nút, không overflow. Không cần làm lại thiết kế.
- Source thay đổi sau build/test thì build lại và chạy checks bị tác động. Báo cáo cuối phải khớp hash source/build cuối cùng.
- `git diff --check` không kiểm nội dung file untracked: kiểm whitespace riêng cho file mới được tạo.

### F5. Bàn giao

Cập nhật báo cáo kiểm chứng với mục R1-R3 mới, hoặc tạo `docs/THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md`. Không thay lịch sử bằng lời khẳng định chưa được kiểm.

Báo cáo phải có:

1. R1/R2/R3: nguyên nhân, behavior sau sửa, file/hàm đã sửa.
2. Những thay đổi so với baseline chưa commit lúc bắt đầu; tách khỏi implementation ba lớp vốn đã có.
3. Regression nào fail trước/pass sau; test cũ nào được cập nhật contract và vì sao.
4. Lệnh thực chạy, pass/fail/skip, thời gian, đường dẫn log/ảnh; nêu test double hay model thật.
5. Hash source/build cuối và kiểm bảo toàn production data/artifacts trong phạm vi thực sự đã kiểm.
6. Findings còn mở/giới hạn, nếu có. Trạng thái reviewer độc lập là có/không.

Final trả lời bằng tiếng Việt, ngắn gọn, link báo cáo và nêu kết quả kiểm chứng. Không commit/push.

## 10. Checklist nghiệm thu

- [ ] R1: nháp dirty không tự đổi revision nền khi input đổi; cảnh báo bền và guard lưu đúng.
- [ ] R1: giữ nháp, task độc lập, explicit apply/discard, review revision 0/0, failed refresh, revision đổi lần nữa đều được kiểm.
- [ ] R1: confirmed xuyên input revision được chuyển thành manual corrected chỉ sau thao tác explicit; provenance cùng revision không regress.
- [ ] R1: test cũ không còn khẳng định được lưu xuyên revision ngay sau reload.
- [ ] R2: lỗi polling giữ khả năng hủy đúng job; đóng/đổi context gửi cancel; không coi network error là terminal.
- [ ] R2: terminal/404 thật mở lại tạo mới; cancel khi error còn mở có lỗi hiển thị/thử lại.
- [ ] R3: retry đến muộn sau cleanup có cancel đúng target; retry bình thường không tự hủy; double-click không gửi trùng.
- [ ] Không có response/ref/query data cũ cập nhật panel khác hoặc xóa tracking của retry mới.
- [ ] Regression có bằng chứng đỏ/xanh; API xác nhận tác động, không chỉ DOM assertions.
- [ ] Build, targeted, full default và real-model checks trên bản cuối đã chạy hoặc ghi rõ phần bị chặn.
- [ ] Không thay production model, dữ liệu, policy; không commit/push; không bỏ delta người dùng.

## 11. Prompt khởi động cho chat Gemini mới

Dán đoạn này vào Gemini có quyền truy cập repository. Nếu Gemini không đọc được file local, gửi toàn bộ tài liệu này kèm đoạn khởi động.

```text
Bạn đang làm việc trong F:\DPL_NEU-ESC trên Windows/PowerShell.

Hãy thực thi kế hoạch trong:
F:\DPL_NEU-ESC\docs\THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md

Nhiệm vụ: sửa ba lỗi đã được review/tái hiện độc lập:
R1/P1: nháp rà soát tự rebase qua input revision mới sau conflict/refetch.
R2/P2: polling lỗi làm mất job ID nên đóng panel sensitivity không cancel.
R3/P2: retry thành công đến muộn sau khi panel đóng/đổi context không cancel.

Đọc toàn bộ handoff trước khi sửa. Handoff này chốt behavior, provenance,
ma trận regression và tiêu chí nghiệm thu; phần R1 thay expectation cũ đang
cho phép lưu nháp trực tiếp lên revision mới. Giữ nháp để đối chiếu, không
âm thầm nâng revision hoặc gắn prediction của văn bản cũ vào văn bản mới.

Repo có implementation ba lớp trong delta chưa commit, gồm file untracked.
HEAD baseline a0cebad8d625c68ca4df755de27a249e2b8ba134 không chứa đủ tính năng.
Resurvey trạng thái hiện tại, giữ mọi thay đổi đã có, chụp baseline của các
file sẽ sửa. Không reset/clean/stash, không commit/push/deploy. Không sửa
production runtime/database/model/policy hoặc nới optimistic concurrency.

Hãy làm đến khi code, regression tests và kiểm chứng hoàn tất; không dừng
ở một kế hoạch khác. Đặc biệt kiểm failed polling, delayed retry, 409 rồi
refetch, hai review revision cùng bằng 0 và provenance confirmed.

Nếu harness hỗ trợ native subagents, dùng Gemini chính viết implementation
và một QA/Review subagent sở hữu tests, review code read-only. Một writer
mỗi file; mọi agent phải giữ thay đổi của nhau. Không giả delegation hoặc
cài framework. Nếu không có subagent, làm tuần tự và nêu rõ giới hạn đó.

Chứng minh regression fail trên baseline, sửa tối thiểu, build đúng source
trước browser tests. Chạy targeted rồi full default và real-model tuần tự
trên runtime tạm. Import services.api.main có side effect: đặt runtime tạm
trước import trong script độc lập; giữ isolation của pytest.

Lưu báo cáo sau sửa theo mục 9/F5 của handoff. Trả kết quả tiếng Việt:
R1-R3 đã xử lý thế nào, files changed, tests thực chạy và findings còn mở.
Các kết quả 272 default/3 real-model pass trong handoff là trước sửa, không
được sử dụng thay cho bằng chứng của bản sửa cuối.
```
