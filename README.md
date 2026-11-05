# NEU-ESC reproduction

Repo này của Group 5 (DPL302m) tái lập Table 6 của paper [NEU-ESC](https://arxiv.org/abs/2506.23524) trên Kaggle GPU T4, cải tiến bằng ED (Ensemble Distillation) và kiểm tra thêm trên UIT-VSFC. Bản nháp paper: [reports/draft_paper.md](reports/draft_paper.md).

## Baseline đã chạy: 12 setup × 15 seed (42–56) = 180 run

| Setup | PhoBERT-base-v2 | ViSoBERT |
|---|---|---|
| Single-task sentiment | ✓ | ✓ |
| Single-task topic | ✓ | ✓ |
| 2-task (encoder dùng chung + 2 head) | ✓ | ✓ |
| 2-task + SMART | ✓ | ✓ |
| 2-task + MLM | ✓ | ✓ |
| 2-task + MLM + SMART | ✓ | ✓ |

Hai setup single-task cùng tạo thành một dòng Table 6, nên 12 setup này ứng với 10 dòng của 2 backbone. Toàn bộ quá trình kiểm tra độ lệch có 210 run, gồm thêm 30 run fp32 và SMART trên embedding.

Runner bám code công khai của tác giả ([hung20gg/multi-task-bert@b5637cc](https://github.com/hung20gg/multi-task-bert/tree/b5637cc0a8a7b5e88e794d180c11902405548eb5)):
- hyperparameter, head và loss 0.5/0.5 lấy theo code tác giả;
- SMART theo đúng code tác giả, đã kiểm khớp từng bit;
- PhoBERT đọc `*_processed.csv` (bản đã tách từ của tác giả).

Kết quả chỉ được gọi là "tái lập theo code công khai", không phải khôi phục đúng thí nghiệm của paper.

## Cấu trúc

| Đường dẫn | Nội dung |
|---|---|
| [src_baseline/](src_baseline/README.md) | Code baseline (reproduce NEU-ESC): runner, queue chạy 2 GPU, kiểm tra kỹ thuật, tổng hợp kết quả, notebook smoke và notebook chạy thật. **Bắt đầu từ đây.** |
| [src_improvement/](src_improvement/README.md) | Code cải tiến: baseline + ED (Ensemble Distillation, `mtl_ed`). |
| `kaggle/` | Chỉ chứa API token của các account Kaggle (gitignored, không commit). |
| `docs/papers/` | Paper và proposal. Chỉ có trên máy, không commit |
| [reports/baseline_reproduce/](reports/baseline_reproduce/README.md) | **Báo cáo baseline reproduce**: số chốt, nguyên nhân lệch so với paper, metrics 15 seed, số liệu paper, bản sao code tác giả, hash dữ liệu |
| [reports/improvement/](reports/improvement/README.md) | Kết quả ED so với baseline trên NEU-ESC |
| [reports/uit_vsfc/](reports/uit_vsfc/README.md) | Kiểm tra tổng quát hoá: baseline và ED trên UIT-VSFC |
| [reports/logit_bias/](reports/logit_bias/summary.md) | Phân tích logit bias sau huấn luyện cho lớp hiếm |
| [reports/draft_paper.md](reports/draft_paper.md) | Bản nháp paper: dàn ý và toàn bộ bảng |
| [data/UIT-VSFC/](data/UIT-VSFC/README.md) | Dữ liệu UIT-VSFC (split chính thức) và cách tạo CSV |

## Dữ liệu

Runner tự tải 6 file CSV từ repo tác giả và kiểm SHA-256 (`python src_baseline/neu_esc_kaggle.py fetch --data-dir …`). Thư mục `data/raw/` và `runs/` đã được `.gitignore`.

**Cần nhóm quyết định:** `data/NEU/*.csv` (3 file CSV gốc) đang nằm trong git và đã có trên `origin/main`, trong khi `data/.gitignore` ghi chưa xác định được quyền phân phối lại. `data/UIT-VSFC/` chưa được commit. Bản CSV NEU trong git dùng CRLF nên không qua được bước kiểm hash của runner (nội dung khớp sau khi đổi về LF); khi train hãy dùng lệnh `fetch` ở trên.

## Quy định

- Không push khi chưa được người phụ trách repo đồng ý.
- Không chọn seed hay checkpoint theo test.
- Điều kiện đi tiếp giữa các seed là `src_baseline/check_runs.py` báo PASS, không phải điểm có gần paper hay không.
