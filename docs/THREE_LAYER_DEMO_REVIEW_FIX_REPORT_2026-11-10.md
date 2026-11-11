# Báo cáo Khắc phục Ba Lỗi Sau Review — Demo Webapp Ba lớp (R1 · R2 · R3)

- **Ngày hoàn tất:** 2026-11-10 / 2026-11-11 (`Asia/Saigon`, workspace `F:\DPL_NEU-ESC`, Windows PowerShell)
- **Branch & Baseline:** `webapp`, `HEAD` `a0cebad8d625c68ca4df755de27a249e2b8ba134` + delta ba lớp M0–M4 chưa commit
- **Tài liệu nhiệm vụ:** [`docs/THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md`](THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md)
- **Tài liệu nền giữ nguyên:** [`docs/VALIDATION_REPORT.md`](VALIDATION_REPORT.md), [`docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md`](WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md), [`PRODUCT.md`](../PRODUCT.md), [`DESIGN.md`](../DESIGN.md), [`docs/LOCAL_APP.md`](LOCAL_APP.md), [`docs/THREE_LAYER_DEMO_RUNBOOK.md`](THREE_LAYER_DEMO_RUNBOOK.md)
- **Trạng thái reviewer độc lập:** **Có** — Subagent [`QA_Review`](conversation://2a1dffea-f03f-4a67-96aa-cb138b0ecd5d) độc lập sở hữu `tests/**`, thực hiện bằng chứng đỏ trước sửa (F1), cập nhật/viết regression tests và thực hiện review read-only toàn bộ production diff (`apps/web/src/ItemDetail.tsx`, `apps/web/src/SensitivityPanel.tsx`, `apps/web/src/styles.css`) với kết quả **PASS (0 finding)**.
- **Trạng thái nghiệm thu R1–R3:** **Đạt cả 3 finding (`R1` · `R2` · `R3`)** trên bản build đóng băng cuối cùng; không `git commit`, không `push`, không deploy, không sửa model/database/policy production.

---

## 1. Chi tiết R1, R2, R3: Nguyên nhân, Hành vi sau sửa & Điểm sửa

### 1.1. R1 (P1) — Nháp rà soát tự rebase sang revision văn bản mới sau conflict/refetch

- **Nguyên nhân ở baseline (`apps/web/src/ItemDetail.tsx`):**
  1. `draftFromReview` và nhánh khởi tạo/cập nhật trong `DetailContent` không lưu số phiên bản văn bản gốc (`base_input_revision`) và nội dung văn bản gốc lúc soạn nháp (`base_text`); nhánh `dirty` khi refetch tự gán lại `base_revision_id = item.revision_id` và `base_revision = 0`.
  2. Khi `revision_id` thay đổi qua background refetch, reload từ `SensitivityPanel` hoặc sau `409 REVISION_CONFLICT`, `useEffect` xóa `error` và toàn bộ trạng thái conflict.
  3. `hasConflict` dựa chủ yếu vào lệch `review.revision`, nên khi cả revision cũ và mới đều chưa có review (`0` vs `0`) không kích hoạt conflict xuyên revision nguồn.
  4. `saveReview` gửi `expected_revision: item.revision` thay vì revision gốc của nháp (`draft.base_input_revision`), khiến lần bấm Lưu tiếp theo gửi đè nhãn cũ lên revision văn bản mới.
  5. Nút resolve bị khóa khi `review.revision` hai phía bằng nhau; handler `confirmDisplayed` và đổi `<select>` không chặn ghi đè khi đang có conflict; `ItemDetail` unmount luôn `<DetailContent>` khi `item.isError` xảy ra trong lúc refetch sau `409`, làm mất nháp đang giữ.
- **Hành vi sau sửa & vị trí mã nguồn ([`apps/web/src/ItemDetail.tsx`](../apps/web/src/ItemDetail.tsx), [`apps/web/src/styles.css`](../apps/web/src/styles.css)):**
  - [`ReviewDraft`](../apps/web/src/ItemDetail.tsx#L25-L35) & [`draftFromReview`](../apps/web/src/ItemDetail.tsx#L67-L80): lưu đủ `base_revision`, `base_revision_id`, `base_input_revision`, `base_text`, `source_prediction_id`, `dirty`.
  - [`ItemDetail`](../apps/web/src/ItemDetail.tsx#L81-L133): khi `!item.data` mới render `ErrorNotice` toàn panel; khi đã có `item.data` luôn giữ `<DetailContent key={`${item.data.id}::${runId}`}>` (kể cả khi `item.isError`), truyền `syncError` và `onRetrySync` để cho phép `"Thử tải bản hiện tại"` mà không mất nháp.
  - [`DetailContent`](../apps/web/src/ItemDetail.tsx#L134-L199): theo dõi `staleSourceRevisions`; `useEffect` (`L168-L199`) chỉ reset tác vụ `!dirty` sang snapshot mới, giữ nguyên mọi trường của nháp `dirty` (kể cả `status`, `label_id`, `note`, `source_prediction_id`, `base_*`) khi input revision đổi hoặc sau refetch/reload.
  - [`hasInputRevisionConflict`](../apps/web/src/ItemDetail.tsx#L251-L258), [`hasNewInputSnapshot`](../apps/web/src/ItemDetail.tsx#L259-L260), [`hasReviewConflict`](../apps/web/src/ItemDetail.tsx#L261-L268), [`hasNewReviewSnapshot`](../apps/web/src/ItemDetail.tsx#L269-L270), [`hasConflict`](../apps/web/src/ItemDetail.tsx#L271-L272): tách rõ xung đột văn bản nguồn (`draft.base_revision_id !== item.revision_id || Boolean(staleSourceRevisions[draft.base_revision_id])`, bắt cả `review.revision 0` vs `0`) khỏi xung đột cùng revision (`REVIEW_CONFLICT`). Khi chưa tải được snapshot revision mới (`!hasNewInputSnapshot`), cảnh báo vẫn khóa lưu và khóa nút resolve cho tới khi tải được snapshot hiện tại.
  - [`resolveConflict`](../apps/web/src/ItemDetail.tsx#L273-L310): có guard kiểm tra snapshot trước khi thực thi; hỗ trợ hai nút riêng từng tác vụ:
    - **Dùng bản hiện tại, bỏ nháp:** nạp review server của revision hiện tại, `dirty = false`, không tự gửi `PUT`.
    - **Áp nháp lên văn bản hiện tại:** cập nhật nền sang revision/review server hiện tại, giữ `dirty = true`, không tự `PUT`. Theo contract provenance Mục 4.4: nếu là xung đột xuyên input revision và nháp đang ở `confirmed` hoặc có `source_prediction_id`, tự động chuyển `status` từ `confirmed` → `corrected` với `source_prediction_id = null` kèm thông báo rõ đây là **nhãn tự chọn**, không gắn nhầm prediction của văn bản cũ; ngược lại, xung đột `REVIEW_CONFLICT` trong cùng input revision vẫn giữ nguyên `source_prediction_id` hợp lệ.
  - [`confirmDisplayed`](../apps/web/src/ItemDetail.tsx#L311-L320), [`saveReview`](../apps/web/src/ItemDetail.tsx#L330-L368), [`save`](../apps/web/src/ItemDetail.tsx#L371-L401): chặn trong handler theo `item.stale` và `hasConflict`; `saveReview` gửi `expected_revision: draft.base_input_revision`; `409 REVISION_CONFLICT` đánh dấu `staleSourceRevisions[sentRevisionId] = true` thay vì tự retry với revision mới; tác vụ không conflict vẫn lưu độc lập; `"Lưu và câu tiếp theo →"` bị khóa nếu có ít nhất một tác vụ invalid hoặc conflict.
  - Giao diện đối chiếu ([`ItemDetail.tsx#L755-L897`](../apps/web/src/ItemDetail.tsx#L755-L897), [`styles.css#L92-L96`](../apps/web/src/styles.css#L92-L96), [`styles.css#L1781-L1804`](../apps/web/src/styles.css#L1781-L1804), [`styles.css#L2499-L2501`](../apps/web/src/styles.css#L2499-L2501)): thêm khối `.review-conflict-compare` hiển thị song song văn bản lúc soạn nháp và văn bản hiện tại (tự xếp 1 cột trên màn hình nhỏ), đồng thời sửa `.primary:hover:not(:disabled)` để nút primary đang khóa không đổi màu hover.

### 1.2. R2 (P2) — Lỗi polling xóa ID job sensitivity chưa kết thúc

- **Nguyên nhân ở baseline (`apps/web/src/SensitivityPanel.tsx`):**
  - Effect đồng bộ theo dõi `experimentQuery.isError` xóa `activeJobIdRef.current = null`; đồng thời `isJobActive` đánh giá lỗi đọc trạng thái thành không active. Do đó khi đóng `<details>`, đóng dialog hoặc đổi item/selection/revision, cleanup không còn `job_id` để gửi `POST /api/v1/jobs/{id}/cancel`, bỏ lại job đang `queued`/`running`, và giao diện mất trạng thái job / cho bấm tạo job mới bất thường.
- **Hành vi sau sửa & vị trí mã nguồn ([`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx)):**
  - [`TrackedJobState`](../apps/web/src/SensitivityPanel.tsx#L35-L40) & [`updateTrackedJob`](../apps/web/src/SensitivityPanel.tsx#L540-L543): lưu trạng thái xác thực gần nhất của job (`experimentId`, `jobId`, `status`, `cancelRequested`) cả trong ref đồng bộ lẫn state React.
  - [`confirmedTerminal`, `isJobActive`, `knownJobId`](../apps/web/src/SensitivityPanel.tsx#L667-L690) & tracking `useEffect` ([`L692-L733`](../apps/web/src/SensitivityPanel.tsx#L692-L733)): tách rõ **lỗi transport/5xx** với **trạng thái terminal/404 xác thực**. Lỗi mạng/5xx giữ nguyên `isJobActive = true` và `activeJobIdRef.current = knownJobId`. Chỉ mở khóa tạo job mới và ngừng active khi nhận `404/NOT_FOUND` xác thực hoặc status terminal xác thực (`completed`, `failed`, `cancelled`, `interrupted`, `completed_with_errors`). Ngược lại, nếu job đã xác nhận terminal/404 trước đó thì lần refetch lỗi sau sẽ không đánh dấu lại thành active hay gửi cancel thừa.
  - [`resetForChange`](../apps/web/src/SensitivityPanel.tsx#L564-L581), context/unmount `useEffect` ([`L583-L624`](../apps/web/src/SensitivityPanel.tsx#L583-L624)), [`handleSubmit`](../apps/web/src/SensitivityPanel.tsx#L865-L981), [`handleCancelActive`](../apps/web/src/SensitivityPanel.tsx#L983-L1044): đóng `<details>`, đóng dialog, đổi selection hoặc chuyển item/run/revision đều gọi best-effort `cancelJob` với `knownJobId`. Khi đang lỗi poll (`experimentQuery.isError && isJobActive`, [`L1320-L1372`](../apps/web/src/SensitivityPanel.tsx#L1320-L1372)), UI giữ đồng thời `ErrorNotice` + nút `"Thử lại"`, giữ nút `"Chạy thử khi bỏ đoạn"` disabled, và giữ `.sensitivity-status` với `"Không đọc được trạng thái thử nghiệm hiện tại"` + nút `"Hủy thử nghiệm"` khả dụng; nếu bấm `"Hủy thử nghiệm"` thủ công gặp lỗi, `actionError` hiển thị thông báo và giữ nút để thử lại.

### 1.3. R3 (P2) — Retry đến muộn sau khi đóng panel/đổi ngữ cảnh không cancel job vừa xếp lại

- **Nguyên nhân ở baseline (`apps/web/src/SensitivityPanel.tsx`):**
  - Trong `handleRetryExperiment`, sau `await retryJob(jobId)`, nhánh `if (reqGen !== generationRef.current) return;` thoát thẳng mà không gọi `cancelJob` lên job vừa được xếp lại (trái ngược với `handleSubmit`).
  - Ngoài ra, query cache theo `experimentId` không có sequence riêng nên response terminal cũ (`failed`) hoặc poll `running` cũ từ query key trước có thể che lấp hoặc ghi đè trạng thái retry mới; và thiếu khóa đồng bộ `actionBusyRef` dễ gây gửi trùng khi double-click nhanh.
- **Hành vi sau sửa & vị trí mã nguồn ([`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx)):**
  - [`handleRetryExperiment`](../apps/web/src/SensitivityPanel.tsx#L1046-L1114): dùng guard đồng bộ `actionBusyRef.current` / `submittingRef.current` ngăn double-click và cạnh tranh submit. Capture sẵn `reqGen`, `retryExperimentId`, `oldExpKey` và `targetJobId` trong closure.
  - Khi `retryJob(targetJobId)` resolve mà `reqGen !== generationRef.current`: lấy `cancelTargetId = updated?.id || targetJobId` (không đọc `activeJobIdRef.current` của ngữ cảnh mới) và gửi best-effort `cancelJob(cancelTargetId)` nếu job còn active hoặc chưa rõ trạng thái, sau đó return mà không cập nhật state/query/ref của panel mới.
  - Khi `reqGen === generationRef.current`: tăng `retrySeqRef.current` / `retrySeq` làm khóa tách biệt cho `experimentQuery`, cập nhật `trackedJob` & `activeJobIdRef`, xóa `oldExpKey` để response `"failed"` cached cũ không lấn át retry mới; kết hợp chặn hạ cấp trạng thái tại `L717-L725`.
  - Lỗi từ chối hợp lệ (`MODEL_IDENTITY_CHANGED`, `REVISION_CONFLICT`, `JOB_NOT_RETRYABLE`, `404`, lỗi mạng) hiển thị `actionError`, không tạo vòng retry tự động và không làm mất nháp rà soát ở `ItemDetail`.

---

## 2. Phạm vi thay đổi so với baseline chưa commit ban đầu

Thống kê dưới đây tách biệt phần **khắc phục R1–R3** khỏi delta triển khai ba lớp M0–M4 vốn đã tồn tại trước khi bắt đầu (`baseline snapshot` lưu trong audit scratch `baseline/`):

| File | Trạng thái git | Thay đổi R1–R3 so với baseline trước sửa | Phạm vi |
|---|---|---|---|
| [`apps/web/src/ItemDetail.tsx`](../apps/web/src/ItemDetail.tsx) | Tracked (`M`) | `1,045` → `1,226` dòng (**`+257 / -76`**) | R1 (draft base revision/text snapshot, syncError không unmount, cross-revision compare & provenance) |
| [`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx) | Untracked (`??`) | `1,479` → `1,706` dòng (**`+285 / -58`**) | R2 (tách poll error khỏi terminal, giữ `knownJobId` & cancel), R3 (`handleRetryExperiment` delayed cancel, `retrySeq`, anti-double-click) |
| [`apps/web/src/styles.css`](../apps/web/src/styles.css) | Tracked (`M`) | `2,503` → `2,530` dòng (**`+28 / -1`**) | `.primary:hover:not(:disabled)` + `.review-conflict-compare` responsive desktop/mobile |
| [`tests/e2e/test_three_layer_demo.py`](../tests/e2e/test_three_layer_demo.py) | Untracked (`??`) | `2,982` → `3,019` dòng (**`+41 / -4`**) | Cập nhật contract hàm `test_t08_current_view_revision_conflict_reload_keeps_review_draft` (`L2762–2895`) theo Mục 4.5 |
| [`tests/e2e/test_three_layer_review_fixes.py`](../tests/e2e/test_three_layer_review_fixes.py) | Untracked mới (`??`) | **`2,521` dòng mới** | `GatedControlledRegistry` + **20 ca E2E Playwright** phủ toàn bộ ma trận R1–R3, negative controls & responsive/keyboard |
| [`docs/THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md`](THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md) | Untracked mới (`??`) | File báo cáo này | Báo cáo F5 sau sửa |
| `apps/web/dist/*` | Build artifact | Rebuild từ source cuối | `index.html`, `assets/index-C01NbrIq.js`, `assets/index-D30vz0W7.css` (thay thế `index-D9NXQDUL.js` / `index-DA8htggh.css` của bản trước sửa) |

Không có bất kỳ chỉnh sửa nào trong `services/**`, `scripts/**`, `demo/**`, `runtime/**`, `services/review_policy.json`, schema nhãn hay tests backend.

---

## 3. Ma trận Regression (Đỏ trước sửa → Xanh sau sửa) & Cập nhật Contract Test cũ

Toàn bộ 20 test trong [`tests/e2e/test_three_layer_review_fixes.py`](../tests/e2e/test_three_layer_review_fixes.py) dùng `GatedControlledRegistry` (kế thừa [`ControlledE2ERegistry`](../tests/e2e/test_three_layer_demo.py) với cờ đồng bộ file `pair_gate.lock`, `pair_entered.flag`, `pair_fail_once.flag`, `model_identity_v2.flag`) và kiểm tra trạng thái bền qua API + DB độc lập (`GET /items/{id}`, `GET /jobs/{id}`, theo dõi `PUT`/`POST /cancel`), chỉ whitelist đúng mã HTTP của fault injection trong từng test.

- **Bằng chứng đỏ F1 trên bản build gốc chưa sửa** (`task-95`: `.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_three_layer_review_fixes.py -v --tb=short`): **15 failed, 5 passed in 271.73s (`0:04:31`)** *(lượt đầu `task-45` là `16 failed, 4 passed in 312.63s` trước khi QA sửa selector `to_be_disabled()` trên `<fieldset>` ở `test_r1_negative_control`)*. Toàn bộ 15 ca regression R1/R2/R3 đều fail đúng lỗi gốc; toàn bộ 5 ca negative control / hành vi cùng revision giữ nguyên pass trên baseline.
- **Kết quả sau sửa trên bản build đóng băng cuối** (trong Full Default Suite `task-241` và targeted `task-194`): **20/20 passed (`0` failed, `0` skipped)**.

| Ca / Hàm kiểm thử | Mục | F1 trên Baseline | Lý do fail F1 (ngắn gọn) | Bản cuối (F3/F4) |
|---|---|---|---|---|
| `test_r1_a_409_revision_conflict_preserves_draft_blocks_save_and_prevents_silent_rebase` | R1-A | **FAIL** | Silent rebase xóa `review-conflict-sentiment` sau 409 + refetch | **PASS** |
| `test_r1_b_background_refetch_and_sensitivity_reload_conflict_with_independent_tasks` | R1-B | **FAIL** | Background refetch & sensitivity reload không hiện conflict xuyên revision | **PASS** |
| `test_r1_c_zero_review_revisions_input_conflict_enables_resolve_buttons` | R1-C | **FAIL** | Hai review revision `0` vs `0` không bật conflict và nút resolve | **PASS** |
| `test_r1_d_explicit_apply_draft_then_save_updates_only_resolved_task` | R1-D | **FAIL** | Không có conflict & nút áp nháp explicit trước khi Lưu | **PASS** |
| `test_r1_e_discard_draft_loads_new_revision_server_review_without_saving` | R1-E | **FAIL** | Hiển thị nhầm thông báo review conflict hoặc không giữ/bỏ nháp xuyên rev đúng contract | **PASS** |
| `test_r1_f_confirmed_provenance_cleared_on_cross_revision_apply_and_confirm_locked` | R1-F | **FAIL** | Đem nhầm `source_prediction_id` của rev 1 sau reload sang rev 2 | **PASS** |
| `test_r1_g_same_input_revision_review_conflict_preserves_confirmed_provenance` | R1-G | PASS | Hành vi cùng revision đúng sẵn ở baseline (bảo vệ không regress) | **PASS** |
| `test_r1_h_failed_refetch_after_409_and_rev3_after_resolve_keep_lock` | R1-H | **FAIL** | `ItemDetail` unmount `<DetailContent>` khi refetch 500 làm mất nháp | **PASS** |
| `test_r1_negative_control_clean_save_and_historical_stale_locked` | NC-R1 | PASS | Negative control lưu sạch không xung đột & khóa historical `stale=true` | **PASS** |
| `test_r2_a_poll_500_close_details_and_dialog_cancels_active_job` | R2-A | **FAIL** | Poll 500 xóa `activeJobIdRef` → đóng panel phát `0` cancel, `.sensitivity-status` biến mất | **PASS** |
| `test_r2_b_poll_network_abort_context_switch_cancels_and_isolates` | R2-B | **FAIL** | Poll network abort xóa ID job → đổi selection/item không gửi cancel | **PASS** |
| `test_r2_c_open_panel_poll_error_retry_and_manual_cancel_with_error_recovery` | R2-C | **FAIL** | Khi poll lỗi vẫn mở lại nút `"Chạy thử khi bỏ đoạn"` (enabled) thay vì khóa & giữ Hủy | **PASS** |
| `test_r2_d_poll_recovers_terminal_or_404_and_subsequent_refetch_500_does_not_relock` | R2-D | **FAIL** | Không hiển thị `.sensitivity-status` đang active trong lúc poll 500 trước khi recover | **PASS** |
| `test_r2_negative_control_normal_sensitivity_completes_without_spurious_cancel` | NC-R2 | PASS | Negative control hoàn tất bình thường không phát cancel nhầm | **PASS** |
| `test_r3_a_delayed_retry_after_close_details_and_close_dialog_cancels_job` | R3-A | **FAIL** | Delayed retry trả 200 sau khi đóng `<details>`/dialog không gửi cancel (`timeout`) | **PASS** |
| `test_r3_b_delayed_retry_after_selection_and_item_switch_isolates_new_panel` | R3-B | **FAIL** | Delayed retry trả 200 sau đổi selection/item không cancel job vừa xếp lại | **PASS** |
| `test_r3_c_retry_response_delayed_after_cleanup_cancels_safely` | R3-C | **FAIL** | Response retry giữ sau cleanup không gửi cancel bù | **PASS** |
| `test_r3_d_same_generation_retry_double_click_no_self_cancel_and_stale_cache` | R3-D | PASS | Negative control retry cùng generation hoàn tất sạch (mở rộng guard double-click + stale cache) | **PASS** |
| `test_r3_e_retry_rejected_by_model_revision_404_network_keeps_review_draft` | R3-E | PASS | Negative control lỗi retry hợp lệ không vòng lặp & giữ nháp rà soát | **PASS** |
| `test_r1_r2_responsive_keyboard_and_screenshots` | UX/A11y | **FAIL** | Không có UI conflict xuyên revision nên `expect(conflict).to_be_visible()` fail | **PASS** |

### Cập nhật Contract cho test cũ ([`tests/e2e/test_three_layer_demo.py#L2762-L2895`](../tests/e2e/test_three_layer_demo.py#L2762-L2895))

- **Hàm:** `test_t08_current_view_revision_conflict_reload_keeps_review_draft`
- **Vì sao phải cập nhật (theo Handoff Mục 4.5):**
  - Ở bản baseline (dòng `2841–2852`), test chỉ đúng ở chỗ giữ nháp `sentiment` và reset tác vụ `topic` không dirty khi tải lại từ rev 1 sang rev 2, nhưng lại assert `review-conflict-sentiment == 0` và bấm `"Lưu cảm xúc"` trực tiếp lên rev 2 — chính là hành vi sai gây bug R1.
  - Đã giữ nguyên mọi kiểm tra bảo toàn nháp và reset `topic`, đồng thời thay phần assert lưu thẳng bằng: (1) xác nhận `review-conflict-sentiment` hiển thị với thông tin rev 1 / rev 2 và đối chiếu text cũ/mới; (2) khóa cả nút Lưu riêng lẻ và nút Lưu & câu tiếp theo (JS click cũng không phát `PUT`, API vẫn trả `reviews.sentiment == None`); (3) bấm nút `"Áp nháp lên văn bản hiện tại: cảm xúc"` không phát `PUT` và vẫn giữ nháp; (4) bấm `"Lưu cảm xúc"` lưu thành công trên rev 2 với đầy đủ giá trị mong đợi qua API.

---

## 4. Lệnh thực chạy, kết quả kiểm chứng & đối chiếu trực quan

Mọi lệnh đều dùng `.venv` trên Windows với runtime tạm, cổng loopback riêng, không dùng `pytest-xdist`.

### 4.1. Thứ tự lệnh trước và sau build đóng băng cuối

| Giai đoạn | Lệnh thực chạy | Kết quả chính xác | Nguồn dữ liệu / Test Double | Ghi chú / Log ID |
|---|---|---|---|---|
| **F1 (Red Baseline)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_three_layer_review_fixes.py -v --tb=short` | **15 failed, 5 passed** trong `271.73s` (`0:04:31`, exit `1`) | Software double `GatedControlledRegistry` trên build gốc | `QA_Review` `task-95` *(lượt `task-45`: 16F/4P trước khi chỉnh selector `<fieldset>`)* |
| **F2 Interim (trước polish CSS & screenshot)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_three_layer_review_fixes.py -v --tb=short` | **20 passed** trong `165.60s` (`0:02:45`, exit `0`) | Software double `GatedControlledRegistry` | `task-194` (trước sửa `.primary:hover:not(:disabled)` trong `styles.css`) |
| **F2 Interim (trước polish CSS & screenshot)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_three_layer_demo.py -q` | **13 passed** trong `152.95s` (`0:02:32`, exit `0`) | Software double `ControlledE2ERegistry` | `task-201` (trước sửa `.primary:hover:not(:disabled)` trong `styles.css`) |
| **F3 Final Build** | `Set-Location 'F:\DPL_NEU-ESC\apps\web'; npm.cmd run build` | **Exit `0`**, `tsc -b` + `vite build` 86 modules trong `4.19s` | Frontend production bundle đóng băng | `task-218` (trước toàn bộ các lượt F3/F4 cuối dưới đây) |
| **F3 Targeted Regressions (Final Build)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest tests/e2e/test_regressions.py tests/e2e/test_workspace.py -q --tb=short` | **13 passed** trong `84.48s` (`0:01:24`, exit `0`) | Software double `TestOnlyRegistry` | `task-224` (chạy trên build cuối `task-218`) |
| **F4 Full Default Suite (Final Build)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest -q` | **292 passed, 0 failed, 0 skipped, 3 deselected**, 22 warnings trong `490.13s` (`0:08:10`, exit `0`) | Software double + unit/API/worker/synthetic | `task-241` — bao gồm đầy đủ 20 ca `test_three_layer_review_fixes.py` + 13 ca `test_three_layer_demo.py` + 13 ca `test_regressions/test_workspace` trên build cuối `task-218` |
| **F4 Real-Model Suite (Final Build, Lần chốt)** | `.\.venv\Scripts\python.exe -B -X utf8 -m pytest -m real_model -q` | **3 passed, 292 deselected**, 3 warnings trong `178.34s` (`0:02:58`, exit `0`) | **Model thật offline** (`neu-phobert-mtl-ed-s42-e10-617f852a3fff` từ copy runtime tạm) | `task-325` *(xem Mục 6 về flake nền có sẵn ở `task-250` & `task-282`)* |
| **Kiểm vệ sinh diff & untracked** | `git diff --check` + kiểm trailing whitespace file untracked bằng Python | **Exit `0`**, `ISSUES: []` | Source & tests | Thực hiện lại sau khi thêm báo cáo này |

*(Ghi chú: 22 warnings ở default suite và 3 warnings ở real-model suite là `StarletteDeprecationWarning`, `SwigPy*` và `Transformers` `clean_up_tokenization_spaces` — đều là cảnh báo thư viện sẵn có, giống báo cáo trước sửa.)*

### 4.2. Kiểm tra trực quan ảnh chụp màn hình (trên build đóng băng cuối)

Toàn bộ 5 ảnh R1/R2 được tạo bởi `test_r1_r2_responsive_keyboard_and_screenshots` trong lượt `task-241` (trên build đóng băng `task-218`) và đã mở kiểm trực tiếp:

- [`test-results/screenshots/r1-desktop-conflict.png`](../test-results/screenshots/r1-desktop-conflict.png) (`1440×960`): Nháp `confirmed` (nhãn `Tích cực`, `Prediction nguồn`, ghi chú có focus ring bàn phím rõ) được giữ nguyên; hộp cảnh báo `Văn bản nguồn đã thay đổi — nháp cảm xúc thuộc phiên bản 1.` xếp 2 cột đối chiếu văn bản rev 1 / rev 2 cân đối, giải thích rõ chuyển sang `Tự chọn / sửa nhãn` khi áp, hai nút `"Dùng bản hiện tại, bỏ nháp"` & `"Áp nháp lên văn bản hiện tại"` đầy đủ nhãn, nút `"Lưu cảm xúc"` khóa rõ trạng thái disabled.
- [`test-results/screenshots/r1-desktop-after-apply.png`](../test-results/screenshots/r1-desktop-after-apply.png) (`1440×960`): Sau khi bấm phím `Enter` vào `"Áp nháp lên văn bản hiện tại: cảm xúc"`, cảnh báo biến mất, trạng thái chuyển đúng thành `Tự chọn / sửa nhãn` với nhãn `Tích cực` và ghi chú giữ nguyên, `"Lưu cảm xúc"` và `"Lưu và câu tiếp theo →"` mở khóa bình thường, không tràn.
- [`test-results/screenshots/r1-mobile-conflict.png`](../test-results/screenshots/r1-mobile-conflict.png) (`390×844`): `.review-conflict-compare` xếp 1 cột dọc sạch, chữ xuống dòng gọn gàng (`overflow-wrap: anywhere`), nút bấm xếp dọc rõ ràng, `scrollWidth <= clientWidth + 1`.
- [`test-results/screenshots/r2-desktop-poll-error.png`](../test-results/screenshots/r2-desktop-poll-error.png) (`1440×960`) & [`test-results/screenshots/r2-mobile-poll-error.png`](../test-results/screenshots/r2-mobile-poll-error.png) (`390×844`): Khi polling gặp GET 500, nút `"Chạy thử khi bỏ đoạn"` giữ trạng thái disabled (hover không bị tối màu), `ErrorNotice` hiển thị `"Lỗi 500 giả lập kiểm tra giao diện."` + nút `"Thử lại"`, bên dưới vẫn giữ hộp `.sensitivity-status` với `"Không đọc được trạng thái thử nghiệm hiện tại"` và nút `"Hủy thử nghiệm"` đang bật, không tràn ngang ở cả desktop lẫn mobile.

---

## 5. Checksum SHA-256 cuối & Bảo toàn dữ liệu Production

Tất cả hash dưới đây được đo trực tiếp bằng `Get-FileHash -Algorithm SHA256` sau khi chốt build & tests cuối cùng:

### 5.1. File mã nguồn, build frontend và tests trong phạm vi R1–R3

| File | Kích thước (bytes) | SHA-256 |
|---|---:|---|
| `apps/web/src/ItemDetail.tsx` | `46,217` | `80051FAFCFDDF3D243BFDB46BB36454ABB52742F52C63803CB5080953A5AC457` |
| `apps/web/src/SensitivityPanel.tsx` | `55,581` | `7D7806BEF488116B523E3E3AEC2B5D61FDFE04D6C4645CC97D8FFFA1384649BB` |
| `apps/web/src/styles.css` | `45,247` | `FD21A605A1004AA768A4CC5647EAA852FE245D4A7A670A7774E66BEFDF983155` |
| `apps/web/dist/index.html` | `470` | `8F0ECDCF7F1DA45EE8261228F1860F189D17C3DC31210BCCFABE7B167B79F9D0` |
| `apps/web/dist/assets/index-C01NbrIq.js` | `400,245` | `B5428BCEDDA9C0B2584C4AF86B68C3342A659E6BA6A1DBBBC37647DA3B153BDA` |
| `apps/web/dist/assets/index-D30vz0W7.css` | `35,401` | `2D9D6B1C830C0791BF17F697C1F5D2E83774041CA215A587C2A55C599AEF11AC` |
| `tests/e2e/test_three_layer_demo.py` | `139,660` | `6C8252F3C882AAA3F6A0351635E0F17A4F2B554EF9E2222EBD758E3086EA0FC1` |
| `tests/e2e/test_three_layer_review_fixes.py` | `100,653` | `093F5404484963E86CDC58F4F1F71CB4F138B3997DAE4D9C45117C753A09CC6A` |

### 5.2. Kiểm bảo toàn Model, Database, Backend & Fixtures

Đối chiếu lại SHA-256 trên workspace cho thấy toàn bộ thành phần production và backend/fixtures **giữ nguyên 100%, không bị sửa hoặc ghi đè**:

- `demo/model.pt`: `754892A782DEC389B041ABC5F923573C091B8E2801DD0F7BE57F718AE88700A8` (khớp `VALIDATION_REPORT.md`)
- `runtime/workspace.sqlite3`: `C5A6A87A1D1B873654F52239298255B54EAAA66E1D6987A4B7D86C2ED612DFE6`
- `runtime/models/neu/current.json`: `887BB18A2860A1D9387D8B21384BCFE76BDD80CDF07639EAEDEA0D849960220B` (khớp `VALIDATION_REPORT.md`)
- `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff/manifest.json`: `5117B413D141D4E6B80A2805B9B5FF27B353D404D3A42BC95C29055E4F527B1D` (khớp `VALIDATION_REPORT.md`)
- `services/review_policy.json`: `2D1CD5D7AF32168AF6C6AE30AF6B1C43BA9F7C2F1CD6D73CC221067D1A1FC9A6` (khớp `VALIDATION_REPORT.md`)
- `services/api/main.py`: `BDE79FFD2482229A645434A83949C64357EFF5CA4B5689AF81CAB050151DE05D`
- `services/storage/db.py`: `E2E44BC94ACB29D598EE21787972E25D543B8BA425C7CA88166C679C9E238647`
- `services/worker.py`: `5BAD6A06538FB1628248C2612999AFE93E4250A2A59F4F33FF8BAB7E76707E95`
- `services/inference/registry.py`: `C200CBBE010A78FABA9A422F9DABC35CCBE042FD314C9C51CFAC8F7B0A791D28`
- `tests/conftest.py`: `D5C22AED13C04A0CAD4248386A60016F4BAB178B2C8E0C9A5EC006A30AC8D3E7` (khớp hash handoff)
- `tests/e2e/conftest.py`: `2D85876DC32FF7EED8527F21E1665D181C384AB267B93E19B4EC0C32FEE2B0FA` (khớp hash handoff)

---

## 6. Findings còn mở, Giới hạn & Ghi nhận minh bạch

- **Reviewer độc lập:** **Có** — [`QA_Review`](conversation://2a1dffea-f03f-4a67-96aa-cb138b0ecd5d) review read-only bản sửa cuối ở frontend + diff và chạy bằng chứng F1 ban đầu; mọi chỉnh sửa trên production frontend do agent điều phối thực hiện tách biệt ownership file với QA.
- **Không còn defect mở thuộc R1, R2, R3.**
- **Hai giới hạn & hiện tượng nền cần nêu trung thực:**
  1. **Flake nền không ổn định thời gian ở bài kiểm thử `real_model` có sẵn ([`tests/inference/test_three_layer_real_model.py#L750-L797`](../tests/inference/test_three_layer_real_model.py#L750-L797), dòng `906`):** Trong lúc chuyển giữa server `run1` và `run2`, test giữ trang desktop mở trên origin cũ của `run1` đã bị tắt ~4,5 giây trong khi khởi động `run2` và kiểm mobile context; truy vấn `/api/v1/profiles` định kỳ mỗi 15 giây trong [`apps/web/src/App.tsx#L19-L23`](../apps/web/src/App.tsx#L19-L23) thỉnh thoảng rơi đúng vào cửa sổ đó và sinh `net::ERR_CONNECTION_REFUSED`. Hai lượt chạy trung gian `task-250` và `task-282` gặp đúng lỗi này (`1 failed, 2 passed`), trước khi lượt kiểm tra chẩn đoán (`task-317`: `3 passed`) và **lượt chạy chuẩn không wrapper cuối cùng (`task-325`: `3 passed, 292 deselected in 178.34s`)** đều pass sạch. Do `App.tsx` và `test_three_layer_real_model.py` nằm ngoài phạm vi R1–R3, hai file này được giữ nguyên và hiện tượng timing nền được ghi nhận minh bạch tại đây.
  2. **Giới hạn mạng best-effort khi request retry chưa nhận HTTP response (`R3`, Mục 6.2.2):** Nếu tab/ứng dụng bị đóng hẳn ở mức tiến trình/OS hoặc mất mạng trước khi trình duyệt nhận response `200` từ `POST /jobs/{id}/retry`, frontend không còn ngữ cảnh nhận response để phát cancel bù; các cơ chế lease/attempt fencing và TTL ở backend tiếp tục giữ vai trò lớp phòng vệ cuối cùng.
