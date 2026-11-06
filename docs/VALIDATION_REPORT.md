# Báo cáo sửa lỗi và validation R1–R8

Ngày 2026-11-06, Windows local, workspace `F:\DPL_NEU-ESC`, HEAD vẫn `c539171`. Đã thực thi `FIX_PROMPT_2026-11-06.md` theo findings trong `REVIEW_2026-11-06.md`. Ba subagent **GPT-6.1 Sol** có ownership riêng: frontend R1/R2/R7; backend R1/R4/R5/R6; ML R3/R8. Hợp đồng nguồn confirmation và base revision của draft được ghi trong `APP_CONTRACT.md` trước khi sửa frontend/backend.

## Kết quả hiện tại

**Đã sửa toàn bộ 8 finding phần mềm. Build frontend pass; full suite cuối: 105 passed, 5 warnings trong 88,79 giây, không skip.** So với bộ 57 ca trước sửa, có thêm 48 ca thực thi (tính các tham số), bao gồm regression cho từng finding và một test bảo vệ runtime khi collect/import API. JUnit: `test-results/validation-2026-11-06.xml`.

Giữ các thay đổi chưa commit; không reset/revert/clean, commit, push hoặc deploy public. Không đổi schema/migration 1, không tạo lại database người dùng. App local cổng 8765 giữ nguyên listener PID **16108** trước/sau kiểm thử; không stop/restart process local như tác dụng phụ của test. API/worker đang chạy vẫn dùng code Python đã nạp trước phiên sửa; cần một lượt restart vận hành có chủ đích để áp dụng backend mới. Bản sửa đã được chạy bằng API/worker và frontend build trong các runtime thử riêng.

**Live inference bằng student ED thật còn chờ artifact.** Đã chạy `scripts/model_status.py --load`: NEU và UIT đều `available=false`, thiếu manifest/bundle trong `runtime/models`. Không tải/train model, không lấy pretrained backbone, synthetic weights hay registry double làm bằng chứng model thật hoạt động. Khi có bundle tin cậy, vẫn phải nghiệm thu reload, latency và luồng import → inference → review → export → restart cho từng profile.

## Bảng xử lý findings

Các đường dẫn dưới đây tương đối với repo. Tên test là bằng chứng có trong full suite cuối.

| Finding | Trạng thái | File sửa chính | Regression chứng minh |
|---|---|---|---|
| R1 | Resolved | `apps/web/src/ItemDetail.tsx`, `types.ts`; `services/api/main.py`; `services/storage/db.py` | API `test_confirmation_note_preserves_explicit_source_from_another_displayed_run`, các case nguồn sai item/revision/schema/label; E2E `test_r1_note_only_across_disagreeing_runs_preserves_confirmation`: run A trung tính, B tích cực, note-only giữ label/source A, explicit reconfirm mới đổi sang B; prediction gốc và history giữ nguyên. |
| R2 | Resolved | `apps/web/src/ItemDetail.tsx`, `styles.css` | E2E `test_r2_two_context_drafts_require_deliberate_resolution`: 2 browser contexts × 409/refetch khi reconnect × sentiment/topic; draft giữ nội dung/base, bấm lưu lại không ghi đè; đối chiếu và chủ động rebase/load server; task còn lại không bị lưu hộ. |
| R3 | Resolved | `services/inference/registry.py` | `test_transient_inference_failure_does_not_poison_registry`; `test_worker_retry_after_transient_failure_with_separate_registries` (4 case: load/inference × RuntimeError/MemoryError), cùng worker/job/bundle, API registry riêng; hash/head/schema hỏng vẫn bị chặn, diagnostics không lưu raw input. |
| R4 | Resolved | `services/worker.py` | `test_bulk_yields_lease_and_resumes_after_repeated_long_quick_jobs`: lease 0,2s, ba quick job 0,35s, bulk tự hoàn tất không duplicate; `test_yield_fences_previous_claim_and_cancel_retry_preserves_committed_rows`; các test cancel trong inference, expired lease và stale worker vẫn pass. |
| R5 | Resolved | `services/storage/db.py` | `test_export_current_and_historical_revisions_have_real_prediction_provenance`: partial, failed, edit-after-run, append-after-run, historical revisions; `selected_run_id` riêng, row model/run chỉ có khi có prediction khớp revision; snapshot bất biến, AI/reference/human riêng, BOM/formula escaping vẫn pass. |
| R6 | Resolved | `services/worker.py`, `services/storage/db.py` | `test_scheduled_cleanup_runs_during_inference_and_backlog` (2 case), TTL ngắn và inference bị chặn, kiểm scheduler thực sự chạy; active job/durable copy được giữ; backup vẫn loại quick payload. |
| R7 | Resolved | `apps/web/src/ImportDataset.tsx` | E2E `test_r7_manual_delimiter_preview_import_and_auto_detect` (Tab/phẩy/chấm phẩy/gạch đứng): auto-detect → chọn thủ công → preview → import; kiểm đúng text/metadata qua API. |
| R8 | Resolved | `scripts/model_oof.py` | `test_recovers_historical_float16_targets` (thứ tự CLI thường/đảo), `test_float32_reconstruction_uses_archived_source_order` với midpoint nhạy thứ tự cộng; sửa target vượt rounding và sai teacher/fold/hash/rows/counts/finite/range đều bị từ chối cho float16/float32. |

