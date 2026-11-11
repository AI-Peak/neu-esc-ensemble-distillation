# Code Review: R1/R2/R3 Bug Fixes

## Tổng quan

**Đánh giá: REQUEST CHANGES.** Có một lỗi chức năng P2 còn mở trong R2: sau khi GET experiment đã trả **404 thật**, một lần refetch lỗi 500 làm UI coi experiment đó là active trở lại, khóa tạo thử nghiệm mới và gửi cancel thừa khi đóng panel. Đã tái hiện độc lập; xem finding F1.

Review ngày **2026-11-11, Asia/Saigon**, tại `F:\DPL_NEU-ESC`, branch `webapp`, HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134` cùng delta chưa commit. Phạm vi là logic R1/R2/R3, CSS liên quan, 20 regression tests mới và test cũ được đổi contract; không đánh giá lại toàn bộ M0-M4.

Nguồn hành vi chính là [handoff](F:/DPL_NEU-ESC/docs/THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md). Đã đối chiếu [báo cáo sửa lỗi](F:/DPL_NEU-ESC/docs/THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md), các contract liên quan trong [kế hoạch kiến trúc](F:/DPL_NEU-ESC/docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md), [PRODUCT.md](F:/DPL_NEU-ESC/PRODUCT.md) và [DESIGN.md](F:/DPL_NEU-ESC/DESIGN.md).

R1 đã xử lý đúng lỗi silent rebase, giữ snapshot nháp, phân biệt hai loại conflict và làm sạch provenance khi người dùng áp nháp qua input revision. R3 đã thêm cancel sau response retry đến muộn, capture đúng job và tách query key theo attempt. R2 xử lý được lỗi poll thông thường nhưng chưa giữ bền bằng chứng job không còn tồn tại.

Kiểm chứng độc lập:

- TypeScript strict và Vite build thành công trong thư mục tạm. SHA-256 của cả ba file build khớp `apps/web/dist` đang được tests sử dụng.
- **46 passed, 0 failed, 0 skipped trong 477.06 giây**, gồm đủ 20 regression tests mới, 13 three-layer tests và 13 regression/workspace cases hiện có.
- Chạy 20 test mới trên bundle trước sửa được lưu sẵn: **15 failed, 5 passed trong 317.38 giây**. Năm ca pass là negative controls/hành vi vốn đúng; không phải mọi test đều cần fail trên baseline.
- Repro bổ sung 404 rồi 500 xác nhận F1 dù toàn bộ 46 tests hiện tại xanh.
- Đã xem trực tiếp năm ảnh R1/R2 desktop/mobile được tạo trong lượt review này.

Trong repository, lượt review chỉ tạo báo cáo này. Không sửa source/tests, commit, push, chạy production server hoặc model inference. Test server dùng registry double, runtime tạm và cổng loopback riêng.

## Kết quả theo checklist

Ký hiệu file dùng trong bảng:

- **I**: [ItemDetail.tsx](F:/DPL_NEU-ESC/apps/web/src/ItemDetail.tsx)
- **S**: [SensitivityPanel.tsx](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx)
- **T**: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py)
- **D**: [test_three_layer_demo.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_demo.py)
- **C**: [styles.css](F:/DPL_NEU-ESC/apps/web/src/styles.css)

`I:168` nghĩa là dòng 168 trong file I. PASS phản ánh code và các đường chạy đã kiểm; không có nghĩa đã kiểm mọi cách xen kẽ request có thể xảy ra.

| # | Mục | Kết quả | Ghi chú |
|---|---|---|---|
| 1 | Không silent rebase nháp dirty | PASS | I:168 chỉ nạp lại task `!dirty`; không gán base mới cho dirty draft. Các phép gán base ở resolve là thao tác explicit; sau save dùng snapshot của request đã lưu. |
| 2 | Tách input conflict và review conflict | PASS | I:251 so revision ID và marker 409; I:261 loại input conflict trước khi xét review revision. Bắt được trường hợp review revision 0/0. |
| 3 | Disabled và guard lưu | PASS | I:332, I:374, I:375 chặn trong handler; I:907 và I:930 khóa hai nút. Guard có thật; cách test guard còn hạn chế ở C1. |
| 4 | Cảnh báo bền qua refetch/reload/poll | PASS | I:116 giữ DetailContent khi có cached item dù refetch lỗi; I:353 ghi marker revision bị từ chối. R1-A/B/H kiểm refetch, reload từ sensitivity và failed refresh. Reload ở đây là tải lại dữ liệu trong app; không phải lưu nháp qua F5/unmount. |
| 5 | Compare UI cũ/mới, responsive | PASS | I:773 dùng `base_text` và `item.text`; C:1781, C:2499 chuyển hai cột thành một cột. Đã xem ảnh 1440x960 và 390x844. |
| 6 | Hai nút resolve đúng semantics | PASS | I:273: discard nạp server review, `dirty=false`; apply giữ nội dung, đổi base, `dirty=true`; không gọi API. R1-D/E assert số PUT và server state. |
| 7 | Provenance confirmed sang corrected | PASS | I:288 đổi confirmed thành corrected; I:295 null source chỉ khi input conflict. R1-F assert API `source_prediction_id is None` và relation `manual`; R1-G bảo vệ nguồn cùng revision. |
| 8 | Conflict lặp khi server đổi lần nữa | PASS | I:344 gửi revision nền của nháp; không retry PUT tự động. R1-H resolve rev2, bị 409 với rev3, rồi phải resolve lần nữa. |
| 9 | Task không dirty nhận revision mới | PASS | I:175 và I:182 nạp review server; R1-B và D:2845 kiểm topic được reset, không conflict. |
| 10 | Conflict độc lập giữa tasks | PASS | Draft/conflict theo `Record<Task,...>`; R1-B lưu topic trong khi sentiment còn conflict; R1-E discard sentiment vẫn giữ topic. Hiện sản phẩm có hai task. |
| 11 | Transport error giữ job active/ID | PASS | S:678 không coi NETWORK_ERROR/5xx là terminal; effect S:692 không xóa ref chỉ vì `isError`. R2-A/B/C kiểm 500/network abort và cancel thật. |
| 12 | Terminal/404 được nhận diện và giữ đúng | FAIL | Status terminal được giữ, nhưng 404 chỉ nằm trong error hiện tại; 500 sau đó làm mất bằng chứng 404 và khôi phục active từ cache queued. F1 đã tái hiện. `interrupted` và `completed_with_errors` cũng là terminal hợp lệ theo kiến trúc. |
| 13 | Đóng panel/unmount gửi cancel | PASS | S:556, S:605, S:735 xử lý details/context/unmount; tests kiểm đúng job và API state. Endpoint đúng là **POST `/jobs/{id}/cancel`**, không phải DELETE, theo contract kiến trúc E2. Cancel thừa sau 404 thuộc F1. |
| 14 | Retry đọc sau transport error | PASS | S:643 retry một lần, dùng backoff mặc định; S:651 dừng interval khi hết retry, UI có “Thử lại”, reconnect có thể refetch. Đây là retry hữu hạn đúng handoff 5.2.4; không phải polling tự động vô hạn sau lỗi. |
| 15 | Retry response stale phải cancel | PASS | S:1072 gọi cancel đúng `updated.id`/target đã capture khi generation đổi, rồi return. R3-A/B/C kiểm request và tác động backend. |
| 16 | Guard chống retry trùng | PASS | S:1047 kiểm ref đồng bộ và state; S:1066 đặt ref trước await. Submit cũng kiểm action busy ở S:870. |
| 17 | Query cache có sequence | PASS | S:637 đưa `retrySeq` vào key; S:1079 tăng sequence sau retry hợp lệ, S:1092 bỏ key cũ. Coverage response GET đến muộn còn hạn chế ở C1. |
| 18 | Đóng panel trong lúc retry | PASS | Cleanup tăng generation; response thành công muộn đi vào S:1072. R3-A/C bao phủ cả request chưa tới server và response bị giữ sau khi server đã retry. |
| 19 | Chất lượng đủ 20 regression tests | CONCERN | Đã đọc và chạy từng test ở bản hiện tại/bundle trước sửa: 15 red/green, 5 controls green/green. DOM `.click()` trên nút disabled chưa chứng minh handler guard; R3-D chưa ép stale GET race. Xem ma trận và C1. |
| 20 | Ma trận tối thiểu R1 | PASS | R1-A: 409/lock; D/E: apply/discard; F: provenance; H: conflict lặp/failed refresh; B: untouched task. Có assertion API/history, không chỉ happy path. |
| 21 | Ma trận R2 | CONCERN | Có poll error, close/cancel, recovery và terminal/404. R2-D kiểm `completed -> 500` nhưng không kiểm `404 -> 500`; F1 lọt qua. |
| 22 | Ma trận R3 | PASS | A/C kiểm close; B kiểm selection/item và job mới không bị hủy nhầm; D kiểm retry hợp lệ không self-cancel; E kiểm lỗi từ chối và nháp còn nguyên. |
| 23 | Contract/provenance trong test cũ | CONCERN | D:2850 đã thêm conflict, lock và explicit apply đúng. Nhưng D:2814 đã đổi sang corrected trước đổi text; cuối test không assert null source. Transition qua resolve được kiểm ở R1-F, không phải test cũ này. Xem C2. |
| 24 | Xác nhận toàn bộ 292 tests | CONCERN | Lượt này xác nhận 46 E2E pass, chưa xác nhận lại 292/3 deselected. Default suite còn synthetic-model inference dù loại `real_model`; không chạy do giới hạn người dùng. Con số 292 là evidence của báo cáo trước. |
| 25 | Không dead/unreachable code | CONCERN | S:717 có guard terminal-to-active không thể tới nhánh return vì S:697 đã return với cùng điều kiện terminal. Không thấy code cũ bị comment out trong phần sửa. Xem C3. |
| 26 | Naming conflict rõ | PASS | I:251/261/271 có semantics đúng: input, review cùng revision, và hợp hai loại. `base_revision` là review revision; `base_input_revision` là input revision. |
| 27 | Type safety | PASS | ReviewDraft/TrackedJobState/ref/state có type, không thêm `any`; strict TypeScript pass. `status: string` nhất quán với Job/SensitivityExperiment hiện có, dù không phải union hẹp. |
| 28 | Race refetch và user action | PASS | Dirty state được giữ bằng functional updater; 409 ghi marker theo revision đã gửi; resolve chờ snapshot mới; backend optimistic guard bảo vệ thay đổi server sau resolve. R1-B/H, R3-A/B/C đã chạy. F1 là ngoại lệ về ghi nhớ outcome của poll. |
| 29 | Cleanup polling/refs | PASS | TanStack quản lý interval; đổi context/unmount bỏ query, tăng generation và cancel; late create/retry bị chặn. Fetch không nhận AbortSignal nên request đã gửi có thể kết thúc sau cleanup, nhưng không có interval sống vô hạn hay kết quả gắn vào panel mới trong các ca đã kiểm. |
| 30 | CSS không phá layout | PASS | Compare grid có `min-width:0`, `white-space:pre-wrap`, `overflow-wrap:anywhere`; breakpoint mobile xếp dọc. Hover primary loại disabled. Ảnh và overflow assertions đều đạt. |
| 31 | Stale closures/dependencies | PASS | Không có `useCallback` trong hai component này. Effect context phụ thuộc item/revision/run/queryClient; async retry giữ reqGen/target riêng và finally kiểm generation trước cập nhật state. |
| 32 | Hai task lưu gần nhau | PASS | UI khóa fieldsets bằng busy; save-next await từng task; cập nhật draft theo key không ghi đè task kia; backend dùng review revision riêng. Không phát hiện regression do delta R1 trong đường lưu bình thường. |
| 33 | base_text rỗng/null | PASS | Contract `Item.text: string`; storage `check_text` từ chối null/blank. Compare render text trực tiếp, không thao tác chuỗi gây crash trên snapshot rỗng. Không có fixture null ngoài contract. |
| 34 | Review revision 0/0 | PASS | I:255 so input revision ID; R1-C kiểm conflict và cả hai nút resolve enabled khi có snapshot mới, không bị mắc ở thông báo đang tải. |
| 35 | Historical stale không ghi | PASS | I:312, I:332, I:372 có guard; fieldset/save-next/history restore bị khóa với `item.stale`. Negative control R1 kiểm historical run. |

### Đối chiếu từng regression test

Tất cả các hàm dưới đây thuộc file **T** và đều **PASS trên bản hiện tại**. Cột baseline là kết quả chạy độc lập trên bundle trước sửa; dòng thất bại là assertion đầu tiên thực tế, không suy diễn rằng các assertion phía sau cũng đã chạy trên baseline.

| Test (tiền tố tên hàm duy nhất, dòng khai báo) | Baseline | Điều thực sự được kiểm / giới hạn |
|---|---|---|
| `test_r1_a_409_revision_conflict...`, T:245 | FAIL tại 306 | 409, snapshot/nháp còn, save/save-next khóa, đúng một PUT, API rev2 chưa có review/history. Baseline không có banner. |
| `test_r1_b_background_refetch...`, T:341 | FAIL tại 400 | Reconnect và sensitivity reload; untouched topic reset; topic lưu được độc lập, sentiment vẫn conflict. |
| `test_r1_c_zero_review_revisions...`, T:468 | FAIL tại 513 | Input khác nhau với review 0/0; compare và resolve buttons dùng được, không nhầm review conflict. |
| `test_r1_d_explicit_apply_draft...`, T:543 | FAIL tại 603 | Apply không PUT; save gửi revision 2/review 0, giữ label/note/null source; kiểm API và chỉ một entry history ở rev2. |
| `test_r1_e_discard_draft...`, T:654 | FAIL tại 723 | Cả hai task dirty; discard sentiment nạp đúng server review, không PUT, giữ conflict/nháp topic. Baseline thiếu conflict topic. |
| `test_r1_f_confirmed_provenance...`, T:753 | FAIL tại 808 | Hai prediction khác input revision; giữ nguồn cũ khi conflict; apply chuyển corrected/null; API và review_relation xác nhận manual. Test dừng sớm ở thiếu banner trên baseline. |
| `test_r1_g_same_input_revision...`, T:855 | PASS | Negative control: review conflict cùng input revision, khác run; apply giữ prediction nguồn cũ và confirmed qua API. |
| `test_r1_h_failed_refetch...`, T:960 | FAIL tại 1030 | Failed GET sau 409 không làm mất nháp; resolve khóa khi chưa có snapshot; thêm rev3 sau resolve phải 409 lại. Baseline fail ở banner, không phải assertion riêng về unmount. |
| `test_r1_negative_control...`, T:1111 | PASS | Lưu confirmed bình thường và historical stale locked; không chấp nhận một fix luôn khóa lưu. |
| `test_r2_a_poll_500_close...`, T:1178 | FAIL tại 1251 | Gated queued/running; GET 500; đóng details/dialog phát cancel, API xác nhận cancelled/cancel_requested. Baseline mất active status trước bước đóng. |
| `test_r2_b_poll_network_abort...`, T:1319 | FAIL tại 1385 | Network abort rồi đổi occurrence/item/revision; đúng job bị cancel, context mới không có result cũ. |
| `test_r2_c_open_panel_poll_error...`, T:1460 | FAIL tại 1538 | Hai GET qua retry, chặn create; manual refetch không tạo job; cancel lỗi rồi thử lại; API cancelled và không cancel thừa khi close. Baseline bật nhầm nút create. |
| `test_r2_d_poll_recovers_terminal...`, T:1594 | FAIL tại 1650 | Recovery completed rồi 500 vẫn unlock; nhánh riêng recovery 404 rồi close. **Không có 404 rồi 500** trước close, nên không bắt F1. |
| `test_r2_negative_control...`, T:1739 | PASS | Hoàn tất tự nhiên không phát cancel khi đóng; chống fix luôn cancel. |
| `test_r3_a_delayed_retry_after_close...`, T:1788 | FAIL tại 1853 | Giữ retry request, đóng details/dialog rồi thả; đợi app cancel và API cancelled. Baseline timeout đợi cancel. |
| `test_r3_b_delayed_retry_after_selection...`, T:1907 | FAIL tại 1972 | Selection đổi; item đổi với job mới đã tạo trước khi response cũ về; cancel đúng job cũ, job mới completed. |
| `test_r3_c_retry_response_delayed...`, T:2046 | FAIL tại 2115 | `route.fetch()` cho server retry, gate chứng minh running; giữ response đến sau cleanup; thả response phải cancel. |
| `test_r3_d_same_generation_retry...`, T:2130 | PASS | Double-click gửi một retry, active UI, create khóa, hoàn tất không self-cancel. Chỉ kiểm terminal cache sẵn có; không giữ/thả GET cũ xuyên retry. |
| `test_r3_e_retry_rejected...`, T:2220 | PASS | Network abort, MODEL_IDENTITY_CHANGED, REVISION_CONFLICT, 404; lỗi hiển thị, không auto-retry, giữ nháp, không attach active job. |
| `test_r1_r2_responsive_keyboard...`, T:2367 | FAIL tại 2411 | Hai viewport, overflow và ảnh; Enter kích hoạt apply/cancel. `.focus()` trực tiếp chưa phải bài kiểm đầy đủ thứ tự Tab. |

Các tests dùng route giữ request/response và cờ worker, kiểm request do app phát rồi mới đọc API độc lập. Những POST/PUT từ HTTP client dùng để dựng trạng thái được phân biệt với hành vi UI. Năm ca baseline pass là hợp lý; không nên sửa chúng chỉ để đạt mục tiêu “20/20 fail trước sửa”.

## Findings

### [FAIL] F1 - [P2] 404 không được ghi nhớ, refetch 500 làm job hết hạn trở thành active

- File: [SensitivityPanel.tsx](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:693).
- Dòng: 667, 678, 693, 706; coverage thiếu tại [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:1689).
- Chi tiết: `isNotFoundError` phụ thuộc vào error hiện tại của query. Khi nhận 404, effect chỉ xóa `activeJobIdRef`, không cập nhật `trackedJob` thành một outcome đã biết là không tồn tại. Cached `exp` và tracked status có thể vẫn là `queued` từ response create. Khi refetch tiếp theo trả 500, `isNotFoundError=false`; cả hai status cached vẫn active nên `confirmedTerminal=false`, nút create khóa lại và effect gán lại job ID đã hết hạn vào ref. Cleanup tiếp đó phát cancel thừa.
- Tác động: trạng thái “kết quả đã hết hạn” bị thay bằng “không đọc được trạng thái”; người dùng không tạo lại trên cùng selection cho tới khi reset context hoặc tải lại thành công. Vi phạm handoff 5.2.1, 5.2.6 và nguyên tắc giữ bằng chứng terminal/không tồn tại. Khẳng định trong báo cáo sửa lỗi dòng 39 rằng terminal/404 đều không bị relock là chưa đúng với 404.
- Đề xuất: lưu outcome `not_found` theo experiment/attempt trong tracking state/ref, dùng outcome đó cho cả active predicate và UI; reset outcome khi create/retry/context mới hợp lệ. Bổ sung ca GET lỗi, GET 404 thật, reconnect GET 500: create vẫn enabled, không có active status và close không cancel. Không để marker cũ lấn át retry của attempt mới.

Repro đã thực chạy bằng test double, production source/build giữ nguyên:

1. Tạo sensitivity experiment; chặn GET bằng 500 để cache còn status từ create.
2. Đợi job terminal qua HTTP client độc lập, cho temporary dataset hết hạn trong **DB test**.
3. Bỏ route lỗi, bấm “Thử lại”; endpoint thật trả 404. Nút chạy mở lại.
4. Cho reconnect refetch GET trả 500; nút chạy khóa lại, trạng thái active và nút hủy xuất hiện.
5. Đóng details; app phát một POST cancel tới job cũ.

```json
{
  "after_real_404_run_enabled": true,
  "after_500_run_enabled": false,
  "after_500_active_status_visible": true,
  "after_500_cancel_enabled": true,
  "cancel_requests_after_close": 1
}
```

Script: [repro_404.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/repro_404.py). Evidence: [repro-404-result.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/repro-404-result.json).

### [CONCERN] C1 - [P3] Một số assertion chưa kiểm được lớp bảo vệ mà tên/comment mô tả

- File: [test_three_layer_review_fixes.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_review_fixes.py:320).
- Dòng: 320, 323, 817, 1045, 2186, 2197.
- Chi tiết: gọi DOM `el.click()` khi nút vẫn disabled bị trình duyệt bỏ qua trước khi handler React chạy. Vì thế các assertion “JS-click no-op” vẫn pass nếu xóa guard bên trong handler nhưng giữ disabled. R3-D có kiểm double-click và cache terminal thông thường, song không giữ một GET cũ rồi thả sau retry; test này pass cả baseline chưa có `retrySeq`, nên chưa chứng minh riêng khả năng chống response cũ. Đây là giới hạn coverage, không phải bằng chứng guard hiện tại sai.
- Đề xuất: thêm ca/harness thực sự gọi action khi conflict, hoặc dùng mutation check để chứng minh bỏ handler guard làm test fail. Với retry, giữ response GET của attempt cũ, retry thành công, thả GET cũ và kiểm active tracking/cancel của attempt mới. Ca 404 rồi 500 cần bổ sung theo F1.

### [CONCERN] C2 - [P3] Test cũ chưa có provenance assertion được yêu cầu

- File: [test_three_layer_demo.py](F:/DPL_NEU-ESC/tests/e2e/test_three_layer_demo.py:2814).
- Dòng: 2814, 2874, 2886, 2889.
- Chi tiết: dù server seed là confirmed, test đã chọn corrected trước khi đổi text; onChange đã null source từ bước đó. Phần cuối chỉ assert status/label/note/topic, không assert `source_prediction_id is None`. Test đã đổi đúng contract explicit resolve, nhưng không kiểm confirmed-to-corrected thông qua resolve như mục 23 mô tả.
- Đề xuất: bổ sung null-source assertion cho test cũ; nếu muốn chính test này bảo vệ transition thì giữ nháp confirmed tới bước apply. Hiện transition đã có assertion API đúng trong test R1-F ở T:841 và T:844, nên đây không phải lỗ hổng provenance của toàn bộ suite.

### [CONCERN] C3 - [P3] Guard terminal-to-active phía sau không thể chạy tới

- File: [SensitivityPanel.tsx](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:717).
- Dòng: 697, 701, 717, 721, 724.
- Chi tiết: effect đã return khi tracked job cùng experiment có status không active tại dòng 701. Không có await hay phép thay đổi tracked ref giữa hai đoạn. Vì vậy điều kiện cùng experiment và `!activeJob(prev.status)` tại dòng 721 không thể đúng khi tới guard thứ hai; nhánh return ở 724 là unreachable. Báo cáo sửa lỗi đang mô tả nhánh này như một lớp bảo vệ hoạt động.
- Đề xuất: gộp logic terminal tracking về một nhánh có thể chạy và bỏ guard dư; khi bổ sung outcome 404 cần kiểm lại tính nhất quán ref/state/cache.

### [PASS] P1 - R1 giữ đúng nền nháp và yêu cầu resolve explicit

- File: [ItemDetail.tsx](F:/DPL_NEU-ESC/apps/web/src/ItemDetail.tsx:168).
- Dòng: 168, 251, 273, 330, 371, 755.
- Chi tiết: không thấy đường effect/render tự nâng base của dirty draft trong delta. Save dùng `base_input_revision`, marker 409 tồn tại khi chưa có snapshot mới; confirmDisplayed không ghi đè nguồn khi conflict. Apply chuyển confirmed sang corrected/null; review conflict cùng revision giữ nguồn hợp lệ. Các ca revision 0/0, độc lập hai task, discard/apply và vòng conflict đã pass.

### [PASS] P2 - Poll transport error thông thường và retry muộn có cleanup đúng

- File: [SensitivityPanel.tsx](F:/DPL_NEU-ESC/apps/web/src/SensitivityPanel.tsx:1046).
- Dòng: 556, 605, 678, 983, 1046, 1072, 1079.
- Chi tiết: GET 500/network không làm mất quyền hủy job còn chưa biết terminal. Retry capture đúng target; nhánh stale gửi cancel sau response, không đọc ref của panel mới. Tests kiểm queued/running, đóng details/dialog, đổi selection/item, response sau cleanup và negative control không self-cancel. Ngoại lệ 404 đã nêu riêng tại F1.

## Kiểm chứng và giới hạn

### Lệnh, kết quả và artifacts

Audit root: [codex-r123-review-374d33b6285e4faab6c45e74aa725c4f](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f).

| Kiểm chứng | Cách chạy | Kết quả |
|---|---|---|
| Strict TypeScript | Tại `F:\DPL_NEU-ESC\apps\web`: `.\node_modules\.bin\tsc.cmd --noEmit` | Exit 0 |
| Build riêng | `.\node_modules\.bin\vite.cmd build --outDir C:\Users\Admin\AppData\Local\Temp\codex-r123-review-374d33b6285e4faab6c45e74aa725c4f\dist` | Exit 0; 86 modules; Vite 4.38s |
| Build/source identity | So SHA-256 index.html, JS, CSS giữa build tạm và dist hiện có | Cả ba khớp |
| Bản hiện tại | `.venv\Scripts\python.exe -B -X utf8 <audit>\run_review_tests.py` | **46 passed in 477.06s**, exit 0 |
| Bundle trước sửa | `.venv\Scripts\python.exe -B -u -X utf8 <audit>\run_baseline_tests.py` | **15 failed, 5 passed in 317.38s**, exit 1 như kỳ vọng đối chứng |
| Repro bổ sung | `.venv\Scripts\python.exe -B -X utf8 <audit>\repro_404.py` | Tái hiện F1; script quan sát kết thúc exit 0 |
| Whitespace tracked delta | `git diff --check` | Exit 0; chỉ có thông báo LF/CRLF của Git |

Wrapper [run_review_tests.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/run_review_tests.py) gọi `pytest.main` với bốn file E2E, `-q -x --tb=short -p no:cacheprovider` và basetemp riêng; chỉ đổi nơi ghi screenshot để không ghi đè ảnh có sẵn. Assertion và source tests giữ nguyên. Log: [e2e-tests.log](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/e2e-tests.log).

Wrapper [run_baseline_tests.py](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/run_baseline_tests.py) chạy đúng 20 tests với `-v --tb=short -p no:cacheprovider`. Browser context phục vụ HTML/JS/CSS từ bundle cũ qua route; API vẫn tới gated test server với runtime riêng. Không thay `apps/web/dist`, không checkout/reset source. Log đầy đủ và assertion đầu tiên của từng failure: [baseline-tests.log](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/baseline-tests.log).

Bundle trước sửa là [neu-review-build-90f078cbd0504625bf385b897f314a46](C:/Users/Admin/AppData/Local/Temp/neu-review-build-90f078cbd0504625bf385b897f314a46), với `index-D9NXQDUL.js` và `index-DA8htggh.css`, khớp tên bundle trước sửa trong báo cáo bàn giao. SHA-256 JS: `74546B0BE8DF98920D392DB57578584C2EE5B074DD9C5B0BBB93C39AFA6BC54A`. Đây là đối chứng trên artifact đã lưu; không phải rebuild từ snapshot source trước sửa. Không dùng HEAD đơn lẻ làm baseline vì HEAD thiếu implementation ba lớp.

Không chạy lại full suite `pytest tests/ -x --timeout=600 -k "not real_model"`: một số default tests trong `tests/inference/test_registry.py` và `tests/inference/test_sensitivity.py` thực thi tiny/random encoder và predict/predict_pair. Loại `real_model` không loại hết inference. Môi trường kiểm chứng cũng không có pytest-timeout trong danh sách plugin; không cài thêm dependency. Vì vậy **292 passed / 3 deselected và real-model acceptance không được xác nhận lại ở lượt này**.

### Kiểm tra trực quan

Đã mở và xem trực tiếp ảnh trong [screenshots của lượt review](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/screenshots): `r1-desktop-conflict.png`, `r1-mobile-conflict.png`, `r1-desktop-after-apply.png`, `r2-desktop-poll-error.png`, `r2-mobile-poll-error.png`. Compare hai cột ở desktop, một cột ở mobile; text và nút xuống dòng trong panel, không thấy tràn ngang. Thông báo chuyển confirmed thành nhãn tự chọn hiển thị trước apply. Khi poll lỗi, nút chạy disabled và nút hủy còn dùng được. Các assertions overflow, focus trực tiếp và Enter trong test cũng pass.

### Định danh source và bảo toàn workspace

Năm file trọng tâm khớp hash trong báo cáo sửa lỗi và giữ nguyên qua lượt review:

| File | SHA-256 |
|---|---|
| I | `80051FAFCFDDF3D243BFDB46BB36454ABB52742F52C63803CB5080953A5AC457` |
| S | `7D7806BEF488116B523E3E3AEC2B5D61FDFE04D6C4645CC97D8FFFA1384649BB` |
| C | `FD21A605A1004AA768A4CC5647EAA852FE245D4A7A670A7774E66BEFDF983155` |
| T | `093F5404484963E86CDC58F4F1F71CB4F138B3997DAE4D9C45117C753A09CC6A` |
| D | `6C8252F3C882AAA3F6A0351635E0F17A4F2B554EF9E2222EBD758E3086EA0FC1` |

Build mới: JS `B5428BCEDDA9C0B2584C4AF86B68C3342A659E6BA6A1DBBBC37647DA3B153BDA`; CSS `2D9D6B1C830C0791BF17F697C1F5D2E83774041CA215A587C2A55C599AEF11AC`; HTML `8F0ECDCF7F1DA45EE8261228F1860F189D17C3DC31210BCCFABE7B167B79F9D0`.

Evidence hash: [source-hashes-before.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/source-hashes-before.json), [build-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-r123-review-374d33b6285e4faab6c45e74aa725c4f/build-verification.json). Tests chỉ sử dụng runtime tạm; không thực hiện kiểm checksum toàn bộ production database/model nên không suy diễn bảo toàn byte-for-byte các artifact ngoài phạm vi đo.

## Tổng kết

- **35 checklist items: 29 PASS / 5 CONCERN / 1 FAIL.** Các CONCERN là mục 19, 21, 23, 24, 25; FAIL là mục 12.
- **Findings chi tiết: 2 PASS / 3 CONCERN / 1 FAIL.** F1 là lỗi chức năng P2; C1-C3 là nhận xét P3 về coverage/maintainability. Việc chưa chạy lại toàn bộ 292 tests được ghi riêng như giới hạn kiểm chứng.
- **Đánh giá tổng thể: REQUEST CHANGES.** Cần sửa việc ghi nhớ 404 và bổ sung regression `404 -> 500 -> close` trước khi chốt R2 đã đạt toàn bộ contract.
- Ưu tiên tiếp theo: xử lý F1 và test đi kèm; bổ sung kiểm guard/GET response cũ trong C1; bổ sung provenance assertion test cũ và bỏ guard dư C2/C3. Không có yêu cầu sửa thêm R1/R3 về chức năng từ bằng chứng đã kiểm trong lượt này.
