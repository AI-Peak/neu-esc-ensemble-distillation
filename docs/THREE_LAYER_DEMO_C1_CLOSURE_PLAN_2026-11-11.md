# Kế hoạch đóng hai findings C1 sau review vòng 2

## 1. Mục tiêu và điểm dừng

Thực thi tại `F:\DPL_NEU-ESC`. Đây là nhiệm vụ sửa tests và hoàn tất nghiệm thu, không phải yêu cầu viết thêm kế hoạch.

Baseline đã review: branch `webapp`, HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134` cộng toàn bộ working-tree delta, gồm nhiều file untracked. Không chỉ dùng HEAD làm baseline: HEAD chưa chứa đầy đủ implementation.

Production hiện tại đã vượt qua kiểm chứng F1, C2, C3 và phép kiểm stale payload thật. Hai findings còn mở là **P3 về độ đúng của tests và evidence C1**:

1. R2-C1a: gỡ `disabled` ở DOM không làm React gọi handler.
2. R2-C1b: giữ request rồi `continue_()` sau retry không tạo response thuộc attempt cũ.

Mục tiêu là sửa đúng hai khoảng trống này, giữ các kiểm tra đã đạt, cập nhật báo cáo trung thực và kết luận hoàn tất ngay khi đáp ứng mục 8. Không tự mở thêm một đợt audit toàn codebase, không bắt người dùng chuyển tiếp qua nhiều chat để đóng cùng hai findings. Chỉ mở rộng sửa production nếu có lỗi mới tái hiện được trực tiếp từ scope này; ghi rõ bằng chứng và thay đổi tối thiểu.

## 2. Tài liệu và baseline phải đọc

Đọc theo thứ tự:

1. `F:\DPL_NEU-ESC\docs\THREE_LAYER_DEMO_REVIEW_FIX_CODEX_REVIEW_ROUND2.md`: findings chính thức, giải thích và kết quả audit.
2. `F:\DPL_NEU-ESC\docs\THREE_LAYER_DEMO_REVIEW_FIX_FOLLOWUP_REPORT_2026-11-11.md`: các claim C1 cần sửa, khoảng dòng 63-64.
3. Các phần liên quan trong `F:\DPL_NEU-ESC\tests\e2e\test_three_layer_review_fixes.py`, `F:\DPL_NEU-ESC\tests\e2e\test_three_layer_demo.py`, `F:\DPL_NEU-ESC\apps\web\src\ItemDetail.tsx` và `F:\DPL_NEU-ESC\apps\web\src\SensitivityPanel.tsx`.
4. Chỉ tra spec R1/R2/R3 trong `F:\DPL_NEU-ESC\docs\THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md` khi cần xác định hành vi. Những yêu cầu audit rộng hoặc chạy full/model tests ở handoff cũ không mở rộng scope của kế hoạch này.

Kiểm tra hướng dẫn repository áp dụng nếu có. Lưu branch/HEAD, `git status --porcelain=v1`, diff và SHA-256 của các file sẽ sửa vào audit directory riêng trước khi edit. Snapshot cả nội dung file untracked liên quan; `git diff` không đủ để lưu chúng. Snapshot chỉ phục vụ đối chiếu, không khôi phục đè lên thay đổi của người khác.

Các hash trọng tâm của baseline:

| File | SHA-256 |
|---|---|
| `apps/web/src/ItemDetail.tsx` | `80051FAFCFDDF3D243BFDB46BB36454ABB52742F52C63803CB5080953A5AC457` |
| `apps/web/src/SensitivityPanel.tsx` | `512FB509291690D9C327CA71AFD6A39086E992E435B22531375B3E2E26564FCF` |
| `tests/e2e/test_three_layer_review_fixes.py` | `31A2AD439AE3BA6F8A5FEF2534E547D17EEAAD00C2CB376E231DD3C64C19A388` |
| `tests/e2e/test_three_layer_demo.py` | `9263EB82A77459730AB13E0769236178B8A25345042621EB71C2F573C7120DAA` |

Nếu snapshot khởi đầu khác baseline trên, kiểm tra delta mới trước khi áp dụng; không ghi đè để ép hash khớp. Nếu file đổi ngoài dự kiến trong lúc mình đang làm, dừng phần ghi chồng lấn và báo người dùng.

## 3. Phạm vi sửa và phối hợp

Phạm vi dự kiến:

- Hai file E2E nêu trên.
- Một helper dùng chung trong `tests/e2e/` nếu giúp tránh lặp; không copy cả server/registry.
- Báo cáo follow-up: giữ lịch sử, thêm correction chỉ rõ evidence C1 cũ không đủ và trỏ đến bằng chứng mới. Không sửa báo cáo review độc lập vòng 1/vòng 2 để biến kết luận cũ thành pass.
- Báo cáo hoàn tất mới: `F:\DPL_NEU-ESC\docs\THREE_LAYER_DEMO_C1_CLOSURE_REPORT_2026-11-11.md`.

Không dự kiến sửa production, API, database, worker, inference, CSS hoặc dependencies. Không thêm test hook vào production chỉ để test dễ hơn. Không commit/push/deploy/reset/clean/stash. Giữ nguyên delta của người dùng.

Nếu có native subagent và thấy có ích: dùng tối đa một subagent QA đọc tests/evidence độc lập. Agent chính sở hữu mọi edit tests/helper/report; QA không sửa các file đó, không chạy suite nặng song song, không spawn tiếp. QA phải đánh giá cả tests do agent chính viết, đặc biệt positive/negative controls. Nếu không có subagent thì tự kiểm tuần tự và ghi rõ, không cài framework hoặc giả lập reviewer độc lập. Không cần thêm một chat hay sự xác nhận của người dùng cho các bước đã được giao.

## 4. Sửa R2-C1a: thực sự chạy handler guard

### 4.1. Vị trí và lý do

Trong `test_three_layer_review_fixes.py`, tìm các đoạn quanh dòng 323/324, 817, 1045/1046. Trong `test_three_layer_demo.py`, kiểm đoạn quanh 2864/2865. Dùng tên test/đoạn code để định vị vì line sẽ đổi sau edit.

Các đoạn `el.disabled = false; el.click();` không chứng minh handler guard: React 19.2.0 vẫn thấy React props.disabled là true và bỏ qua onClick. Audit trước đo native click = 1, callback invocation = 0.

Giữ các assertion nút disabled. Thay phần tuyên bố kiểm guard bằng cách thực sự gọi callback/action của component với conflict đang tồn tại.

### 4.2. Cách triển khai ưu tiên, không thêm framework

Repository hiện chưa có component-test runner. Có thể dùng helper chỉ nằm trong E2E để lấy **callback onClick đang bind trên chính button hiện tại** và gọi trực tiếp, bỏ qua lớp dispatch disabled của React:

1. Tìm React props trên DOM node của button theo prefix `__reactProps$` của React đang pin trong package.json. Đây là adapter dành riêng cho test; không đưa vào app.
2. Assert tìm đúng props, `typeof onClick === "function"`, và trạng thái disabled/conflict đúng kỳ vọng. Nếu adapter không tìm được callback, test phải fail rõ ràng, tuyệt đối không skip hoặc im lặng fallback sang click.
3. Lấy callback từ render hiện tại mỗi lần gọi; không giữ closure trước khi conflict được render. Không thay `props.disabled`, props khác, state hoặc nội dung callback để làm scenario dễ pass.
4. Gọi chính callback đó; ghi bằng chứng callback được gọi đúng số lần. Nếu callback có dùng event, cung cấp event đúng phần nó cần. Hiện các button save bọc `() => void save(...)`, vì vậy không được giả định `await onClick()` chờ toàn bộ save async hoàn tất.
5. Theo dõi request và UI phù hợp để kiểm side effect sau invocation. Giải thích helper gọi trực tiếp bound callback, không gọi đó là một synthetic click đã đi qua React event dispatch.
6. Ghi ngắn gọn dependency vào React internals trong helper. Nếu có phương án harness ổn định hơn dùng hạ tầng sẵn có mà không thêm dependency hay sửa app, có thể dùng, nhưng phải chứng minh invocation tương đương.

Không chỉ đổi `el.click()` thành `dispatchEvent()` hoặc `click(force=True)`; cả hai đều chưa đủ nếu React vẫn chặn disabled listener.

### 4.3. Assertions bắt buộc

- Conflict sau 409 + đã tải snapshot mới: gọi callback Save và Save & Next; không thêm PUT, không tự chuyển item, giữ draft và conflict.
- Conflict + GET snapshot mới lỗi/chưa tải được: gọi callback Save và Save & Next; vẫn không thêm PUT, không mất draft hoặc resolve ngầm.
- Confirm displayed khi có prediction mới nhưng draft còn conflicted: callback được gọi; source_prediction_id/label/note của draft cũ không bị thay bằng prediction mới, banner conflict còn nguyên. Nút confirm vốn thay local state nên không dùng riêng assertion không PUT để kết luận nó có guard đúng.
- Các đoạn tương tự trong test_three_layer_demo.py phải được sửa hoặc đổi mô tả về đúng mức coverage thực tế; không để claim handler guard dựa vào forced DOM click cũ.

### 4.4. Positive và negative controls

Positive control: dùng cùng adapter/callback path trên trạng thái hợp lệ để quan sát side effect vốn phải xảy ra, chẳng hạn save tạo đúng một PUT hoặc confirm cập nhật đúng prediction. Có thể tận dụng flow resolve/save hiện có; không cần dựng một framework mới. Counter tăng đơn thuần không đủ làm positive control.

Negative control: trong **bản sao frontend của working tree hiện tại ở thư mục tạm**, vô hiệu hóa đúng guard conflict mà test muốn bảo vệ rồi chạy targeted test mới. Không sửa production workspace để tạo mutant rồi sửa lại. Không dùng checkout từ HEAD vì thiếu untracked implementation.

Lưu ý `ItemDetail.tsx` có guard lồng nhau ở `save()` và `saveReview()`; Save & Next có thêm guard task-wide. Nếu bỏ một guard mà guard còn lại vẫn chặn, việc test vẫn pass không chứng minh test vô dụng. Thiết kế mutant bỏ các conflict gates liên quan đến hành vi được kiểm, giữ các kiểm tra không liên quan. Với confirmDisplayed, bỏ riêng conflict gate là một mutant độc lập. Ghi chính xác lớp/hành vi đã được kiểm, không tuyên bố unit coverage riêng cho tất cả inner guards khi outer guard đã return.

Yêu cầu tối thiểu: mutant save-conflict phải làm test fail vì PUT phát sinh hoặc navigation không hợp lệ; mutant confirm-conflict phải làm test fail vì draft/provenance bị đổi. Fail do build lỗi, adapter lỗi, server không chạy hoặc timeout không liên quan không được tính. Bản production hiện tại phải pass cùng các tests đó.

Không cần chạy toàn bộ 46 ca trên mutant. Lưu diff mutant, lệnh, log và assertion thất bại để kết quả có thể kiểm tra lại.

## 5. Sửa R2-C1b: giữ và giao đúng response của attempt cũ

Test chính: `test_r3_d_same_generation_retry_double_click_no_self_cancel_and_stale_cache` trong `test_three_layer_review_fixes.py`, đoạn khoảng 2206-2275.

Thứ tự cần đảm bảo:

1. Attempt 1 đã failed, retry button hiện. Xác định experiment/job đúng; route chỉ capture GET chi tiết liên quan, không vô tình bắt list endpoint hoặc job khác.
2. Trong route handler trước retry, gọi `route.fetch()` để thực sự lấy response lúc attempt 1 còn failed. Assert HTTP 200, payload.status == failed và identity khớp experiment/job. Lưu `(route, response)` và payload; chưa fulfill browser.
3. Chỉ sau khi snapshot cũ đã được chụp, double-click retry. Giữ kiểm đúng một retry POST và gate worker đang có.
4. Thả retry POST; đợi server xác nhận running bằng entered flag/API. Assert UI active, cancel visible, create disabled, chưa có cancel request.
5. Thả **response đã chụp** bằng `route.fulfill(response=snapshot)`; không gọi fetch lại/continue_ ở bước này. Theo dõi đúng request/response để chứng minh payload delivered vẫn là failed dù server hiện running. Fulfill thành công đơn thuần chưa đủ nếu request bị abort hoặc response chưa được quan sát.
6. Đợi response được browser nhận/hoàn tất bằng event thích hợp và UI có cơ hội xử lý. Sau đó assert UI vẫn active, cancel vẫn hiện, create vẫn disabled, không tự cancel. Không dùng riêng một sleep rồi cho rằng đã tạo được race.
7. Thả worker gate, đợi kết quả hoàn tất; API completed, create enabled, không self-cancel. Giữ coverage double-click và completion vốn có.
8. Cleanup route/gate/context/client/server trong finally hoặc fixture teardown phù hợp, kể cả khi assertion fail. Chỉ tác động tài nguyên của test.

Để chứng minh test thực sự giao payload cũ, assertion captured=failed, server-at-delivery=running, delivered=failed là bắt buộc. Có thể dùng negative control trả running thay snapshot cũ và xác nhận assertion delivered=failed fail; điều đó chỉ chứng minh scenario không bị giả, không được gọi là mutation coverage của query isolation production. Không bắt buộc thêm mutation production thứ ba cho C1b khi đã có payload/thứ tự quan sát rõ ràng và các assertion hành vi.

Reviewer trước đã chạy biến thể đúng này và implementation pass. Dùng audit script làm tài liệu tham khảo, rồi đưa scenario vào permanent test; không chỉ sửa script tạm và tuyên bố repository test đã được sửa.

## 6. Kiểm chứng trong phạm vi hữu hạn

Không chạy production server, model inference kể cả synthetic-model inference, train/download weights, full pytest toàn repo hoặc pytest-xdist. Dùng registry doubles hiện có, runtime tạm và port loopback riêng. Nếu script độc lập import API, đặt FEEDBACK_RUNTIME sang thư mục tạm trước import `services.api.main`. Fixtures pytest hiện có đã xử lý isolation; không phá cơ chế đó.

Thứ tự:

1. Chạy targeted tests C1a/C1b sau edit để debug.
2. Chạy positive/negative controls nêu trên trên đúng bundle tương ứng; lưu evidence.
3. Tại `F:\DPL_NEU-ESC\apps\web`, chạy `.\node_modules\.bin\tsc.cmd --noEmit` và `.\node_modules\.bin\vite.cmd build --outDir <đường-dẫn-dist-tuyệt-đối-trong-audit-mới>`. Thay placeholder bằng thư mục riêng của lượt này. Dùng local binary, không cài package qua npx.
4. Xác minh dist mà E2E thực sự phục vụ tương ứng production source hiện tại. Nếu production giữ nguyên, so hash output tạm với dist hiện có là đủ; không trỏ final suite nhầm sang mutant. Nếu buộc phải sửa production, cập nhật bundle E2E theo cơ chế repo và ghi rõ.
5. Chạy đúng bốn file dưới đây trên bản cuối cùng, một lượt tổng hợp sau khi các targeted checks đã đạt.

```powershell
.\.venv\Scripts\python.exe -B -u -X utf8 -m pytest tests/e2e/test_three_layer_review_fixes.py tests/e2e/test_three_layer_demo.py tests/e2e/test_regressions.py tests/e2e/test_workspace.py -q -x --tb=short -p no:cacheprovider
```

Có thể dùng wrapper đã có để redirect basetemp/screenshots vào audit directory mới. Baseline là **46 passed, 0 skipped**; nếu thêm test count có thể tăng. Không xóa test/giảm assertion/skip để đạt số pass. Nếu fail, sửa nguyên nhân trong scope rồi chạy lại phần bị ảnh hưởng; kết quả bàn giao phải tương ứng phiên bản file cuối cùng.

6. Chạy `git diff --check`, kiểm trailing whitespace cả file untracked mới, đối chiếu source hashes và trạng thái Git trước/sau; ghi rõ mọi file thay đổi do lượt này.

Không chạy lại bộ lớn thêm nhiều lần khi đã pass và không có thay đổi mới. Không tự đặt việc review lại toàn bộ R1/R2/R3 là điều kiện kết thúc.

## 7. Evidence sẵn có để tái sử dụng

Audit vòng 2 nằm tại:

`C:\Users\Admin\AppData\Local\Temp\codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f`

Các file hữu ích:

- `audit_c1.py`, `c1-audit-result.json`: đo native click/handler và quan sát response của test cũ.
- `check_f1_and_real_stale.py`, `boundary-results.json`: ca stale payload thật đã pass và hai ca biên F1 đã pass.
- `run_review_tests.py`, `e2e-tests.log`: wrapper và kết quả 46 passed in 370.58s.
- `source-hashes-before.json`, `source-hashes-after.json`, `build-verification.json`: identity đã kiểm.

Đây là artifact tham khảo, không phải dependency cho tests lâu dài. Nếu temp directory đã mất, tự xây lại helper tối thiểu từ findings; không bắt người dùng cung cấp lại. Lưu các kết quả mới vào audit directory riêng và dùng link tuyệt đối trong báo cáo. Không dùng log cũ làm bằng chứng cho tests mới.

## 8. Definition of Done và báo cáo cuối

Chỉ kết luận hoàn tất khi đủ tất cả:

- [ ] Callback thật được gọi trong các trường hợp C1a cần bảo vệ; UI disabled vẫn được kiểm riêng.
- [ ] Positive control có side effect quan sát được; mutant save và confirm fail đúng assertion hành vi, bản production pass.
- [ ] R3-D chụp failed trước retry, server running trước delivery, giao failed thật sau retry; tracking và completion vẫn đúng.
- [ ] Không còn comment/report tuyên bố forced DOM click cũ đã kiểm handler hoặc request giữ lại đã là response cũ.
- [ ] Các kiểm F1, C2, C3 và regression TTL không bị mất hay nới assertion.
- [ ] Bốn file E2E cuối cùng pass, không fail/skip; typecheck/build/diff check đạt.
- [ ] Source production giữ nguyên, hoặc mọi thay đổi production đều có repro/evidence cụ thể; mọi thay đổi ngoài scope được bảo toàn.
- [ ] Báo cáo hoàn tất ghi file thay đổi, cách fix, bảng evidence cho từng finding, lệnh/exit code/test count/duration, đường dẫn logs, hashes cuối và giới hạn còn lại.

Báo cáo kết luận một trong hai trạng thái rõ ràng: **ĐÃ HOÀN TẤT hai findings C1** hoặc **CHƯA HOÀN TẤT**, kèm đúng mục còn thiếu. Không gọi tự kiểm là review độc lập nếu không có reviewer độc lập. Nếu QA subagent có tham gia, ghi nó đã đọc gì và có sở hữu test nào không.

Final trả lời tiếng Việt, ưu tiên câu trả lời: đã xong chưa, production có phải sửa không, tests nào đã chạy, có gì còn chặn. Link báo cáo hoàn tất. Khi đủ Definition of Done thì chốt, không yêu cầu một vòng xác nhận của người dùng để thực hiện các bước đã được giao.

Cuối final cung cấp một prompt ngắn để người dùng có thể mang về chat review nếu muốn. Prompt phải có workspace, branch/HEAD thực tế, các file đã sửa, đường dẫn báo cáo/evidence, kết quả tests và hashes trọng tâm; yêu cầu review delta C1 mới. Đây là lựa chọn kiểm tra bổ sung của người dùng, không phải điều kiện bắt buộc để agent thực thi được phép báo đã hoàn tất.
