# Prompt thực thi sửa lỗi sau review

Dán phần nội dung từ câu tiếp theo vào chat mới, workspace `F:\DPL_NEU-ESC`.

Bạn tiếp quản web app Feedback Workspace tại `F:\DPL_NEU-ESC` để **sửa các lỗi đã được review và tái hiện**, kiểm thử lại, rồi bàn giao. Hãy thực hiện code; không dừng ở kế hoạch hoặc chỉ giải thích.

## 1. Ngữ cảnh cần đọc

Đọc theo thứ tự:

1. `docs/REVIEW_2026-11-06.md` — nguồn chính: 8 finding R1–R8, vị trí, trigger, reproduction và tiêu chí sửa.
2. `docs/APP_CONTRACT.md`, `docs/BACKEND.md` — hợp đồng hiện tại.
3. `docs/VALIDATION_REPORT.md`, `docs/LOCAL_APP.md`, `docs/MODEL_WORKFLOW.md` — cách chạy, bằng chứng và giới hạn.
4. `PRODUCT.md`; tham khảo `docs/WEB_APP_DEMO_PLAN.md` và `docs/PROJECT_UNDERSTANDING.md` khi cần.

Kiểm `AGENTS.md`, Git status và mã thực tế. Phần lớn implementation hiện chưa commit; đó là công việc cần giữ, không reset/revert/clean. Line numbers trong review có thể thay đổi, tìm theo hàm và hành vi.

Review trước đã chạy build thành công và 57 test pass, nhưng phát hiện 8 edge cases chưa được bao phủ. Không coi bộ test hiện có xanh là đủ hoàn thành lần sửa này.

## 2. Mục tiêu và giới hạn

Đây là công cụ local để nhập phản hồi → phân tích → lọc → rà soát/sửa nhãn → xuất CSV. Báo cáo nghiên cứu chỉ là tab phụ. Giữ React/TypeScript + FastAPI/Python + SQLite; giữ giao diện và luồng đang dùng, không redesign hay xây lại app.

Chưa có checkpoint ED fine-tune thật ở lần review. Đây là blocker nghiệm thu model riêng, không phải lý do dừng sửa phần mềm. Không lấy pretrained model, fixture hoặc bảng accuracy làm inference thật. Không tự train/download ensemble hoặc tìm dữ liệu ngoài phạm vi để lấp blocker.

Không tự commit, push, deploy public hoặc sửa/xóa dữ liệu người dùng. App thật có thể đang chạy tại `127.0.0.1:8765`; tests/repro dùng runtime tạm và cổng riêng, không stop app đó như một side effect của test. Nếu cần restart app để bàn giao thì phải phân biệt rõ process do script quản lý và bảo toàn dữ liệu/job.

## 3. Dùng subagents GPT-6.1 Sol

Dùng model `gpt-6.1-sol`, phân việc với ownership rõ ràng. Gợi ý:

- Agent frontend: R2, R7 và phần UI của R1.
- Agent backend/worker: R4, R5, R6 và phần API/storage của R1 sau khi chốt contract.
- Agent ML: R3, R8.

Bạn là agent chính: chốt contract R1 với frontend/backend trước, tích hợp và chạy kiểm thử chung. Các agent không làm một mình, không revert thay đổi người khác. Tránh hai người sửa cùng file đồng thời. Cho agent review lại bản sửa của phần khác sau khi tích hợp nếu hữu ích.

## 4. Danh sách bắt buộc sửa

### R1 — Giữ đúng nhãn human khi run khác dự đoán khác

`apps/web/src/ItemDetail.tsx`: trạng thái confirmed hiện lấy label hiển thị và payload save từ prediction đang xem. Sửa note có thể đổi nhãn đã xác nhận ở run A sang prediction B.

Cần phân biệt:
- Review đã lưu: label, source_prediction_id và note của nó.
- Người dùng chủ động xác nhận prediction đang xem.

Sửa note không được đổi label/source. Nếu API hiện chỉ cho confirmed khớp prediction hiện tại, hãy bổ sung/điều chỉnh contract để giữ confirmation nguồn hợp lệ, không chỉ sửa frontend rồi phát sinh 409. Giữ history, schema, input revision và optimistic concurrency.

Test hai run trên cùng input với label khác nhau; đổi run và note-only save phải giữ label/source cũ; explicit reconfirm mới thay đổi.

### R2 — Conflict không được tự nâng base revision của draft cũ

Draft cần lưu base review revision riêng theo task. Refetch/409 không tự lấy server revision mới để gửi draft cũ. Hiển thị xung đột và cho tải bản server hoặc chủ động áp lại draft sau đối chiếu; không xóa nội dung đang viết âm thầm.

Test hai tab/context hoặc hai client cùng chỉnh: save cạnh tranh nhận conflict, click lại không âm thầm overwrite, và có đường resolve rõ ràng. Bao phủ cả refetch nền trước lần save đầu.

### R3 — Lỗi inference transient không khóa registry lâu dài

`services/inference/registry.py` cache mọi exception trong `_failures`; worker từ đó coi artifact unavailable và không retry được dù artifact tốt.

Phân loại lỗi load/integrity với runtime inference; transient lỗi không poison availability vĩnh viễn, thành công phải clear trạng thái thích hợp. Giữ bảo vệ hash/schema/head và không lưu raw input trong exception. API và worker production là hai process, đừng giả định chúng chia sẻ registry failure state.

