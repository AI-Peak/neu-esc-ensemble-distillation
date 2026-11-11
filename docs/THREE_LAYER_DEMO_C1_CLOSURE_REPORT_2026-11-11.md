# Kết quả đóng hai findings C1 sau review vòng 2

**ĐÃ HOÀN TẤT hai findings C1.** Không còn blocker trong Definition of Done của kế hoạch ngày 2026-11-11 (Asia/Saigon). Production giữ nguyên; không commit/push/deploy, không chạy production server hoặc model inference.

## Baseline và bảo toàn workspace

- Workspace: `F:\DPL_NEU-ESC`; branch `webapp`; HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134`. Baseline bao gồm toàn bộ working-tree delta và file untracked, không lấy riêng HEAD.
- Đã đọc kế hoạch, review vòng 2 và follow-up trước edit. Không tìm thấy AGENTS.md áp dụng ở workspace/ancestor. Các hash trọng tâm khởi đầu khớp kế hoạch.
- Audit riêng: [codex-c1-closure-61c42b97388a47c8915119b8926057e3](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3). Lưu branch/HEAD/status, staged và working-tree diff trước sửa, toàn bộ manifest SHA-256 và bản sao nội dung các file liên quan, kể cả file untracked.
- Trong 208 file Git-visible khởi đầu, 205 file giữ nguyên byte; chỉ hai file tests và follow-up report đổi. Thêm helper và báo cáo này. Toàn bộ 35 file dưới apps/services trong manifest giữ nguyên, bao gồm các source untracked. Các delta khác được bảo toàn; branch/HEAD không đổi.
- Evidence: [snapshot trước sửa](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/before), [manifest trước](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/all-source-hashes-before.json), [manifest cuối](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/all-source-hashes-after.json), [đối chiếu bảo toàn](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/preservation-verification.json), [status trước](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/status-before.txt), [status sau](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/status-after.txt), [delta riêng lượt C1](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/c1-closure.delta.diff).

## Các file đã sửa/tạo

| File | Thay đổi |
|---|---|
| `tests/e2e/react_callbacks.py` (mới) | Adapter test-only gọi onClick đang bind trên button hiện tại, assert props/DOM disabled và callback hợp lệ, đếm invocation, không sửa React props/state. |
| `tests/e2e/test_three_layer_review_fixes.py` | R1-A/F/H dùng callback thật, thêm assertions draft/provenance/navigation; positive controls Save/confirm; R3-D chụp và giao snapshot failed thật, theo dõi browser response và cleanup. |
| `tests/e2e/test_three_layer_demo.py` | Thay forced disabled DOM clicks trong ca conflict bằng callback thật, giữ các assertions C2 và thêm kiểm draft/provenance/item. Thêm ROOT vào sys.path để helper import được khi chạy standalone test server. |
| `docs/THREE_LAYER_DEMO_REVIEW_FIX_FOLLOWUP_REPORT_2026-11-11.md` | Thêm correction rõ evidence C1 cũ không đủ, đánh dấu claim lịch sử bị bác bỏ và trỏ đến evidence thay thế. |
| `docs/THREE_LAYER_DEMO_C1_CLOSURE_REPORT_2026-11-11.md` (mới) | Báo cáo kết quả này. |

Không sửa báo cáo review độc lập vòng 1/vòng 2, không sửa production/API/worker/database/CSS/dependencies, không thêm test hook vào sản phẩm.

## Evidence theo finding

| Finding | Scenario và kết quả quan sát | Kết luận |
|---|---|---|
| R2-C1a: 409, đã có snapshot mới (R1-A) | Save và Save & Next vẫn disabled. Gọi từng bound callback đúng một lần; PUT vẫn chỉ là PUT 409 ban đầu; không chuyển item; draft status/label/note và conflict giữ nguyên. | PASS |
| R2-C1a: 409, GET snapshot lỗi (R1-H) | Gọi Save/Save & Next dù UI disabled; không thêm PUT, draft giữ nguyên, conflict còn, apply/discard vẫn disabled; recovery/rev3 flow và save hợp lệ vẫn pass. | PASS |
| R2-C1a: prediction mới, draft còn conflict (R1-F) | Callback confirm được gọi trong conflict; source rev1, label Tích cực, note và banner conflict giữ nguyên, không đổi sang source rev2. Explicit apply vẫn corrected/null provenance và lưu đúng. | PASS |
| R2-C1a: ca demo C2 | Callback Save/Save & Next không PUT/navigate/đổi confirmed draft; explicit apply vẫn chuyển corrected, giữ label/note, API source_prediction_id=null. | PASS |
| Positive confirm | Cùng adapter trên trạng thái hợp lệ đổi unreviewed thành confirmed, label/source đúng prediction rev1. | PASS |
| Positive Save | Cùng adapter gửi đúng một PUT HTTP 200, API lưu note và source_prediction_id đúng. | PASS |
| Mutant save-conflict | Bản sao frontend working tree bỏ conflict gates liên quan trong saveReview, save và task-wide Save & Next; giữ stale/valid. R1-A fail vì PUT tăng 1→2. | Kill đúng hành vi |
| Mutant confirm-conflict | Chỉ bỏ hasConflict gate trong confirmDisplayed; R1-F fail vì source_prediction_id bị đổi sang prediction rev2. | Kill đúng hành vi |
| R2-C1b: R3-D | route.fetch() trước retry chụp HTTP 200/failed, identity đúng experiment/job; double-click chỉ một retry POST; worker gated/server running; fulfill đúng snapshot; đúng request được browser nhận, finished() thành công, body failed bằng toàn bộ snapshot; sau render UI vẫn active/cancel visible/create disabled, 0 cancel; mở gate → API completed/create enabled. | PASS |
| Control scenario C1b | Harness giao running thay snapshot; test fail chính assertion delivered=failed. | Chứng minh scenario; không phải mutation query isolation |

Helper dùng React internals `__reactProps$` của React 19.2.0 đang pin. Nó lấy callback mới tại mỗi lần gọi, không cache closure trước conflict, fail rõ nếu adapter thiếu callback/props. Đây là direct bound callback invocation, không phải synthetic click qua React dispatch. Các button hiện tại là wrapper không dùng event; Save trả void nên kiểm async work bằng request/UI, không dựa vào await callback. Hai frame và một task sau network completion cho continuations/React effects xử lý; C1b không chỉ dựa vào sleep.

Controls kiểm hành vi save-conflict qua các conflict gates kết hợp; không tuyên bố unit isolation từng inner guard khi outer guard return. Control C1b không sửa production. Log control C1b có thông báo asyncio Target closed trong cleanup sau assertion fail; đây không phải nguyên nhân failure.

Evidence mới: [callback và stale payload observations](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/c1-observations.json), [reports đầy đủ lượt cuối](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/final-e2e/reports.jsonl), [diff mutant save](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/mutant-save.diff), [diff mutant confirm](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/mutant-confirm.diff), [manifest bản sao và build mutant](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/mutant-builds.json), [bundle thực phục vụ mutant save](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-save/served-assets.jsonl), [bundle thực phục vụ mutant confirm](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-confirm/served-assets.jsonl). Bản sao frontend có cả implementation untracked, junction chỉ dùng node_modules đã cài; source mutant ở audit, không sửa rồi khôi phục production workspace, không checkout từ HEAD.

## Lệnh và kết quả kiểm chứng

Runtime đều tạm; test server chỉ loopback port riêng và registry doubles hiện có (GatedControlledRegistry/ControlledE2ERegistry/TestOnlyRegistry). Wrapper [run_checks.py](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/run_checks.py) đặt FEEDBACK_RUNTIME trước import, giữ isolation fixtures, redirect basetemp/screenshots, ghi kết quả và stdout theo test; bundle override chỉ dùng cho hai mutant. Lượt final không có bundle override. Không dùng xdist, không inference kể cả synthetic-model inference.

| Kiểm chứng | Exit | Kết quả / thời gian | Log |
|---|---|---|---|
| Targeted batch đầu (debug) | 1 | 4 passed, 1 failed (nhầm schema test R3-D); wrapper 31.66s | [targeted.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/targeted.log) |
| Targeted R3-D/demo sau sửa schema (debug) | 1 | 1 passed, 1 setup error (import helper); wrapper 12.84s | [targeted-c1b-demo.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/targeted-c1b-demo.log) |
| Targeted demo sau sửa import | 0 | 1 passed; wrapper 7.02s | [targeted-demo-fixed.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/targeted-demo-fixed.log) |
| Mutant save | 1 (đúng kỳ vọng) | 1 failed vì PUT thứ hai; 7.76s | [negative-save.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-save.log) |
| Mutant confirm | 1 (đúng kỳ vọng) | 1 failed vì provenance đổi; 16.55s | [negative-confirm.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-confirm.log) |
| Control C1b running body | 1 (đúng kỳ vọng) | 1 failed vì running != failed; 10.17s | [negative-stale-scenario.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-stale-scenario.log) |
| Typecheck | 0 | 6.12s | [typecheck.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/typecheck.log) |
| Build production source ra audit/dist | 0 | 2.94s | [build.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/build.log) |
| Hash fresh dist so dist E2E | 0 | HTML/JS/CSS khớp toàn bộ byte | [build-verification.json](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/build-verification.json) |
| Bốn file E2E bản cuối | 0 | **46 passed in 395.37s (0:06:35); 0 failed, 0 skipped** | [final-e2e.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/final-e2e.log) |
| git diff --check + whitespace cả file untracked sửa/tạo | 0 | Không trailing whitespace; thông báo Git LF/CRLF chỉ là warning | [diff-check.log](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/diff-check.log), [preservation](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/preservation-verification.json) |

Hai lỗi debug do test mới đã được sửa: nhầm field id với experiment_id và thiếu import path khi test server chạy standalone. Không coi các lượt debug lỗi là lượt nghiệm thu xanh; lượt tổng hợp cuối chạy trên phiên bản tests cuối cùng và pass cả 46 ca. Source tests không đổi sau lượt này.

Lệnh chính tại `F:\DPL_NEU-ESC` (wrapper chỉ thêm artifact routing nêu trên):

```powershell
.\.venv\Scripts\python.exe -B -u -X utf8 -m pytest tests/e2e/test_three_layer_review_fixes.py tests/e2e/test_three_layer_demo.py tests/e2e/test_regressions.py tests/e2e/test_workspace.py -q -x --tb=short -p no:cacheprovider
```

Lệnh thực chạy và cấu hình basetemp: [final-e2e/result.json](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/final-e2e/result.json). Lệnh controls và bundle tương ứng: [negative-commands.json](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/negative-commands.json). Tại `apps/web` dùng local `.\node_modules\.bin\tsc.cmd --noEmit` và `.\node_modules\.bin\vite.cmd build --outDir C:\Users\Admin\AppData\Local\Temp\codex-c1-closure-61c42b97388a47c8915119b8926057e3\dist`, không cài package/npx.

| Nhóm cuối | Kết quả |
|---|---|
| `tests/e2e/test_three_layer_review_fixes.py` | 20 passed |
| `tests/e2e/test_three_layer_demo.py` | 13 passed |
| `tests/e2e/test_regressions.py` | 9 passed |
| `tests/e2e/test_workspace.py` | 4 passed |

F1, C2, C3 và TTL regression vẫn giữ assertions và pass trong lượt này; không skip, xóa test hay hạ assertion. Không chạy lại full pytest toàn repository hoặc mở thêm audit R1/R2/R3 ngoài scope C1.

## SHA-256 cuối

| File | SHA-256 |
|---|---|
| `apps/web/src/ItemDetail.tsx` | `80051FAFCFDDF3D243BFDB46BB36454ABB52742F52C63803CB5080953A5AC457` |
| `apps/web/src/SensitivityPanel.tsx` | `512FB509291690D9C327CA71AFD6A39086E992E435B22531375B3E2E26564FCF` |
| `tests/e2e/test_three_layer_review_fixes.py` | `9C12E55AEA05E665657639252026830E25C45E6824B809AFD5C9A0B0540FE416` |
| `tests/e2e/test_three_layer_demo.py` | `713619240C429598C5A7416B8B129B65D820AD12A224C06A7A8E512CFA9F3991` |
| `tests/e2e/react_callbacks.py` | `536B0BC9AA6ABC2CD4D241A09D6DC4C3CA74FFD946A6B34765BF9791E4CB0C49` |
| `docs/THREE_LAYER_DEMO_REVIEW_FIX_FOLLOWUP_REPORT_2026-11-11.md` | `12B002848DEFB0DACBDED45261A97C307395ACEDD74A6C8B511826E1D0E9CBAA` |

Bundle production/E2E giữ nguyên:

- index.html: `9006FF034CC7DD659CE3E85A1C7FCD69C18DB08B8D40A05C7C957C8E538D1BA4`
- index-DfAjhymE.js: `B0E9984135F1DAFE41939C254CE19F5A555FB02E0F814E394C08A3C18BCE53A2`
- index-D30vz0W7.css: `2D9D6B1C830C0791BF17F697C1F5D2E83774041CA215A587C2A55C599AEF11AC`

Manifest cuối trong audit bao gồm hash báo cáo này; không nhúng self-hash trong nội dung báo cáo. Hash của báo cáo review độc lập và kế hoạch cũng giữ nguyên.

## QA độc lập và giới hạn

Dùng đúng một native subagent QA (`/root/c1_qa`), chỉ đọc, không sở hữu/edit tests, không chạy suite nặng hay spawn tiếp. QA đọc kế hoạch/review vòng 2, helper, delta tests so snapshot, positive/negative evidence, mutant diffs/manifests/served assets, kết quả build và bàn giao cuối. Agent chính sở hữu toàn bộ edits và trực tiếp chạy kiểm chứng. Kết luận QA được lưu riêng tại [qa-review.md](C:/Users/Admin/AppData/Local/Temp/codex-c1-closure-61c42b97388a47c8915119b8926057e3/qa-review.md); đây là review độc lập tests/evidence, không gọi tự kiểm của agent chính là review độc lập.

Giới hạn còn lại: adapter phụ thuộc React internals đang pin; khi đổi phiên bản không tương thích test sẽ fail rõ. Controls không đo unit coverage riêng từng inner guard và không chứng minh toàn bộ query isolation bằng mutation. Không kiểm production server/model/database hay full suite ngoài bốn file được giao. Các giới hạn này đã được kế hoạch chấp nhận và không phải blocker C1.

## Definition of Done

- [x] Callback thật được gọi trong các ca C1a; disabled UI được kiểm riêng.
- [x] Positive controls có side effect; hai mutant fail đúng hành vi; cùng tests pass trên production hiện tại.
- [x] R3-D chụp failed trước retry, server running trước delivery, browser nhận failed thật; tracking và completion đúng.
- [x] Đã bỏ forced DOM click claims trong tests; follow-up giữ lịch sử nhưng correction rõ evidence cũ không đủ.
- [x] F1/C2/C3/TTL không mất hoặc nới assertions.
- [x] Bốn file cuối 46 passed, 0 failed/skip; typecheck/build/diff/whitespace đạt.
- [x] Production và các delta ngoài scope được bảo toàn.
- [x] Báo cáo có edits, controls, logs, commands, exit codes, duration, hashes và giới hạn.

**Chốt: ĐÃ HOÀN TẤT hai findings C1. Không còn blocker trong phạm vi kế hoạch.**
