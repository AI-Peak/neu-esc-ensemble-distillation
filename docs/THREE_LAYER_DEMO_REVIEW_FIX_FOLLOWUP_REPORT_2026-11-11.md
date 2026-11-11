# Báo cáo Khắc phục Sau Review Độc lập: Demo Webapp Ba Lớp (F1 · C1 · C2 · C3)

> **Correction C1 — 2026-11-11 (sau review vòng 2):** Các kết quả bên dưới là lịch sử của lượt follow-up trước. Hai claim C1 về forced DOM click và stale response đã bị bác bỏ bởi [review vòng 2](THREE_LAYER_DEMO_REVIEW_FIX_CODEX_REVIEW_ROUND2.md): React vẫn chặn callback khi props.disabled=true; route.continue_() chỉ gửi request sau retry và nhận running. Vì vậy các lần pass cũ không chứng minh handler guard hoặc payload attempt cũ. Evidence thay thế, controls và kết quả nghiệm thu mới nằm trong [báo cáo đóng C1](THREE_LAYER_DEMO_C1_CLOSURE_REPORT_2026-11-11.md). Không sửa kết luận của reviewer độc lập.

- **Thời gian hoàn tất:** 2026-11-11, `Asia/Saigon`
- **Workspace:** `F:\DPL_NEU-ESC`, Windows PowerShell, branch `webapp`, HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134` + uncommitted delta
- **Tài liệu review nền:** [`docs/THREE_LAYER_DEMO_REVIEW_FIX_CODEX_REVIEW.md`](THREE_LAYER_DEMO_REVIEW_FIX_CODEX_REVIEW.md)
- **Tài liệu tham chiếu:** [`docs/THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md`](THREE_LAYER_DEMO_REVIEW_FIX_HANDOFF_2026-11-10.md), [`docs/THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md`](THREE_LAYER_DEMO_REVIEW_FIX_REPORT_2026-11-10.md)

---

## 1. Phân quyền và Mô hình Phối hợp Subagent

Trong lượt khắc phục này, **đã kích hoạt native subagent QA/Review** nhằm phân tách rõ trách nhiệm giữa người xây dựng test/kiểm thử và người viết mã nguồn production:

### 1.1. Phân định quyền sở hữu (Ownership)
1. **Gemini chính:**
   - Sở hữu production implementation: [`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx) và các kiểu dữ liệu liên quan.
   - Sở hữu quy trình build (`apps/web/dist`), snapshot trước sửa, báo cáo follow-up và prompt bàn giao cho Codex.
   - Tuyệt đối không sửa các file tests trong thời gian subagent sở hữu chúng.
   - Tự mình thẩm định diff, assertion và chạy lại toàn bộ test suite để nghiệm thu độc lập cuối cùng.
2. **Subagent QA/Review (`QA_Review`, Conversation ID `e4a1bdf0-251f-4de1-8c24-a2679aa35a6d`):**
   - Sở hữu độc quyền các file tests:
     - [`tests/e2e/test_three_layer_review_fixes.py`](../tests/e2e/test_three_layer_review_fixes.py)
     - [`tests/e2e/test_three_layer_demo.py`](../tests/e2e/test_three_layer_demo.py)
   - Thiết kế ca kiểm thử F1 chứng minh lỗi đỏ trên bundle baseline trước sửa.
   - Bổ sung ca kiểm tra handler guard và stale GET response race (C1), bổ sung provenance assertion và flow (C2).
   - Review mã nguồn production theo chế độ chỉ đọc (read-only), không sửa code production.

### 1.2. Mức độ độc lập
- Subagent QA/Review là **reviewer tách khỏi người viết production code** (Gemini chính viết production, subagent review read-only).
- Subagent **không phải là reviewer độc lập của chính các test do mình viết**.
- Toàn bộ kết quả kiểm thử và diff mã nguồn đã được **Gemini chính xác minh lại trực tiếp** (đọc diff chi tiết, chạy độc lập toàn bộ 46 E2E tests).
- **Codex sẽ thực hiện review độc lập vòng hai** đối với cả implementation và test suite.

---

## 2. Chi tiết Xử lý Các Findings Từ Codex Review

