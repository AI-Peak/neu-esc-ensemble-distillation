# Runner Kaggle T4 cho tái lập NEU-ESC

Thư mục này là bộ chạy tái lập Table 6 của NEU-ESC trên Kaggle **GPU T4 x2**. Kế hoạch ban đầu là 40 run (8 setup × 5 seed 42–46, các bước bên dưới mô tả đợt này). Kết quả chốt có 180 run: 12 setup × 15 seed (42–56), sau khi thêm seed 47–56 và hai setup MLM; xem [báo cáo baseline](../reports/baseline_reproduce/README.md).

| Backbone | Setup | Hàng Table 6 |
|---|---|---|
| PhoBERT-base-v2, ViSoBERT | `st_sentiment`, `st_topic` | Single task |
| | `mtl` | 2-task |
| | `mtl_smart` | 2-task & SMART |
| | `mtl_mlm` | 2-task & MLM |
| | `mtl_mlm_smart` | 2-task & MLM & SMART |

Runner bám code công khai của tác giả ([hung20gg/multi-task-bert@b5637cc](https://github.com/hung20gg/multi-task-bert/tree/b5637cc0a8a7b5e88e794d180c11902405548eb5), bản sao nằm ở [reports/baseline_reproduce/author_code/](../reports/baseline_reproduce/author_code/)).

## Bám code tác giả ở những điểm nào

| | Single task | 2-task / 2-task + SMART |
|---|---|---|
| Model | `AutoModelForSequenceClassification` | encoder → `[CLS]` → Linear → SiLU → LayerNorm → Linear(4) / Linear(10) |
| Epoch | 15, early stopping patience 4 theo val macro-F1 | 20 |
| AdamW | lr 2e-5, eps 1e-8, weight decay 0.01 | lr 2e-5, eps 5e-9, weight decay 0.01 |
| LinearLR theo epoch | 1 → 0.2 | 1 → 0.1 |
| Loss | CE | `0.5·(CE_s + 0.02·SMART_s) + 0.5·(CE_t + 0.02·SMART_t)` |

Thiết lập chung: batch 128, max_length 128, tokenizer slow. Dữ liệu lấy từ CSV của tác giả, có kiểm SHA-256. PhoBERT đọc `*_processed.csv` (tác giả đã tách từ sẵn), ViSoBERT đọc CSV gốc. Model khóa theo revision ghi trong `BACKBONES` của `neu_esc_kaggle.py`. Các phát hiện về code tác giả nằm trong [báo cáo baseline](../reports/baseline_reproduce/README.md); số liệu Table 6, Figure 3 và kiểm tra dữ liệu nằm trong [paper/](../reports/baseline_reproduce/paper/) và [data_source/](../reports/baseline_reproduce/data_source/).

**SMART theo đúng code tác giả.** Code gốc cộng noise vào *token ID* rồi gọi `.long()`, nên gradient theo noise luôn là `None`. Kết quả là khoảng 49% token bị đổi thành ID liền trước, sau đó tính sym-KL với `reduction='sum'`. Hàm `author_smart_ids` cho ra ID và loss giống hệt `SMARTLoss` gốc. Lệnh `python src_baseline/check_author_smart.py` kiểm tra điều này.

**Lệch có chủ đích** (mỗi run ghi lại trong `config.json`):
1. **fp16 autocast + GradScaler**, vì T4 không có bf16; tác giả train fp32.
2. **Batch 128 = micro-batch × tích lũy gradient**, mỗi micro-batch pad theo câu dài nhất. Đã kiểm trên CPU: logits sau 2 bước tối ưu với micro-batch 16 và 128 lệch nhau tối đa 4e-7, trong khi một bước tối ưu làm logits thay đổi khoảng 9e-3. Riêng SMART, phần sym-KL dạng `sum` được cộng dồn không chia, đúng scale của batch 128.
3. **SMART bỏ lượt forward đầu tiên**: lượt này không ảnh hưởng kết quả vì gradient theo noise luôn là `None`.
4. **Chọn checkpoint 2-task theo trung bình val macro-F1 của hai task.** Tác giả lưu mọi epoch từ epoch 4 rồi chọn tay. Test không bao giờ được dùng để chọn.

Metrics có thêm `weighted_f1_author_mtl`: trainer 2-task của tác giả gọi `f1_score(pred, true)`, tức đảo đối số, nên weighted-F1 của họ tính theo phân phối dự đoán. Dùng cột này khi so wF1 của các hàng 2-task với Table 6.

## Các file

| File | Việc |
|---|---|
| `neu_esc_kaggle.py` | `fetch` (tải và kiểm CSV), `prefetch` (cache model), `train` (một run) |
| `run_queue.py` | chạy nhiều run, mỗi GPU một process, run dài chạy trước; bỏ qua run đã `COMPLETED` |
| `check_runs.py` | kiểm tra kỹ thuật run đã xong (điều kiện đi tiếp), không so với paper |
| `aggregate.py` | gộp các thư mục `runs/` thành mean ± std, so với Table 6, tính mức lợi giữa các setup kèm Welch p |
| `smoke_timing.ipynb` | 8 setup × 30 step để đo thời gian/VRAM và ngoại suy tổng GPU-giờ |
| `run_seeds.ipynb` | chạy thật theo danh sách `SEEDS` |
| `check_author_smart.py` | so SMART của runner với `SMARTLoss` gốc |

## Chạy trên Kaggle

1. **Đưa code lên.** Có hai cách:
   - Upload các file `.py` trong `src_baseline/` thành một Kaggle Dataset **riêng tư**, rồi *Add Input* vào notebook. Notebook tự tìm `neu_esc_kaggle.py` trong `/kaggle/input`. **Không upload các thư mục `account_*`**, vì chúng chứa API token (`kaggle.json`).
   - Hoặc để notebook `git clone`, nếu code đã có trên GitHub. Việc push do người phụ trách module 04 quyết định.
2. **Cài đặt notebook:** Accelerator = **GPU T4 x2**, Internet = **On** (tài khoản cần xác minh số điện thoại).
3. **Chạy `smoke_timing.ipynb`** (khoảng 20–40 phút). Nó in bảng thời gian mỗi run và tổng GPU-giờ cho 40 run, đồng thời gợi ý micro-batch theo VRAM.
4. **Chạy `run_seeds.ipynb` với `SEEDS = [42]`** bằng *Save Version → Save & Run All*. Notebook tự chạy `check_runs.py`. Chỉ khi **cả 8 run PASS** mới chạy tiếp seed 43–46.
5. **Chạy mỗi seed còn lại trong một session riêng.** Mỗi tài khoản Kaggle chạy một seed.
6. **Tải kết quả về máy.** Thư mục `/kaggle/working/runs/` của mỗi session nằm ở tab Output của notebook version. Giải nén vào `runs/s42/`, `runs/s43/`, …. `runs/` đã được `.gitignore`. Sau đó kiểm tra và gộp:

```bash
python src_baseline/check_runs.py runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 --seeds 42 43 44 45 46
python src_baseline/aggregate.py runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 runs/gap/a runs/gap/mlm --out reports/baseline_reproduce/metrics
```

Kết quả thô từng run (logits, predictions) nằm trong `runs/` và không commit. Bảng tổng hợp nhỏ `reports/baseline_reproduce/metrics/` (gồm `summary.md`, `summary.csv`, `per_run.csv`, `gains.csv`) thì được commit làm kết quả tái lập.

**Điều kiện đi tiếp là điều kiện kỹ thuật, không phải điểm số.** `check_runs.py` cho PASS khi:
- run chạy xong đúng protocol (không phải run smoke/debug);
- loss hữu hạn và giảm;
- val macro-F1 cao hơn mức đoán toàn lớp đa số;
- logits hữu hạn, đủ 3.305 dự đoán val và 6.613 dự đoán test, ID không trùng;
- mọi run cùng một phiên bản code (cùng `runner_sha256`).

Không duyệt theo việc điểm có gần Table 6 hay không. Nếu lệch xa paper thì chỉ đi tìm lỗi trong code, không chỉnh cấu hình để đuổi theo số của paper. Nếu buộc phải đổi protocol thì tạo cohort mới và ghi quyết định trước khi xem điểm test.

Mỗi run ghi vào `runs/<backbone>-<setup>-s<seed>/`. Không lưu checkpoint, chỉ lưu các file sau:
- `config.json`: hyperparameter, phiên bản thư viện, GPU, SHA-256 của dữ liệu, các lệch đã nêu, và `code` (SHA-256 của `neu_esc_kaggle.py`, kèm git commit nếu có);
- `epochs.jsonl`: loss, thời gian, VRAM đỉnh và val metrics từng epoch;
- `metrics.json`: epoch tốt nhất, val/test metrics, F1 từng lớp, confusion matrix (hàng = nhãn thật), thời gian;
- `predictions.csv`: dự đoán val/test của epoch được chọn theo ID mẫu, ví dụ `test:000000:cdd81b2c7b96` (split, số dòng trong CSV, tiền tố hash của CSV gốc);
- `logits.npz`: logits val/test của epoch được chọn, ID mẫu, nhãn, và logits val của mọi epoch (`--test-every-epoch` lưu thêm test từng epoch, chỉ để phân tích sau).

Các cờ `--epochs`, `--max-steps-per-epoch`, `--limit-eval`, `--model-path`, `--fp32` biến run thành `benchmark_eligible=false`. `aggregate.py` bỏ qua các run này, trừ khi thêm `--include-debug`.

## Thử trên CPU

Cần `torch`, `transformers<5`, `sentencepiece`, `scikit-learn`, `pandas`. Dùng một model tí hon có tokenizer thật, đặt ở `runs/tiny/phobert`. `data/raw/` và `runs/` đều đã được `.gitignore`, nên dữ liệu và model thử không bị commit nhầm:

```bash
python src_baseline/neu_esc_kaggle.py fetch --data-dir data/raw/kaggle
python src_baseline/neu_esc_kaggle.py train --backbone phobert --setup mtl_smart --seed 42 --data-dir data/raw/kaggle --out-dir runs/cpu --model-path runs/tiny/phobert --epochs 2 --max-steps-per-epoch 3 --limit-eval 200 --micro-batch 32
```
