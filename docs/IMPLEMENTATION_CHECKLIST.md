# Tiến độ triển khai

- [x] Đọc tài liệu, kiểm Git, giữ nguyên tài liệu chưa commit.
- [x] Chốt label map và API/inference contract (`APP_CONTRACT.md`).
- [x] Kiểm kê artifact, adapter và hook export/reload/parity bằng model nhỏ kiểm thử.
- [x] API, migration SQLite, import/export, review revisions.
- [x] Worker leases/fencing/recovery và quick jobs TTL.
- [x] React workspace tiếng Việt, charts/table/filter/review.
- [x] Tích hợp, kiểm thử pytest và Playwright desktop/mobile/restart.
- [x] Scripts Windows, backup/restore, chạy local và báo cáo bàn giao.
- [ ] Nghiệm thu live inference bằng checkpoint thật (phụ thuộc artifact).

Repo/cache liên quan chưa có student ED fine-tune hoặc OOF. Không chạy teacher ensemble trên CPU. Workflow GPU/export đã chuẩn bị trong `MODEL_WORKFLOW.md`. Xem `VALIDATION_REPORT.md` để phân biệt kiểm thử phần mềm và nghiệm thu model thật.