### 2.1. Finding F1 (P2) — Ghi nhớ bền vững outcome 404, ngăn relock và cancel thừa sau refetch 500
- **Nguyên nhân tại baseline:**
  `isNotFoundError` chỉ dựa vào `experimentQuery.error` tức thời. Khi nhận 404 thật, effect chỉ gán `activeJobIdRef.current = null` mà không lưu trạng thái kết thúc vào `trackedJob`. Khi một lần refetch tiếp theo gặp lỗi 500, `isNotFoundError` trở thành `false`; cache `queued` từ lúc khởi tạo sống lại, làm `confirmedTerminal = false`, khiến nút tạo thử nghiệm bị khóa lại, thanh trạng thái active và nút hủy xuất hiện, và khi đóng panel/dialog gửi `POST /cancel` thừa tới job đã không còn tồn tại.
- **Bằng chứng ĐỎ (FAIL) trước sửa trên bundle baseline:**
  Subagent QA bổ sung kịch bản 404 -> refetch 500 trong `test_r2_d_poll_recovers_terminal_or_404_and_subsequent_refetch_500_does_not_relock`:
  ```text
  tests\e2e\test_three_layer_review_fixes.py:1752: in test_r2_d_poll_recovers_terminal_or_404_and_subsequent_refetch_500_does_not_relock
      expect(run_btn).to_be_enabled()
  E   AssertionError: Locator expected to be enabled
  E   Actual value: disabled
  ```
- **Giải pháp xử lý trong [`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx):**
  1. Mở rộng `TrackedJobState` với `attempt?: number` nhằm liên kết chặt chẽ trạng thái tracked với số lần thử nghiệm (`retrySeq`).
  2. Phân tách `isQueryNotFound` (lỗi 404 hiện thời) và `isConfirmedNotFound = isQueryNotFound || activeTracked?.status === "not_found"`.
  3. Trong `useEffect`: khi gặp `isQueryNotFound`, ghi nhận bền vững `status: "not_found"` kèm `attempt: retrySeq` vào `trackedJob` và `trackedJobRef`.
  4. `confirmedTerminal` kết hợp `isConfirmedNotFound`, bảo đảm khi đã có bằng chứng 404 thì `isJobActive` luôn là `false` dù query sau đó có trả 500. Nút tạo thử nghiệm luôn mở khóa, không hiển thị `.sensitivity-status`, không hiển thị nút hủy, và `activeJobIdRef.current` giữ `null` nên đóng panel không phát sinh cancel.
  5. Các thao tác tạo mới (`handleSubmit`), thử lại (`handleRetryExperiment`), xem job cũ (`Xem thử nghiệm đang chạy`) và hủy (`handleCancelActive`) đều cập nhật `attempt` tương ứng, ngăn không cho marker 404 cũ lấn át attempt mới.

### 2.2. Concern C1 (P3) — Lịch sử thay đổi; evidence cũ không đủ (xem correction ở đầu báo cáo)
- **Vấn đề tại baseline:**
  1. Các dòng gọi DOM `el.click()` trên nút disabled bị browser tự động nuốt chửng trước khi event tới React handler, nên chưa chứng minh được lớp bảo vệ bên trong handler (`hasConflict`, `item.stale`).
  2. R3-D chỉ kiểm double-click và cache terminal có sẵn, chưa giữ một GET request của attempt cũ và thả sau khi đã retry sang attempt mới.
- **Giải pháp xử lý trong [`tests/e2e/test_three_layer_review_fixes.py`](../tests/e2e/test_three_layer_review_fixes.py):**
  1. Cải tiến assertion kiểm tra handler guard tại các dòng 323, 817, 1045:
     `el.evaluate("el => { el.disabled = false; el.click(); }")`
     **Claim cũ bị bác bỏ:** ~~Bằng cách cưỡng chế bỏ thuộc tính `disabled` ở DOM trước khi click, event được chuyển trực tiếp vào React synthetic event handler.~~ Assertion không có PUT ở phiên bản này chỉ kiểm disabled dispatch, chưa chứng minh guard callback.
  2. Mở rộng `test_r3_d_same_generation_retry_double_click_no_self_cancel_and_stale_cache` (dòng 2205-2270):
     - Giữ 1 request GET đang bay của attempt cũ (attempt 1 đang failed).
     - Thực hiện double-click "Thử lại thử nghiệm" sang attempt mới (attempt 2).
     - Đợi attempt 2 chuyển sang running (gated bởi `gate_lock`), UI hiển thị active tracking của attempt 2.
     - **Correction:** code cũ chỉ giữ request và thả bằng continue_(); chưa chụp response của attempt cũ. Response thực nhận là running của attempt mới.
     - Assertion cũ dự định bảo vệ tracking/cancel của attempt 2, nhưng chưa có bằng chứng payload attempt cũ đã được giao.
     - Mở worker gate: attempt 2 hoàn tất thành công và hiển thị kết quả.

### 2.3. Concern C2 (P3) — Bổ sung Provenance Assertion và Transition trong Test Cũ
- **Vấn đề tại baseline:**
  Trong `tests/e2e/test_three_layer_demo.py::test_t08_current_view_revision_conflict_reload_keeps_review_draft`, test đã chọn corrected trước khi sửa text, và ở cuối test chỉ kiểm tra nhãn/ghi chú mà không assert `source_prediction_id is None`.
- **Giải pháp xử lý trong [`tests/e2e/test_three_layer_demo.py`](../tests/e2e/test_three_layer_demo.py):**
  1. Giữ nháp bắt đầu từ trạng thái `confirmed` với `source_prediction_id: pred["id"]` đã được seed.
  2. Sửa ghi chú để tạo dirty draft nhưng vẫn ở `confirmed`.
  3. Claim lịch sử về forced click `save_sent_btn.evaluate("el => { el.disabled = false; el.click(); }")` không gửi PUT **chưa chứng minh handler guard**. Ca C2 vẫn kiểm transition/provenance; callback coverage được sửa trong lượt đóng C1.
  4. Người dùng click explicit "Áp nháp lên văn bản hiện tại: cảm xúc": chứng minh transition chuyển đổi từ `confirmed` -> `corrected`, nhãn giữ nguyên và xóa `source_prediction_id`.
  5. Lưu thành công và bổ sung assertion:
     `assert saved_item["reviews"]["sentiment"]["source_prediction_id"] is None`.

### 2.4. Concern C3 (P3) — Loại bỏ Guard Không Thể Chạm Tới (Dead Code)
- **Vấn đề tại baseline:**
  Tại `SensitivityPanel.tsx:717-724`, nhánh guard kiểm tra `prev.experimentId === experimentId && !activeJob(prev.status) && activeJob(exp.status)` là dead code vì nhánh `locallyTerminal` ở dòng 697-704 đã return với cùng điều kiện terminal.
- **Giải pháp xử lý trong [`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx):**
  Gộp toàn bộ logic terminal thành một nhánh duy nhất `locallyTerminal` kiểm tra `!activeJob(trackedJobRef.current.status)`. Loại bỏ hoàn toàn khối guard dư thừa ở sau.