R1 thêm trường API tùy chọn `source_prediction_id`, kiểm cùng item/input revision/schema và label khi confirmed; không cần migration. Note-only giữ source của review đã lưu. R2 chỉ nâng base draft khi lưu thành công hoặc người dùng chủ động resolve. R4 nhả lease và trả unfinished job về queued trong cùng transaction commit; claim kế tiếp tăng attempt để fence batch cũ.

CSV thêm `selected_run_id`, `prediction_status`, `prediction_id` và nguồn review theo task. `prediction_status=processed|failed|unprocessed`; dòng chưa có prediction phù hợp không mang run/model cũ. Quick TTL vẫn 15 phút sau terminal; worker kiểm cleanup mỗi 30 giây, gồm khi backlog liên tục và inference dài, bình thường xóa trong tối đa 35 giây sau TTL. SQLite lock contention có thể cộng thời gian busy timeout; xem `BACKEND.md`.

OOF audit không tăng tolerance tùy ý: replay đủ 30 nguồn theo thứ tự archive, softmax/mean float64 → float32 như assembly → dtype lưu float16/float32, rồi so khớp chính xác. Vẫn cần sáu held-out predictions mỗi dòng và toàn bộ kiểm tra provenance cũ. Audit ghi dtype lưu từng task và dtype tensor train float32; promotion float16 không phục hồi precision đã mất.

## Lệnh và bằng chứng đã chạy

Frontend build được chạy **trước full suite cuối**:

```powershell
cd F:\DPL_NEU-ESC\apps\web
npm.cmd run build
cd F:\DPL_NEU-ESC
.\.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=test-results/validation-2026-11-06.xml
.\.venv\Scripts\python.exe -X utf8 scripts/model_status.py --load
git diff --check
```

TypeScript/Vite pass: 84 modules, JS **343,49 kB** (gzip 102,43 kB), CSS **27,97 kB** (gzip 6,51 kB). `git diff --check` pass; các file untracked trong phạm vi sửa cũng được kiểm whitespace bằng no-index và review trực tiếp. Không đổi dependency. Setup/install, pip check, npm audit và số benchmark của lần triển khai trước không được coi là đã chạy lại trong lượt sửa này.

| Nhóm trong full suite cuối | Số ca pass |
|---|---:|
| Inference/artifact/OOF | 50 |
| API/storage | 31 |
| Worker integration | 6 |
| Windows launcher | 1 |
| Backup/restore | 2 |
| Reports | 1 |
| Playwright Chromium | 13 |
| Cô lập runtime mặc định khi import API | 1 |
| **Tổng** | **105** |

Targeted trước tích hợp: backend/worker **37 passed**; inference **50 passed**; E2E hồi quy ban đầu **7 passed**, sau đó thêm hai case topic vào full suite cuối. Đã lưu bằng chứng baseline trong phiên: 11 ca backend mới fail trước sửa; 3 ca ML fail trước sửa (exception lộ text, worker retry không phục hồi, float16 bị từ chối). Không dùng failure selector/harness để tuyên bố đã tái hiện lỗi sản phẩm: các lượt E2E đầu gặp selector label chính xác và trigger refetch không khớp cấu hình production; đã sửa harness dùng role textbox và reconnect thật, sau đó pass.

Review chéo độc lập: frontend phát hiện thêm transient lazy-load poisoning và OOF summation order ở bản sửa đầu; ML đã sửa và thêm regressions. Backend review luồng draft/source frontend, ML review transaction/lease/export/TTL backend; không còn finding chặn trong phạm vi R1–R8. Không mở rộng sang redesign.