Test fail-once → retry thật trong worker → success không cần restart/sửa artifact; artifact hỏng vẫn bị chặn.

### R4 — Preemption không làm bulk hết lease

`services/worker.py`: bulk giữ lease giữa batch nhưng heartbeat chỉ gia hạn quick job đang chạy. Quick lâu hơn lease làm bulk interrupted dù worker khỏe.

Thiết kế yield/resume có transaction/fencing hoặc heartbeat cho suspended jobs đúng nghĩa. Không chỉ tăng timeout. Giữ cancel, retry, priority, progress và chống duplicate.

Test quick lâu hơn lease, chuỗi quick jobs, bulk tự hoàn tất không cần retry; kiểm stale worker và cancellation vẫn đúng.

### R5 — Export provenance đúng từng dòng/revision

`Store.export()` không được gắn latest run/model vào revision mới hoặc dòng thêm sau run chưa được phân tích. Tách selected run của export với actual prediction provenance; dòng chưa xử lý cần trạng thái rõ và provenance phù hợp, không giả đã thuộc run cũ.

Explicit historical run export phải lấy revisions của run đó. File snapshot đã xuất không đổi khi edit/review tiếp.

Test edit-after-run, append-after-run, partial/failed và historical run; giữ AI/reference/human tách biệt, CSV BOM và formula escaping.

### R6 — TTL quick payload hoạt động khi worker luôn bận

Cleanup phải chạy định kỳ theo thời gian, không chỉ lúc queue idle. Cần hoạt động cả trong inference dài, không xóa active job hợp lệ hoặc dữ liệu đã chủ động lưu thành dataset bền.

Định nghĩa khoảng cleanup tối đa hợp lý và cập nhật mô tả nếu cần. Test dùng clock kiểm soát hoặc TTL ngắn, không ngủ 15 phút; không chỉ gọi cleanup trực tiếp rồi coi đã test scheduler.

### R7 — Dấu phân cách Tab thật

Trong JSX, `value="\t"` hiện là hai ký tự. Dùng `value={"\t"}` hoặc conversion rõ ràng.

E2E tải file tab-separated, chọn Tab thủ công, preview và import đúng text/metadata; kiểm auto-detect và delimiter khác không regress.

### R8 — Recovery OOF float16 đúng precision

`scripts/model_oof.py` đang áp tolerance float32 lên historical float16 targets. Hỗ trợ reconstruction theo dtype có bound rõ, hoặc rebuild float32 từ đủ 30 OOF rồi strict audit và cập nhật recovery workflow.

Không bỏ validation provenance, 30 teachers, 6 held-out predictions mỗi dòng, fold/hash/order/finite/range. Không chỉ tăng tolerance tùy ý.

Test historical float16 hợp lệ được phục hồi; target bị sửa ngoài rounding error và provenance sai vẫn fail. Ghi đúng precision targets thực sự dùng train.

## 5. Quy trình sửa và kiểm thử

1. Xác nhận các lỗi còn tồn tại trên tree hiện tại. Tạo regression test có ý nghĩa cho từng finding trước/cùng bản sửa; lưu evidence lỗi ban đầu khi khả thi.
2. Chốt R1 contract và ownership, sửa theo cụm độc lập; không refactor diện rộng.
3. Nếu thay schema database, thêm migration tương thích dữ liệu hiện có. Không sửa lại migration 1 như thể mọi máy đều database mới, không xóa runtime để test pass.
4. Cập nhật TypeScript/API contract/tests/docs liên quan trong cùng thay đổi.
5. Chạy targeted regressions, sau đó build và full suite một lần khi đã tích hợp. Nếu có failure thì fix và chạy lại phần cần thiết.
6. Kiểm browser thật cho R1/R2/R7, có thể dùng test-only model fixtures tách khỏi production. Backend jobs/TTL/registry phải có integration tests tương ứng.
7. Đọc lại diff và cho review độc lập các case đã sửa. Không mở rộng scope vô hạn sang cosmetic issues.

Lệnh nền:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd apps\web
npm.cmd run build
```

E2E dùng production frontend build, nên build trước lượt chạy full suite cuối. Dùng Python `-X utf8` khi cần cho script đọc/ghi tiếng Việt trên Windows.

## 6. Bàn giao

Cập nhật báo cáo validation với kết quả THỰC SỰ chạy, không giữ nguyên số 57 như thể chưa thêm regressions. Tạo bảng R1–R8: resolved/chưa resolved, file thay đổi và test chứng minh. Cập nhật contract, local/model workflow nếu hành vi đổi.

Phân biệt rõ:
- Build/test phần mềm và các case hồi quy đã pass.
- Live inference bằng checkpoint ED thật còn chưa nghiệm thu nếu weights vẫn thiếu.

Không tuyên bố model thật chạy chỉ vì synthetic parity hoặc E2E double pass. Không hạ test hoặc xóa validation để làm xanh. Hoàn tất các lỗi có thể sửa trong phạm vi này trước khi bàn giao; nếu một finding không còn đúng, cung cấp evidence cụ thể thay vì sửa mù.

Bắt đầu đọc review, kiểm workspace và triển khai.
