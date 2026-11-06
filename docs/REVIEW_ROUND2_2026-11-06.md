# Review lại bản sửa R1–R8

Ngày 2026-11-06. Workspace `F:\DPL_NEU-ESC`, HEAD `c539171`, review trên working tree chưa commit.

## Kết luận

**Cả 8 finding cũ đã được xử lý trong phạm vi tái kiểm tra. Không phát hiện finding P1/P2 mới có bằng chứng trong vùng sửa và các luồng liên quan.** Đây là kết luận về các bản sửa được review, không là bảo đảm mọi chức năng của ứng dụng đều không còn lỗi.

Agent chính và ba subagent GPT-6.1 Sol kiểm code, contract và regression tests theo ba phần: frontend, backend/worker, inference/OOF. Không sửa implementation, không train/tải model, không restart app người dùng.

| Finding | Kết quả kiểm lại |
|---|---|
| R1 | Draft giữ label và prediction nguồn của review; note-only không chuyển theo run hiện tại. Backend kiểm nguồn cùng item/input/schema/label. Explicit reconfirm có thao tác riêng. |
| R2 | Draft giữ base revision riêng từng task; conflict hoặc refetch không tự nâng base của draft dirty. UI chặn save và cho tải server hoặc chủ động áp lại bản nháp. |
| R3 | Runtime/load transient errors không poison artifact availability; worker retry được trong cùng process. Artifact lỗi cấu trúc/hash/schema vẫn bị chặn. |
| R4 | Batch chưa hoàn tất nhả lease và về queued trong transaction commit progress; claim mới tăng attempt. Quick job lâu không làm bulk bị interrupted. |
| R5 | Export tách selected run khỏi prediction provenance từng dòng. Revision chưa phân tích không mang model/run cũ; historical snapshot vẫn dùng revision gốc. |
| R6 | Cleanup có lịch độc lập queue idle, chạy trong keepalive khi inference dài; bảo vệ active jobs và dữ liệu đã lưu bền. |
| R7 | Option Tab gửi ký tự TAB thật; E2E kiểm preview và commit các delimiter. |
| R8 | OOF reconstruction theo thứ tự nguồn archive và chuỗi precision float64 → float32 → dtype lưu; float16 hợp lệ qua kiểm tra, tampering/provenance sai vẫn bị từ chối. |

## Kiểm chứng chạy lại trong lượt review

- `npm.cmd run build` trong `apps/web`: TypeScript/Vite thành công; JS 343,49 kB, gzip 102,43 kB.
- `.venv\Scripts\python.exe -X utf8 -m pytest -q --junitxml=test-results/review-round2-2026-11-06.xml`: **105 passed, 5 warnings, 89,68 giây**, không skip.
- `git diff --check`: pass.
- Full suite gồm API/storage, worker boundaries, inference/OOF, 13 Chromium E2E, Windows launcher, backup và runtime isolation. Các regression browser R1/R2/R7 đã chạy trong suite này; không chỉ kiểm tên test hoặc dựa vào báo cáo bàn giao.
- Đã xem ảnh trạng thái confirmation giữ nguồn và giao diện giải quyết conflict do E2E tạo. Phạm vi này không là audit accessibility toàn diện.
- Subagent backend còn chạy targeted checks: 15 passed, 22 deselected. Không dùng kết quả này thay cho full suite của agent chính.

Các warning hiện có liên quan Starlette/httpx, SentencePiece và Transformers; không có failure. E2E và model tests dùng test-only doubles/synthetic artifacts để kiểm hành vi, không chứng minh chất lượng student ED thật.

## Giới hạn và vận hành còn lại

1. `runtime/models` chưa có bundle fine-tune. Nghiệm thu live inference, latency và RAM bằng model thật vẫn chưa hoàn tất. Đây là phụ thuộc artifact đã biết, không là lỗi mới của bản sửa.
2. Trong lúc review, listener cổng 8765 vẫn là PID 16108, khởi động lúc 06:31:35 giờ Việt Nam. Các file API/storage/worker được cập nhật khoảng 07:01–07:02, nên process backend đang chạy chưa nạp bản sửa. Cần restart có chủ đích để sử dụng backend mới; review không tự restart hoặc can thiệp dữ liệu/job đang dùng.
3. Tests dùng runtime tạm, cổng riêng; `tests/conftest.py` cô lập cả module-level API trước collection. Không xóa/reset runtime người dùng.

Báo cáo finding gốc `REVIEW_2026-11-06.md` được giữ làm lịch sử. Kết quả vòng hai này thay thế trạng thái chưa sửa của R1–R8 ở báo cáo đó.