### 2.5. Phát hiện và Xử lý Regression Phụ do Subagent QA Tìm Ra
- **Vấn đề phát sinh:**
  Trong lần sửa đầu tiên của Gemini chính, tại nhánh 404 có gọi `queryClient.removeQueries(...)`. Khi component `SensitivityPanel` đang mount với `enabled: experimentId != null`, việc xóa query làm TanStack Query kích hoạt ngay 1 lượt fetch mới để bù cache, dẫn tới request GET thứ 2 tới endpoint 404, vi phạm assertion `assert len(ttl_get_urls) == 1` trong `test_t08_races_cancel_5xx_retry_ttl_pair_invalid_and_locks`.
- **Xử lý:**
  Gemini chính đã loại bỏ `queryClient.removeQueries`. Trạng thái `not_found` đã được bảo vệ hoàn toàn bởi `trackedJob` (`attempt`), `isConfirmedNotFound` và `locallyTerminal`, không cần can thiệp cache TanStack Query, bảo toàn contract dừng polling sau 404.

---

## 3. Bằng chứng Kiểm chứng và Nghiệm thu Cuối cùng

Toàn bộ các bước kiểm chứng được chạy tuần tự, cô lập port và database:

| Kiểm chứng | Lệnh | Kết quả | Ghi chú |
|---|---|---|---|
| Strict TypeScript | `apps/web`: `.\node_modules\.bin\tsc.cmd --noEmit` | **Exit 0** (0 lỗi) | Đạt chuẩn type an toàn |
| Vite Production Build | `apps/web`: `.\node_modules\.bin\vite.cmd build` | **Exit 0** | Sinh ra `index-DfAjhymE.js` (400.60 kB) và `index-D30vz0W7.css` (35.40 kB) |
| Review Fixes Suite (20 tests) | `pytest tests/e2e/test_three_layer_review_fixes.py -q` | **20 passed in 127.35s** | Lịch sử F1/R1-R3; hai claim coverage C1 đã bị bác bỏ ở vòng 2 |
| Three-Layer Demo Suite (13 tests) | `pytest tests/e2e/test_three_layer_demo.py -q` | **13 passed in 118.90s** | Bao gồm C2 (`source_prediction_id is None`) và no 404 retry |
| Regressions & Workspace Suite (13 tests) | `pytest tests/e2e/test_regressions.py tests/e2e/test_workspace.py -q` | **13 passed in 60.92s** | Bảo đảm không có regression ngoài phạm vi ba lớp |
| **Tổng số E2E Tests** | **Toàn bộ 4 files E2E** | **46 passed, 0 failed, 0 skipped (~5.1 phút)** | **100% GREEN** |
| Whitespace & Git Delta | `git diff --check` | **Exit 0** | Không có lỗi trailing whitespace hay định dạng |