## Cô lập test và giới hạn bằng chứng

Mỗi API/worker/browser/lifecycle test dùng runtime tạm và cổng ngẫu nhiên riêng. Khi audit harness cuối phiên, phát hiện import `services.api.main` tự tạo app/Store mặc định trước khi từng test truyền tmp_path. Các lượt trước khi thêm bảo vệ vẫn khởi tạo Store mặc định, có startup migration/cleanup; vì vậy không dùng chúng làm bằng chứng cô lập runtime. Đã thêm `tests/conftest.py` đặt FEEDBACK_RUNTIME vào thư mục tạm **trước test collection**, khôi phục env và cleanup cuối phiên; `test_module_level_app_uses_session_temporary_runtime` chứng minh module-level app không trỏ runtime người dùng. Full suite 105 ca nêu trên chạy sau bản sửa này. Không chủ động sửa/xóa dataset người dùng hoặc dừng process local.

E2E server ghi log riêng trong thư mục pytest và chỉ dừng cây process đã tự tạo còn sống. Windows lifecycle start/stop/recovery chạy trên runtime tạm có dấu cách và cổng riêng. Không gọi start/stop lên `runtime` thật để kiểm thử.

**Test doubles chỉ trong `tests/`**, model ID `TEST-DOUBLE-NOT-A-MODEL`. Random tiny encoder/synthetic OOF chứng minh cơ chế phần mềm, không chứng minh student ED thật hoặc chất lượng AI. Test tokenizer ViSoBERT dùng cache local với encoder ngẫu nhiên; lần chạy này không skip, không tải weights. Production không có fixture switch/fallback model giả.

Đã xem trực tiếp ảnh `test-results/screenshots/r1-preserved-confirmation.png` và `r2-conflict-topic-True.png`, kiểm nhãn/source và các lựa chọn resolve hiển thị rõ. 13 browser tests gồm các luồng desktop/mobile/laptop cũ, import/review/export/restart, missing model trung thực, focus/contrast/overflow, cùng các case R1/R2/R7 mới. Không coi đây là audit WCAG toàn diện. Năm warnings từ Starlette/httpx, SentencePiece và Transformers là cảnh báo dependency hiện có, không làm fail suite.

## Phép đo lưu trữ từ lần triển khai trước

Không chạy lại benchmark trong lượt sửa R1–R8. Giữ số đo trước để tham khảo, không coi là số đo inference hoặc SLA hiện tại.


Chạy `scripts/benchmark_storage.py`, dữ liệu CSV tiếng Việt tự tạo, database tạm. Một lượt đo trên máy này, không phải SLA:

| Dòng | Preview ms | Import ms | Summary ms | Export ms |
|---:|---:|---:|---:|---:|
| 1 | 4,16 | 3,97 | 1,37 | 3,51 |
| 10 | 3,87 | 4,45 | 1,62 | 4,63 |
| 100 | 7,98 | 10,74 | 4,51 | 14,06 |
| 500 | 90,92 | 36,57 | 18,63 | 56,47 |

Peak working set của process benchmark lưu trữ khoảng **25,1 MiB**, RSS cuối khoảng 22,6 MiB. JSON đo nằm ở `runtime/validation/storage-benchmark.json`. Không model nào được load trong phép đo này. Chưa có latency/cold-load/peak RAM của student thật và chưa có căn cứ thay giới hạn 500 dòng hoặc tuyên bố hiệu năng ViSoBERT so với PhoBERT.

## Artifact thật và vận hành

Theo `MODEL_WORKFLOW.md`, cần bundle student ED đã fine-tune có provenance hoặc đủ 30 OOF teacher để audit và khôi phục targets đúng precision trước huấn luyện trên máy phù hợp. Không lấy metrics/report hay backbone cache thay weights đã huấn luyện. Khi có bundle: `model_status.py --load`, benchmark, rồi nghiệm thu luồng thực tế cho NEU/UIT. Phần này còn **pending artifact**, độc lập với 8 lỗi phần mềm đã resolved.

Hợp đồng và hướng dẫn đã cập nhật: `APP_CONTRACT.md`, `BACKEND.md`, `LOCAL_APP.md`, `MODEL_WORKFLOW.md`. Backend mới có hiệu lực sau restart vận hành có chủ đích; kiểm tra process identity do script quản lý và bảo toàn job/dữ liệu trước restart. Phiên sửa này giữ app local đang chạy, không tự commit/push/deploy public.
