# src_improvement: code cải tiến (improvement)

Thư mục này = **[src_baseline/](../src_baseline/README.md) + ED (Ensemble Distillation, setup `mtl_ed`)**; ngoài ra không có gì khác.

- Runner `neu_esc_improvement.py` được dựng từ đúng file `src_baseline/neu_esc_kaggle.py`, chỉ thêm phần cải tiến.
- Mọi setup của baseline (`st_sentiment`, `st_topic`, `mtl`, `mtl_smart`, `mtl_mlm`, `mtl_mlm_smart`) vẫn chạy được và cho logits **giống hệt** runner baseline. Điều này đã kiểm trên CPU.
- Dữ liệu, backbone, siêu tham số chung, cách chọn checkpoint và các file output đều giống baseline; xem README của baseline.
- `--dataset vsfc` chạy mọi lệnh trên UIT-VSFC thay vì NEU-ESC, cùng siêu tham số (xem [data/UIT-VSFC](../data/UIT-VSFC/README.md)).

| File | Nội dung |
|---|---|
| `neu_esc_improvement.py` | Runner: `fetch`, `prefetch`, `train`, `ensemble-targets` |
| `run_queue.py` | Chạy nhiều job, mỗi GPU một job; `--folds N` để chạy các fold teacher |
| `check_runs.py` | Kiểm tra kỹ thuật các run (PASS/FAIL) |
| `aggregate_improvement.py` | So ED với các baseline reproduce (trung bình ± std, Δ, Welch t-test) |

## Thay đổi so với baseline

1. Thêm setup `mtl_ed` và các hằng số `ED`, `FOLD_SEED`.
2. Thêm phần chia fold (`--fold k --num-folds N`) và term ED trong hàm loss của `train()`.
3. `predict()` trả model về đúng mode cũ.
4. Thêm output `oof.npz` cho run fold.
5. Thêm lệnh `ensemble-targets` và lựa chọn `--dataset`.

Code các thử nghiệm không dùng (ablation giai thừa, các biến thể tự distill) đã được gỡ khỏi thư mục này; vẫn còn trong lịch sử git.

## ED (`mtl_ed`)

- Kiến trúc và loss giữ nguyên như `mtl` của baseline (không SMART, không MLM).
- Thêm một teacher cố định: dự đoán *out-of-fold* của một ensemble trên tập train.
- Từ epoch 1, mỗi task cộng thêm γ · KL(p_ens ‖ p), γ = 1.
- Cần `--ens-targets`. Chọn checkpoint và test bằng chính model; khi dùng thật vẫn chỉ là một model.

Out-of-fold nghĩa là mỗi câu train chỉ được dự đoán bởi model *không* thấy câu đó lúc train. Nhờ vậy nhãn mềm mang thông tin thật, không phải nhãn đã học thuộc.

## Chạy ED (3 bước)

```bash
# 1. Teacher: chia train thành 5 fold (cố định, FOLD_SEED = 2026), mỗi run train trên 4 fold và dự đoán fold còn lại -> oof.npz
python src_improvement/run_queue.py --setups mtl --folds 5 --seeds 42 43 44 --backbones phobert visobert --data-dir DATA --out-dir runs/teachers

# 2. Gộp xác suất out-of-fold của mọi run (có thể trộn backbone và seed) thành một file
python src_improvement/neu_esc_improvement.py ensemble-targets runs/teachers/*-f?of5 --out runs/teachers/ens_targets.npz

# 3. Train ED
python src_improvement/run_queue.py --setups mtl_ed --seeds 42 43 --backbones phobert visobert --data-dir DATA --out-dir runs/ed -- --ens-targets runs/teachers/ens_targets.npz
```

Ở bước 2, mọi dòng train phải có ít nhất một dự đoán out-of-fold, nên mỗi bộ fold phải đủ cả 5 fold. Bước 3 kiểm tra file target được tạo từ đúng train CSV (SHA-256).

Lệnh tổng hợp:

```bash
python src_improvement/aggregate_improvement.py runs/gap/f runs/s42 runs/s43 runs/s44 runs/s45 runs/s46 runs/gap/a runs/gap/mlm --out reports/improvement
```

## Test nhanh trên CPU

```bash
python src_improvement/run_queue.py --setups mtl --folds 2 --seeds 42 --backbones phobert --data-dir DATA --out-dir runs/cpu --no-prefetch -- --model-path TINY --epochs 1 --max-steps-per-epoch 3 --limit-eval 200
python src_improvement/neu_esc_improvement.py ensemble-targets runs/cpu/phobert-mtl-s42-f0of2 runs/cpu/phobert-mtl-s42-f1of2 --out runs/cpu/ens.npz
python src_improvement/neu_esc_improvement.py train --backbone phobert --setup mtl_ed --seed 42 --data-dir DATA --out-dir runs/cpu --model-path TINY --epochs 2 --max-steps-per-epoch 3 --limit-eval 200 --ens-targets runs/cpu/ens.npz
```

`TINY` là một model nhỏ tự tạo (cùng tokenizer với PhoBERT), chỉ dùng để kiểm tra code chạy được.