---

## 4. Định danh Mã Nguồn và Bàn giao

### Bảng SHA-256 các file trọng tâm sau sửa:

| File | SHA-256 | Trạng thái |
|---|---|---|
| [`apps/web/src/SensitivityPanel.tsx`](../apps/web/src/SensitivityPanel.tsx) | `512FB509291690D9C327CA71AFD6A39086E992E435B22531375B3E2E26564FCF` | Đã sửa F1, C3, attempt tracking |
| [`apps/web/src/ItemDetail.tsx`](../apps/web/src/ItemDetail.tsx) | `80051FAFCFDDF3D243BFDB46BB36454ABB52742F52C63803CB5080953A5AC457` | Giữ nguyên từ lượt review trước |
| [`apps/web/src/styles.css`](../apps/web/src/styles.css) | `FD21A605A1004AA768A4CC5647EAA852FE245D4A7A670A7774E66BEFDF983155` | Giữ nguyên từ lượt review trước |
| [`apps/web/src/types.ts`](../apps/web/src/types.ts) | `6344249FF5D694F45D990A17969236446C78845B2239853F40D46AE6B658D609` | Giữ nguyên từ lượt review trước |
| [`tests/e2e/test_three_layer_review_fixes.py`](../tests/e2e/test_three_layer_review_fixes.py) | `31A2AD439AE3BA6F8A5FEF2534E547D17EEAAD00C2CB376E231DD3C64C19A388` | Lịch sử: F1; hai claim C1 forced click/stale response bị bác bỏ, xem correction |
| [`tests/e2e/test_three_layer_demo.py`](../tests/e2e/test_three_layer_demo.py) | `9263EB82A77459730AB13E0769236178B8A25345042621EB71C2F573C7120DAA` | Bổ sung C2 (transition confirmed->corrected, null source assertion) |
| `apps/web/dist/index.html` | `9006FF034CC7DD659CE3E85A1C7FCD69C18DB08B8D40A05C7C957C8E538D1BA4` | Rebuilt Vite bundle |
| `apps/web/dist/assets/index-D30vz0W7.css` | `2D9D6B1C830C0791BF17F697C1F5D2E83774041CA215A587C2A55C599AEF11AC` | Rebuilt Vite bundle |
| `apps/web/dist/assets/index-DfAjhymE.js` | `B0E9984135F1DAFE41939C254CE19F5A555FB02E0F814E394C08A3C18BCE53A2` | Rebuilt Vite bundle |

Không có thay đổi trong production database, model weights, API endpoints, backend worker hay review policy. Không commit, không push git.

## 5. Correction và evidence thay thế cho C1

- R2-C1a: tests hiện gọi trực tiếp callback onClick lấy từ props React của chính button ở render hiện tại bằng helper test-only `tests/e2e/react_callbacks.py`. Helper fail rõ khi adapter không hỗ trợ, ghi số invocation và giữ props/DOM disabled. Đây là direct callback invocation, không phải synthetic click qua React dispatch. Assertions bảo vệ PUT, navigation, conflict, draft và provenance; positive controls quan sát confirm đổi draft và Save gửi đúng một PUT.
- R2-C1b: permanent R3-D dùng route.fetch() chụp HTTP 200/failed trước retry, giữ response và identity; sau khi worker gated running, fulfill chính snapshot. Test theo dõi đúng request, response.finished(), body failed, UI active/cancel/create lock, không self-cancel và completed sau mở gate.
- Hai mutant frontend nằm ngoài workspace, sao từ toàn bộ frontend working tree hiện tại: bỏ các conflict gates liên quan save gây PUT thứ hai; bỏ riêng confirm conflict gate gây đổi provenance. Control C1b trả running thay snapshot làm assertion delivered=failed fail; đây là control cho scenario, không phải mutation coverage của query isolation.
- Kết quả/logs/hashes cuối cùng: [THREE_LAYER_DEMO_C1_CLOSURE_REPORT_2026-11-11.md](THREE_LAYER_DEMO_C1_CLOSURE_REPORT_2026-11-11.md). Các bảng hash và thời gian ở mục 3–4 phía trên được giữ làm lịch sử, không phải định danh tests sau lượt đóng C1.
