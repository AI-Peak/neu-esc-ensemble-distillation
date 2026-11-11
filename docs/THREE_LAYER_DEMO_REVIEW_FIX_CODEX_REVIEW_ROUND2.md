# Code Review: R1/R2/R3 Follow-up - Round 2

Review độc lập ngày **2026-11-11, Asia/Saigon**. Workspace `F:\DPL_NEU-ESC`, branch `webapp`, HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134` cùng working-tree delta chưa commit.

**Kết luận: REQUEST CHANGES đối với phần tests/báo cáo C1.** F1, C2 và C3 đã đạt trong phạm vi kiểm chứng. Chưa phát hiện lỗi production mới; implementation cũng vượt qua ca stale payload thực sự do reviewer bổ sung. Tuy nhiên, hai thay đổi C1 chưa tạo được bằng chứng mà báo cáo follow-up khẳng định, nên chưa thể đóng toàn bộ scope bàn giao.

## Findings còn mở

### [P3] R2-C1a - Gỡ disabled ở DOM vẫn không đưa event vào handler React

- File chính: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:323).
- Vị trí tương tự: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:817), [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:1045), [test_three_layer_demo.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_demo.py:2864).
- Báo cáo liên quan: [follow-up report](F:/DPL_NEU-ESC/docs/THREE_LAYER_DEMO_REVIEW_FIX_FOLLOWUP_REPORT_2026-11-11.md:63).

`el.disabled = false` chỉ đổi DOM property. React vẫn giữ `props.disabled === true` của render hiện tại. Trong React 19.2.0 đang dùng, `getListener` trả `null` cho onClick của button có React props disabled: xem [react-dom-client.production.js](F:/DPL_NEU-ESC/apps/web/node_modules/react-dom/cjs/react-dom-client.production.js:1517). Native click có thể được phát nhưng callback `onClick` của component không được gọi.

Reviewer tái hiện trên build hiện tại, sau input-revision conflict và sau khi fieldset hết busy. Harness tạm bọc đúng callback đã bind để đếm invocation, giữ nguyên hành vi callback. Kết quả:

```json
{
  "domDisabled": false,
  "reactPropsDisabled": true,
  "nativeClickCount": 1,
  "handlerCallCount": 0,
  "handlerCallCountAfterDirectControl": 1,
  "put_count_including_initial_409": 1
}
```

Positive control gọi trực tiếp cùng callback làm counter tăng lên 1 và guard hiện tại không phát PUT thêm. Điều này phân biệt được việc handler có guard đúng với việc test forced click chưa chạy tới handler. Không có mutation production source trong phép đo này; việc truy cập React props nội bộ chỉ nằm trong harness audit tạm, không được thêm vào sản phẩm.

**Tác động:** các assertion “không có PUT” vẫn không bảo vệ guard bên trong handler như C1 yêu cầu. Comment trong tests và khẳng định “event được chuyển trực tiếp vào React synthetic event handler” trong báo cáo là sai. Đây là thiếu sót của kiểm thử, không phải bằng chứng guard production đang sai.

**Đề xuất:** giữ kiểm disabled ở UI, bổ sung harness thực sự gọi callback/action và chứng minh handler đã được thực thi. Thêm negative control/mutation phù hợp: khi bỏ lớp guard được bảo vệ trong bản sao kiểm thử, assertion phải fail. Nếu có nhiều guard lồng nhau, nêu rõ lớp nào được kiểm. Không chỉ tiếp tục đổi DOM attribute. Sửa mô tả evidence trong báo cáo follow-up tương ứng.

### [P3] R2-C1b - Test stale GET giữ request, nên nhận payload của attempt mới

- File: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:2210).
- Điểm thả request: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:2255).
- Báo cáo liên quan: [follow-up report](F:/DPL_NEU-ESC/docs/THREE_LAYER_DEMO_REVIEW_FIX_FOLLOWUP_REPORT_2026-11-11.md:64).

`hold_stale_exp_get` chỉ giữ `route`, chưa gọi upstream để chụp response trước retry. Khi `route.continue_()` chạy sau `_wait_flag(entered_flag)` và sau khi UI đã active, GET mới được gửi đến server. Lúc đó job đang ở attempt mới; request khởi phát sớm không đồng nghĩa payload thuộc attempt cũ.

Reviewer chạy nguyên hàm R3-D hiện tại với instrumentation chỉ quan sát đúng request bị giữ. Test pass, nhưng response của request đó là:

```json
{
  "test_passed": true,
  "captured_count": 1,
  "released_get_responses": [
    { "http": 200, "status": "running" }
  ]
}
```

Như vậy test chưa đưa payload `failed` của attempt cũ về sau retry, và không assert nội dung response là trạng thái cũ. Trường hợp nó kiểm hiện tại là request GET bị trì hoãn rồi nhận trạng thái mới, không phải race được mô tả trong C1.

**Đề xuất:** trong route trước retry, gọi `route.fetch()` để chụp response 200 có `status == "failed"`, giữ cả response và route. Cho retry mới được server chấp nhận, gate xác nhận `running`; sau đó `route.fulfill(response=snapshot)` với response cũ. Assert payload/thứ tự đã quan sát, active UI vẫn đúng, create còn khóa, không self-cancel và cleanup vẫn hủy đúng job. Nếu kiểm isolation cụ thể, dùng mutation có kiểm soát trong bản sao để xác nhận test bắt được lỗi cần bảo vệ.

Reviewer đã thử chính biến thể giữ response này bằng harness tạm và **implementation hiện tại pass**:

```json
{
  "captured_status_before_retry": "failed",
  "server_status_at_delivery": "running",
  "delivered_status_after_retry": "failed",
  "test_passed_with_real_stale_payload": true
}
```

Vì vậy không có yêu cầu sửa production code từ finding này; cần đưa scenario đúng vào regression suite và sửa khẳng định đã hoàn tất C1.

## Đối chiếu F1/C1/C2/C3

| Hạng mục | Kết quả | Evidence và giới hạn |
|---|---|---|
| F1: ghi nhớ 404 qua 500 | PASS | `not_found` được lưu trong tracked state/ref và gắn attempt; R2-D mở rộng pass trên bản hiện tại, fail đúng trên bundle trước follow-up. |
| F1: 404 qua network error và unmount | PASS | Reviewer kiểm riêng với 404 thật rồi abort GET; create vẫn enabled, không active/cancel UI, unmount phát 0 cancel. |
| F1: tạo mới sau 404 không bị marker cũ lấn át | PASS | Tạo job mới trên cùng selection, không reset context; job mới active, create khóa; close chỉ cancel job mới và API xác nhận cancelled. |
| F1: UI/ref/query nhất quán | PASS | UI dùng `isConfirmedNotFound`; effect giữ ref null khi locallyTerminal đúng attempt. Transport lỗi đơn thuần vẫn giữ tracking job chưa biết terminal. |
| C1: handler guard test | CHƯA ĐẠT | Forced DOM click vẫn bị React props.disabled chặn trước handler; R2-C1a. |
| C1: stale GET test trong repository | CHƯA ĐẠT | Request bị giữ chưa có snapshot response; khi thả nhận running của attempt mới; R2-C1b. |
| C1: production chịu được stale payload thật | PASS, kiểm bổ sung | Harness reviewer chụp failed trước retry, giao failed sau running; active tracking và hoàn tất hợp lệ vẫn đúng. Evidence này không thay thế việc bổ sung permanent regression. |
| C2: confirmed qua explicit apply thành corrected/null | PASS | Test cũ giữ confirmed/source đến sau refetch; explicit apply đổi status, giữ label/note; API assert source null tại dòng 2893. |
| C2: giữ coverage corrected draft | PASS | Các ca R1-A/D/E và các case khác vẫn tạo corrected draft; không mất toàn bộ coverage cũ khi thay flow test t08. |
| C3: bỏ guard unreachable | PASS | Effect chỉ còn một nhánh locallyTerminal có kiểm attempt; không còn guard terminal-to-active lặp phía sau. |
| Regression GET thứ hai sau 404 | PASS trong suite hiện có | Nhánh 404 không gọi removeQueries; test TTL hiện có pass trong nhóm three-layer E2E. |

### Nhận xét implementation

[SensitivityPanel.tsx](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:675) chỉ chọn tracked state cùng experiment và attempt hiện tại. [Nhánh 404](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:704) lưu `status: "not_found"`, `attempt: retrySeq`; [locallyTerminal](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:723) ngăn exp cached active khôi phục ref. [UI](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:1334) ưu tiên outcome đã xác nhận, nên lỗi transport đến sau không che mất trạng thái hết hạn.

Các đường cập nhật tracked state đã được đọc: create ở dòng 966, cancel ở dòng 1027, retry ở dòng 1105, theo dõi existing job ở dòng 1294 và query sync ở dòng 746. Các đường này gắn attempt tương ứng; reset selection/context xóa tracking, create/retry tăng sequence và query key gồm sequence. `attempt` còn là optional type nhưng các đường ghi hiện tại đều cấp giá trị; chưa thấy lỗi chức năng từ optional fallback trong phạm vi review.

`ItemDetail.tsx` và `styles.css` có SHA-256 giữ nguyên so với vòng một. Guard R1 vẫn có ở confirmDisplayed/saveReview/save; thay đổi C2 nằm ở test. Bản sửa không cần đổi API, worker hay provenance backend để vượt qua các ca đã kiểm.

## Kiểm chứng độc lập

### Môi trường và artifacts

Audit root của lượt này:
[codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f).

Mọi server kiểm thử dùng `GatedControlledRegistry`/registry doubles có sẵn, runtime tạm và loopback port riêng. Không chạy model inference, không chạy production server. Source/tests repository được giữ nguyên; chỉ báo cáo vòng hai được tạo trong repository. Scripts và evidence bổ sung nằm trong audit root.

| Kiểm chứng | Kết quả |
|---|---|
| `.\node_modules\.bin\tsc.cmd --noEmit` tại apps/web | Exit 0 |
| Vite build ra `<audit>\dist` | Exit 0, 86 modules, 1.49s |
| So SHA-256 build tạm với dist đang dùng trong tests | HTML, JS, CSS đều khớp |
| Bốn file E2E trên bản hiện tại | **46 passed in 370.58s (0:06:10)**, exit 0, không fail/skip |
| R2-D mở rộng trên bundle trước follow-up | **1 failed in 23.58s**, exit 1; fail đúng dòng 1752 vì run button disabled sau 404 -> 500 |
| Audit C1 callback và GET payload | Exit 0; xác nhận cả hai lỗ hổng coverage |
| Ca bổ sung F1/network/create và stale payload thật | Exit 0; các assertion đều pass |
| `git diff --check` | Exit 0; chỉ có thông báo LF/CRLF của Git |

Lệnh chạy scripts dùng `F:\DPL_NEU-ESC\.venv\Scripts\python.exe -B -u -X utf8 <script>`. Các entry points/evidence:

- [run_review_tests.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/run_review_tests.py): gọi pytest cho đúng bốn file E2E, `-q -x --tb=short -p no:cacheprovider`, runtime và screenshots riêng. Không đổi assertion tests. Kết quả: [e2e-tests.log](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/e2e-tests.log).
- [check_f1_before_fix.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/check_f1_before_fix.py) và [f1-before-fix.log](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/f1-before-fix.log): chạy R2-D mới với build lưu từ vòng một, bằng route phục vụ assets cũ. Không checkout/reset hoặc thay dist repository.
- [audit_c1.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/audit_c1.py) và [c1-audit-result.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/c1-audit-result.json): đo callback invocation và quan sát response của request bị giữ trong chính test R3-D hiện tại.
- [check_f1_and_real_stale.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/check_f1_and_real_stale.py) và [boundary-results.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/boundary-results.json): kiểm 404/network/unmount, tạo mới sau 404 và dùng proxy route trong harness để giao snapshot failed thật qua retry.

Bundle trước follow-up nằm tại [dist vòng một](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/dist). JS `index-C01NbrIq.js` có SHA-256 `B5428BCEDDA9C0B2584C4AF86B68C3342A659E6BA6A1DBBBC37647DA3B153BDA`, đã được xác minh ở vòng một. Đây là đúng baseline còn F1 sau khi R1/R2/R3 được sửa lần đầu, không phải bundle cũ trước toàn bộ R1/R2/R3.

### Source/build identity

Các hash thực đo khớp toàn bộ hash trọng tâm người dùng bàn giao:

| File | SHA-256 |
|---|---|
| SensitivityPanel.tsx | `512FB509291690D9C327CA71AFD6A39086E992E435B22531375B3E2E26564FCF` |
| test_three_layer_review_fixes.py | `31A2AD439AE3BA6F8A5FEF2534E547D17EEAAD00C2CB376E231DD3C64C19A388` |
| test_three_layer_demo.py | `9263EB82A77459730AB13E0769236178B8A25345042621EB71C2F573C7120DAA` |
| index.html | `9006FF034CC7DD659CE3E85A1C7FCD69C18DB08B8D40A05C7C957C8E538D1BA4` |
| index-DfAjhymE.js | `B0E9984135F1DAFE41939C254CE19F5A555FB02E0F814E394C08A3C18BCE53A2` |
| index-D30vz0W7.css | `2D9D6B1C830C0791BF17F697C1F5D2E83774041CA215A587C2A55C599AEF11AC` |

Evidence: [source-hashes-before.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/source-hashes-before.json), [source-hashes-after.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/source-hashes-after.json), [build-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-round2-8425b3ba274b421abcfeaf55a6449e9f/build-verification.json).

Đối chiếu cuối lượt: cả 8 file source/test trong manifest trước/sau giữ nguyên SHA-256. So sánh `git status --porcelain=v1` chỉ có thêm báo cáo vòng hai này; branch và HEAD vẫn đúng như bàn giao.

### Giới hạn

- Không chạy lại toàn bộ 292 tests hoặc real-model tests. Default suite có synthetic-model inference dù loại marker real_model; giữ giới hạn không inference từ nhiệm vụ review.
- Báo cáo Gemini không cung cấp đường dẫn snapshot source trước follow-up hoặc logs chi tiết. Review này dùng source hiện tại, hashes vòng một, bundle vòng một đã xác minh và các lần chạy độc lập. Không tuyên bố đã tái dựng toàn bộ diff follow-up từ một source snapshot chưa được cung cấp.
- Các nhận xét chỉ thuộc scope F1/C1/C2/C3 và bảo vệ R1/R2/R3; không review lại toàn bộ delta ba lớp, không kiểm toàn bộ model/database production.
- Không tạo subagent trong lượt review Codex này; kết luận về tests được kiểm độc lập với nhóm Gemini đã viết chúng.

## Tổng kết nghiệm thu

- **F1: đạt. C2: đạt. C3: đạt. C1: chưa đạt ở cả hai phần coverage.**
- Hai findings còn mở đều **P3 về tests và độ chính xác của báo cáo**; không ghi nhận lỗi chức năng production mới từ lượt kiểm chứng này.
- **REQUEST CHANGES** để đóng scope follow-up: sửa handler-guard test thực sự đi tới handler, giữ/thả response payload cũ đúng cách, cập nhật evidence C1 và chạy lại checks liên quan.
- Implementation hiện tại đã vượt qua hai ca audit bổ sung tương ứng, nên chưa có căn cứ yêu cầu thay đổi production code chỉ để xử lý hai findings này.
