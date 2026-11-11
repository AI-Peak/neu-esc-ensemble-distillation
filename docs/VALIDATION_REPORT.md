# Báo cáo Kiểm chứng & Nghiệm thu Demo Webapp Ba lớp (T00–T11 · M0–M4 — 2026-11-10)

- **Ngày hoàn tất nghiệm thu:** 2026-11-10 (`F:\DPL_NEU-ESC`, Windows 10/11, Python `3.10.11`, nhánh `webapp`, `HEAD` `a0cebad8d625c68ca4df755de27a249e2b8ba134` + thay đổi `T00–T11` chưa commit).
- **Tài liệu quy chuẩn:** [`docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md`](docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md) (`T00–T11`, `M0–M4`, `C–G`, `H1–H3`, `I1–I7`, `J1–J4`). Các phần lịch sử **F1/F2**, **R1–R4**, **PhoBERT MTL-ED đợt gốc** và **R1–R8** bên dưới được giữ nguyên toàn vẹn.
- **Trạng thái nghiệm thu:** **ĐẠT (M0 · M1 · M2 · M3 · M4)** — **0 P0 · 0 P1 · 0 P2 mở**. Không tự ý `git commit`, `push`, `deploy`, `train`, tải pretrained weights, hay khởi động/dừng app production trên cổng `8765`.
- **Điều phối & Kiểm thử Cô lập (`I2–I7`):** Harness hỗ trợ native subagent: **1 Coordinator chính** + **3 subagent độc lập (`Backend`, `Frontend`, `QA_Review`)** làm việc theo ownership không chồng lấn qua các đợt `0–5`. QA review read-only implementation trước mỗi mốc M1–M4. Toàn bộ tác vụ inference nặng (`T05`, `real_model`, `H2`, `G4`) chạy tuần tự (1 lượt mỗi thời điểm, không dùng `pytest-xdist`) trên runtime/model root tạm tại `C:\Users\Admin\AppData\Local\Temp\feedback-three-layer-9df36e015c834a549411cccb3433c43e`.

---

## 1. Tổng hợp Mốc Sản phẩm (M0–M4) & Tài liệu đã cập nhật

| Mốc | Phạm vi | Thay đổi & Đầu ra chính | Trạng thái |
|---|---|---|---|
| **M0** | `T00` Baseline & Cô lập | Chụp snapshot SHA-256 (`baseline/t00_baseline.json`), thiết lập audit root cô lập ngoài repo (`runtime/` production không bị chạm). | **Đạt** |
| **M1** | `T01–T02` Decision Support | Thêm [`services/analytics.py`](services/analytics.py), cập nhật [`services/storage/db.py`](services/storage/db.py), [`services/api/main.py`](services/api/main.py), [`apps/web/src/TopicAttention.tsx`](apps/web/src/TopicAttention.tsx), [`Workspace.tsx`](apps/web/src/Workspace.tsx): xếp hạng **Chủ đề cần chú ý** (`negative_count DESC, eligible_count DESC, topic_id ASC`), mẫu số rõ, `Ít dữ liệu` (`n < 5`), `Toxic` tách riêng (`neu-v1`), chuyển đổi nguồn nhãn `effective`/`ai`, lọc click-through giữ bộ lọc và `run_id`, E2E + review độc lập M1. | **Đạt** |
| **M2** | `T03–T05` Tín hiệu rà soát & Validation | Thêm [`services/review_policy.json`](services/review_policy.json), [`services/review_signals.py`](services/review_signals.py), [`scripts/evaluate_review_signals.py`](scripts/evaluate_review_signals.py); tách riêng `review_signal` khỏi `needs_review` cũ; cờ theo task + `truncated` độc lập; đồng bộ `pending_signal_review` theo `source_prediction_id` & `revision_id`; modal xuất CSV `filtered`/`all` bất biến; chạy evaluation thật T05 trên `3.305` dòng raw `val_set.csv`. | **Đạt** |
| **M3** | `T06–T09` Khám phá độ nhạy & Bền vững | Thêm [`services/sensitivity.py`](services/sensitivity.py), [`apps/web/src/SensitivityPanel.tsx`](apps/web/src/SensitivityPanel.tsx); migration SQLite **schema v2** (`jobs.priority`, `sensitivity_experiments`, `sensitivity_rate_limits`); chuẩn hóa & tách occurrence an toàn Unicode/NFD/emoji (UTF-16 indices); worker preemption `priority=1`, `predict_pair` atomic trên cùng identity, cancel/retry/TTL 15 phút, cập nhật [`scripts/backup_local.py`](scripts/backup_local.py) + test DB v1/backup/cascade delete/readonly guards. | **Đạt** |
| **M4** | `T10–T11` Demo thật & Handover | Tạo [`data/demo/three_layer_feedback_vi.csv`](data/demo/three_layer_feedback_vi.csv) (24 câu minh họa) & [`data/demo/README.md`](data/demo/README.md); chạy [`tests/inference/test_three_layer_real_model.py`](tests/inference/test_three_layer_real_model.py), hồi quy F1/F2 `@pytest.mark.real_model`, full default suite, rehearsal `H2` & benchmark `G4`; hoàn thiện [`docs/THREE_LAYER_DEMO_RUNBOOK.md`](docs/THREE_LAYER_DEMO_RUNBOOK.md), [`docs/LOCAL_APP.md`](docs/LOCAL_APP.md), [`PRODUCT.md`](PRODUCT.md) và báo cáo này. | **Đạt** |

---

## 2. Danh tính Build Frontend, Model, Preprocessing & Policy ở thời điểm chốt

- **Frontend build đóng băng (`apps/web/dist/`):** Không thay đổi source/build trong suốt Wave 5 (mọi bài kiểm thử default + `real_model` M4 chạy trên đúng bản build này):
  - `apps/web/dist/index.html` (`470` bytes): SHA-256 `3E14C36520E750ABD74E7DF7A99CB8933F43908565D1898BFA86BA89DF02056D`
  - `apps/web/dist/assets/index-D9NXQDUL.js` (`393.485` bytes): SHA-256 `74546B0BE8DF98920D392DB57578584C2EE5B074DD9C5B0BBB93C39AFA6BC54A`
  - `apps/web/dist/assets/index-DA8htggh.css` (`34.983` bytes): SHA-256 `54A08E3ECE54C196866F8D6A70D1B7914A0F9326F2460E2DAB79E6C68C7B4718`
- **Model thật được kiểm chứng (bản copy bất biến của bundle active NEU, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`):**
  - `profile=neu`, `schema_id=neu-v1`, `model_id=neu-phobert-mtl-ed-s42`, `model_version=neu-phobert-mtl-ed-s42-e10-617f852a3fff`, `mode=cpu-fp32-eval`.
  - Backbone: `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1` (`runtime/cache/phobert-base-v2/config.json` SHA-256 `26d21a304fdea8fada88e7c6b7c7fef15c902c690bfb0fa47f60bdb61c68307a`).
  - Bundle checksums (khớp tuyệt đối giữa production `runtime/models/neu/` và bản copy cô lập):
    - `current.json`: `887bb18a2860a1d9387d8b21384bcfe76bdd80cdf07639eaedea0d849960220b`
    - `manifest.json`: `5117b413d141d4e6b80a2805b9b5ff27b353d404d3a42bc95c29055e4f527b1d`
    - `model.safetensors`: `036b62c7b24fbe10ba30562090908fe8c81d0ebe339a84ad9fb02a569b2e20b1` (nguồn `demo/model.pt` SHA-256 `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`)
    - `preprocessing.json` spec digest (`preprocessing_sha256`): `27aa95d7e12a35df4c8614f555b7d3b17476189fc5350d240e07376703ed654a` (`underthesea 9.5.0`, `format="text"`, `use_fast=false`, `max_length=128`, `equivalence="approximate"`).
  - Profile `uit`: giữ `unavailable` (chưa có checkpoint UIT).
- **Review Signal Policy ([`services/review_policy.json`](services/review_policy.json)):**
  - `policy_id = "review-signals-v1"`, `policy_hash = "2d1cd5d7af32168af6c6ae30af6b1c43ba9f7c2f1cd6d73cc221067d1a1fc9a6"`, `experimental = true`, `top1_min = 0.60`, `margin_min = 0.15` cho cả Sentiment và Topic (`neu-v1` & `uit-v1`).

---

## 3. Lệnh kiểm thử & Kết quả chốt tích hợp cuối (Wave 5)

Toàn bộ lệnh dưới đây chạy trong `.venv` (`Python 3.10.11`, `torch 2.14.1+cpu`, `transformers 4.44.2`, `safetensors 0.8.0`, `underthesea 9.5.0`) **sau lần chỉnh sửa code/test/build cuối cùng**, với `$env:FEEDBACK_RUNTIME` trỏ tới audit root cô lập:

| Nhóm kiểm thử | Lệnh thực chạy | Kết quả chính xác | Log / Bằng chứng |
|---|---|---|---|
| **Full Integrated Default Suite** | `.\.venv\Scripts\python.exe -X utf8 -m pytest -q --basetemp '...\qa-runtime\pytest-m4-final-default-r2'` | **272 passed, 0 failed, 0 skipped, 3 deselected**, 22 warnings trong **264.52s** (`0:04:24`, exit `0`). *(3 ca deselected là nhóm `@pytest.mark.real_model`; đã xác nhận bằng lệnh dưới).* | `...\qa-runtime\m4-final-default-tests.log` |
| **G3 Real-Model 3-Layer Acceptance (Offline + Frozen Build)** | `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference/test_three_layer_real_model.py -m real_model -v --basetemp '...\real-model-tests\three-layer-r3'` (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) | **1 passed in 43.33s** (exit `0`). Xác minh full-stack với 24 câu thật, `TopicAttention` (`Dịch vụ` #1 `4/6`), `5` S-flag / `5` T-flag / `9` `pending_signal_review`, human review giữ AI gốc, sensitivity dòng 2 + >128 token (`161 -> 154` tail equal `true`, `161 -> 153` head equal `false`, parity max diff `0.0`), NFD grapheme guard, UI CSV export `9d5ea991-f1d2-48e4-82f7-9d077e67cb1a` byte-identical qua restart + append. | `...\reports\m4-real-three-layer.log`, `...\reports\real-model-three-layer.json` |
| **F1/F2 Real-Model Regressions (Offline + Empty HF Cache + Socket Blocked Import)** | `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference/test_phobert_import_and_preprocessing.py -m real_model -v --basetemp '...\real-model-tests\f1-f2'` (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`) | **2 passed, 10 deselected, 2 warnings in 54.43s** (exit `0`). Chứng minh từ chối config sai 6-head, `verify_only`, offline full-stack import & export snapshot bền qua restart. | `...\reports\m4-real-f1-f2.log` |
| **T05 Raw Validation Policy (`review-signals-v1`)** | `.\.venv\Scripts\python.exe scripts/evaluate_review_signals.py --model-root ...\validation-runtime\models --profile neu --validation-csv data/cache/neu/val_set.csv --processed-validation-csv data/cache/neu/val_set_processed.csv --policy services/review_policy.json --out ...\reports\review-signals-validation.json --markdown-out ...\reports\review-signals-validation.md --batch-size 64` | Exit `0`, **3.305/3.305 dòng hợp lệ** (`0` failed) trong **291.171s** (CPU FP32 offline). | `...\reports\review-signals-validation.{json,md}` |
| **H2 Rehearsal & G4 Benchmarks (CPU FP32 Offline)** | `.\.venv\Scripts\python.exe -X utf8 run_h2_g4.py --audit-root ...\feedback-three-layer-9df36e015c834a549411cccb3433c43e` *(script audit tạm)* | Exit `0`: hoàn tất 100% H2 trên `three_layer_feedback_vi.csv` nguyên vẹn và G4 (24/100/500 stack + preemption `0,322s` + API median/p95 + `ModelRegistry` direct). | `...\reports\m4-h2-g4.log`, `...\reports\m4-rehearsal-h2.json`, `...\reports\m4-benchmark-g4.json` |
| **Vệ sinh Git diff** | `git diff --check` | Exit `0` (sạch trailing whitespace & conflict marker sau toàn bộ chỉnh sửa). | Verified tại Bước 5F |

*(Lưu ý về 22 warnings ở default suite và 2 warnings ở F1/F2: xuất phát từ `StarletteDeprecationWarning`, `SwigPyPacked`/`SwigPyObject`/`swigvarlink` và `Transformers` `clean_up_tokenization_spaces` — đều là cảnh báo dependency có sẵn, không làm fail test.)*

---

## 4. Kết quả Validation Offline `T05` (`review-signals-v1` trên `val_set.csv` thô)

Chạy trên đúng bundle copy bất biến `neu-phobert-mtl-ed-s42-e10-617f852a3fff` (`CPU FP32`, adapter `underthesea 9.5.0`) và `data/cache/neu/val_set.csv` (**`3.305` dòng thô**, SHA-256 `0b2567fe5374cf9b8d22de92ce71d3f9bfa036dffac46fa6f7a5650e85c81169`, `gold_alignment_verified = true`, `policy_tuned = false`, `experimental = true`).

| Tác vụ / Hợp nhất | Số dòng gắn cờ | Tỷ lệ gắn cờ | Tổng số lỗi trên split | Tỷ lệ lỗi chung | Lỗi trong nhóm gắn cờ (`error_rate_flagged`) | Lỗi ngoài nhóm gắn cờ (`error_rate_unflagged`) | Độ phủ lỗi (`error_capture`) | Lift |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Sentiment** | `227` (`LOW_TOP1` `227`, `SMALL_MARGIN` `142`, cả hai `142`) | `6,87%` | `540` | `16,34%` | `49,78%` (`113/227`) | `13,87%` (`427/3.078`) | `20,93%` (`113/540`) | `3,05` |
| **Topic** | `399` (`LOW_TOP1` `399`, `SMALL_MARGIN` `204`, cả hai `204`) | `12,07%` | `679` | `20,54%` | `57,14%` (`228/399`) | `15,52%` (`451/2.906`) | `33,58%` (`228/679`) | `2,78` |
| **Hợp nhất (`union`)** | `593` (`S-only` `194`, `T-only` `366`, cả hai `33`) | `17,94%` | `1.087` | `32,89%` | `62,23%` (`369/593`) | `26,47%` (`718/2.712`) | `33,95%` (`369/1.087`) | `1,89` |

- **Bằng chứng tách riêng cảnh báo cắt ngắn (`> 128` token):** Có **`66/3.305` (`2,00%`)** dòng bị cắt ngắn; tỷ lệ lỗi hợp nhất ở nhóm bị cắt ngắn đạt **`60,61%` (`40/66`)** so với **`32,32%` (`1.047/3.239`)** ở nhóm không cắt ngắn. Đáng chú ý, **`50/66`** dòng bị cắt ngắn vẫn có điểm softmax cao/cách biệt rõ trên cả hai tác vụ (`truncated_and_score_clear_union_count = 50`) — chứng minh việc tách `Đầu vào bị cắt ngắn` khỏi cờ `top1`/`margin` là cần thiết để không bỏ sót cảnh báo cắt đầu vào.
- **Giới hạn diễn giải:** `val_set.csv` là split validation từng dùng chọn epoch 10 của checkpoint nên số liệu chỉ mang tính mô tả offline (`offline_validation_descriptive`), không phải tỷ lệ dự kiến trên dữ liệu triển khai thực tế và chưa hiệu chuẩn ngưỡng (`policy_tuned = false`).

---

## 5. Tóm tắt Rehearsal H2 (`data/demo/three_layer_feedback_vi.csv`, 24 câu)

Chi tiết từng bước và tham số thực tế đã ghi đầy đủ tại Mục 2 của [`docs/THREE_LAYER_DEMO_RUNBOOK.md`](THREE_LAYER_DEMO_RUNBOOK.md). Điểm chính:
- **Thời gian & RAM (H2 đơn luồng offline):** Startup tới health `1,195s`; cold batch 24 dòng `7,584s` (worker RSS `1.206,2 MiB`, peak working set `1.642,9 MiB`, API RSS `4,3 MiB`); warm single Quick Analysis `0,559s` wall (`51,55 ms` inference); warm Sensitivity pair (`D06`) `0,574s` wall (`42,89 ms` inference).
- **Hành vi thật trên 24 câu nguyên vẹn:** Khớp `14/24` Sentiment và `20/24` Topic với tham chiếu đề xuất trong [`data/demo/README.md`](data/demo/README.md) (`D05` mỉa mai vẫn đạt `Tích cực 0,9118`; `D24` gán `Tiêu cực 0,9796` thay vì `Toxic`); `5` cờ Cảm xúc + `5` cờ Chủ đề = **`9/24`** dòng `pending_signal_review`, `0` bị cắt ngắn; `Dịch vụ` đứng đầu **Chủ đề cần chú ý** (`4/6` Tiêu cực = `66,7%`, `0` Toxic, `small_sample=false`); thử nghiệm bỏ `"báo lỗi liên tục"` trên `D06` làm Cảm xúc đổi `Tiêu cực (0,595) -> Trung tính (0,988)` và Chủ đề đổi `Dịch vụ (0,698) -> Học tập (0,732)` kèm `SENSITIVITY_NOT_CAUSAL`; sửa độc lập Cảm xúc trên `D01` (`0 -> 1`) bảo toàn dự đoán AI & giá trị số tín hiệu; CSV export `47baab40-cdf9-4be3-a747-90c8cbaa2d21` (`24` dòng, `19.705` bytes).

---

## 6. Kết quả Benchmark G4 (CPU FP32 trên dữ liệu tổng hợp `24 / 100 / 500`)

- **Cấu hình máy đo:** `Windows-10-10.0.26200-SP0`, AMD Ryzen 7 PRO 5850U (`8` nhân vật lý / `16` luồng), `30,83 GiB` RAM, `torch 2.14.1+cpu` (`num_threads=8`), `mode=cpu-fp32-eval`. *Chỉ là phép đo cô lập trên một máy dùng text tổng hợp, không phải SLA đa máy.*

### 6.1. Full Stack (API + Worker + SQLite WAL)

| Cỡ dataset | Tổng thời gian batch | Thông lượng | Worker RSS cuối | Worker Peak WSet | Ghi chú thực thi |
|---:|---:|---:|---:|---:|---|
| **24 dòng** (cold load) | `7,276 s` | `3,30 dòng/s` | `1.202,9 MiB` | `1.641,7 MiB` | Gồm worker lazy-load PhoBERT + `underthesea` (`startup health: 1,163s`, API RSS `4,2 MiB`). |
| **100 dòng** (warm) | `5,889 s` | `16,98 dòng/s` | `895,9 MiB` | `1.641,7 MiB` | Worker đã nạp ấm model; `0` lỗi. |
| **500 dòng** (warm + preemption) | `31,625 s` | `15,81 dòng/s` | `887,0 MiB` | `1.641,7 MiB` | Chèn Sensitivity `priority=1` khi bulk ở `8/500`; Sensitivity xong trong **`0,322 s` (`322 ms`)** trước khi bulk đi từ `8 -> 16` và hoàn tất `500/500` (`0` failed). *(Sensitivity lúc queue rỗng, 3 mẫu: median `612,58 ms`, p95 `682,69 ms`).* |

### 6.2. Độ trễ API Endpoints tại `N = 24 / 100 / 500` (10 lượt GET, 5 lượt Export)

| Endpoint / Thao tác | N=24 Median / p95 | N=100 Median / p95 | N=500 Median / p95 | Payload tại N=500 |
|---|---|---|---|---:|
| `GET /summary` (`effective`) | `12,56 / 13,16 ms` | `18,63 / 25,24 ms` | **`84,81 / 123,79 ms`** | `2.221 B` |
| `GET /summary` (`ai`) | `7,52 / 10,19 ms` | `17,38 / 19,41 ms` | **`89,55 / 109,61 ms`** | `2.045 B` |
| `GET /summary` (`topic=2`) | `7,85 / 10,16 ms` | `15,34 / 19,93 ms` | **`92,89 / 111,30 ms`** | `1.248 B` |
| `GET /items` (`page_size=25`) | `12,35 / 14,81 ms` | `22,52 / 43,61 ms` | **`98,34 / 126,10 ms`** | `50.914 B` |
| `GET /items` (`pending_signal_review`) | `8,08 / 21,06 ms` | `20,80 / 25,70 ms` | **`89,23 / 103,37 ms`** | `60.703 B` |
| `GET /items` (`topic=2&sentiment=2`) | `8,80 / 9,89 ms` | `16,81 / 20,93 ms` | **`72,77 / 95,08 ms`** | `2.234 B` |
| `POST /exports` (`all`) | `16,14 / 23,95 ms` | `49,85 / 57,25 ms` | **`206,86 / 259,93 ms`** | — |
| `GET /exports/{id}` (CSV UTF-8 BOM) | `16,32 / 33,92 ms` | `15,82 / 30,04 ms` | **`33,18 / 46,01 ms`** | `433.643 B` |

### 6.3. Đo trực tiếp `ModelRegistry` (`cpu-fp32-eval`)

- `cold_first` (1 dòng đầu, gồm nạp PhoBERT + `underthesea`): **`3,695 s`** (RSS `1.206,9 MiB`).
- `warm_single` (10 mẫu): median **`55,85 ms`**, p95 **`62,41 ms`**.
- `warm_predict_pair` (5 mẫu): median **`81,82 ms`**, p95 **`85,25 ms`**.
- Direct batch `24 / 100 / 500`: `0,556 s` (`43,13 dòng/s`, `0` truncated) / `2,666 s` (`37,51 dòng/s`, `4` truncated) / `13,655 s` (`36,62 dòng/s`, `20` truncated `<= 189` token, peak wset **`1.656,7 MiB`**).

---

## 7. Phân tách rạch ròi Test Double vs Synthetic vs Model thật

| Loại nguồn kiểm chứng | Các thành phần / tests áp dụng | Chứng minh điều gì | Không chứng minh điều gì |
|---|---|---|---|
| **Software Test Doubles** | `TestOnlyRegistry` & `ControlledE2ERegistry` (`TEST-DOUBLE-E2E-CONTROLLED`), `without_model` trong API / Worker / Backup T09 / E2E M1–M3 (`tests/api/*`, `tests/integration/*`, `tests/test_backup.py`, `tests/e2e/*`) | UI/UX, lọc/phân trang/sort, optimistic concurrency (`409`), schema v2, worker preemption/cancel/lease/TTL, cascade delete, CSV snapshot & backup/restore DB v1→v2. | **Không** phải suy luận hay độ nhạy của checkpoint PhoBERT / ViSoBERT / UIT thật. |
| **Synthetic Tiny Random Encoders** | `tests/inference/{test_phobert_config,test_registry,test_sensitivity}.py` (weights PyTorch nhỏ ngẫu nhiên + tokenizer thật trong `tmp_path`) | Guard validation `config.json`, format 1/2 parity cơ chế, NFD grapheme boundaries và `model_input_equal` quanh ngưỡng `128` token. | **Không** phản ánh độ chính xác hoặc xác suất của model đã fine-tune. |
| **Synthetic Throughput Texts** | Dữ liệu text tiếng Việt tổng hợp `24 / 100 / 500` dòng trong benchmark `G4` | Thông lượng, preemption, độ trễ API và RSS/peak working set trên CPU FP32 với model PhoBERT thật. | Không đại diện phân bố chủ đề/cảm xúc của phản hồi sinh viên thật. |
| **Model & Dữ liệu thật** | Bản copy bất biến `neu-phobert-mtl-ed-s42-e10-617f852a3fff` (từ `demo/model.pt`) + `val_set.csv` (`3.305` dòng) + `three_layer_feedback_vi.csv` (`24` câu minh họa) | Validation T05, F1/F2 regression thật, G3 E2E ba tầng thật (`test_three_layer_real_model.py`), H2 rehearsal (`24` câu) và tải/chạy PhoBERT offline. | Không hiệu chuẩn softmax; `three_layer_feedback_vi.csv` do nhóm tự soạn minh họa (`illustrative=true`), không phải benchmark thống kê. |

---

## 8. Kiểm tra trực quan ảnh chụp màn hình

Toàn bộ ảnh đã được mở xem trực tiếp bằng `read_file`:
- **M1 (`test-results/screenshots/m1-*.png`, 6 ảnh `1440x960` / `1024x768` / `390x844` / `320x568`):** Bảng **Chủ đề cần chú ý** tách cột `Toxic`, nhãn `Ít dữ liệu`, chuyển mobile stacked cards và partial/error state sạch sẽ.
- **M2 (`...\reports\screenshots\m2-*.png` & `test-results/screenshots/m2-*.png`, 4 ảnh):** Cột `Tín hiệu model` tách `Rà soát`, focus bàn phím vào `Vì sao được đánh dấu?`, công bố policy hash & 3 chữ số thập phân rõ nét trên desktop/mobile.
- **M3 (`...\reports\screenshots\m3-*.png` & `test-results/screenshots/m3-*.png`, 3 ảnh):** Cặp gốc/biến thể đặt cạnh nhau/xếp dọc, đếm token trước cắt, đổi nhãn dẫn đầu và thu gọn bảng Chủ đề đúng thiết kế trên `1440px`, `390px`, `320px`.
- **M4 Real-Model (`...\reports\screenshots\m4-desktop-real-model.png` & `m4-mobile-390-real-model.png`):** Kiểm trực tiếp với `neu-phobert-mtl-ed-s42` trên 24 câu thật (`Demo Ba Tầng PhoBERT Thật`): bảng same-label ở drawer phải hiển thị chuẩn `0.000` (không lỗi `±0.000`), đếm `15` vs `13` token trước cắt, thông báo hợp lệ `"Nhãn dẫn đầu không đổi vẫn là một kết quả hợp lệ."`; mobile `390x844` không tràn ngang. *(Ghi nhận trung thực: trên `m4-desktop-real-model.png` có toast nền `"Đã tạo bản chụp CSV gồm 24 phản hồi."` ở cạnh dưới từ bước xuất CSV liền trước, không che khuất nội dung hay nút thao tác của drawer phải).*

---

## 9. Bảo toàn Artifact Production & Các giới hạn trung thực (`J1–J3`)

- **Bảo toàn 100% baseline `T00`:** Toàn bộ `10` file gốc/source/config/cache, `14` file thuộc bundle active `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff` (kể cả `current.json` & `demo/model.pt`), cùng `apps/web/dist/**` được kiểm lại SHA-256 ở Bước 5F cho **0 sai khác**. `runtime/` production và tiến trình ngoài không bị đụng chạm; `Win32_Process` sạch các process worker/API/pytest tạm.
- **Giới hạn trung thực bắt buộc nêu rõ:**
  1. Chính sách `review-signals-v1` là **heuristic thử nghiệm chưa hiệu chuẩn** (`experimental=true`, `policy_tuned=false`); điểm softmax không phải xác suất dự đoán đúng.
  2. Hệ thống **không phát hiện mỉa mai** (`D05` cho `Tích cực 0,9118`) và lớp hiếm **`Toxic`** có hạn chế thực nghiệm như đã báo cáo trong paper (`D24` gán `Tiêu cực 0,9796`).
  3. **Khám phá độ nhạy (`Sensitivity`)** chỉ đo phản ứng khi bỏ một đoạn trên đầu vào hiện tại — **không** phải bằng chứng nhân quả hay token attribution (LIME/SHAP/heatmap).
  4. Bộ tách từ `underthesea 9.5.0` cho PhoBERT có mức tương đương **`approximate`** so với tiền xử lý gốc của tác giả NEU và chỉ đọc tối đa **`128` token** (`HEAD`-window).
  5. Profile `uit` tiếp tục `unavailable` (chưa có checkpoint UIT); các con số `G4` chỉ phản ánh cấu hình phần cứng local đo được, không phải SLA đa máy.

---

# Báo cáo sửa F1/F2 PhoBERT — kiểm chứng mới ngày 2026-11-10

Phạm vi thực thi: `docs/CODEX_PHOBERT_F1_F2_FIX_PROMPT_2026-11-10.md`, nhánh
`webapp`, HEAD `0068fe640fdd90edbff578b008b6edfd1879ba99`. Các báo cáo R1–R4 bên
dưới là lịch sử; kết quả mới cho F1/F2 nằm trong phần này. Không commit, push,
deploy, train, tải pretrained weights hoặc thay đổi frontend/paper.

## Thay đổi F1 và bằng chứng checkpoint thật

- `services/inference/phobert_config.py` định nghĩa contract ngữ nghĩa dùng chung
  cho preparation, mọi đường resolver import và loader bundle format 2. Các giá
  trị được cố định theo specification của revision PhoBERT đã pin, cùng defaults
  được kiểm trực tiếp trong Transformers 4.44.2. Chi tiết từng trường và lý do nằm
  trong `MODEL_WORKFLOW.md`. Không suy ra giá trị mong đợi từ config đang xét hoặc
  checksum tự khai. Config chuẩn bị sẵn và file trong HF cache tại đúng revision
  cùng có SHA-256 `26d21a304fdea8fada88e7c6b7c7fef15c902c690bfb0fa47f60bdb61c68307a`;
  hash chỉ là provenance, contract ngữ nghĩa mới quyết định tương thích.
- `scripts/model_prepare_phobert.py`, `scripts/model_import_phobert.py` và
  `services/inference/registry.py` dùng validator chung. Import kiểm trước khi
  tính version/reuse, cấp phát model hoặc tạo staging. Giữ kiểm model ID, revision,
  checksum khi có provenance; JSON đổi whitespace/order/metadata vẫn hợp lệ.
  Version/provenance ghi toàn bộ config, contract, validator hash và chế độ CPU
  FP32/eval. ViSoBERT format 1 không bị áp contract PhoBERT.
- `tests/inference/test_phobert_config.py` kiểm validator production trực tiếp,
  không thay bằng mock: 4 đường resolution (directory/file/source/cache), config
  6-head, activation, epsilon, decoder/cross-attention, các trường còn lại, CLI
  exit `1`, provenance giả, missing config và pointer/bundle không đổi khi fail.
  Fixture tiny encoder chỉ thay validator trong test cơ chế generic. Bỏ kỳ vọng
  production chấp nhận `layer_norm_eps` khác; giữ kiểm digest riêng.
- Test `test_real_phobert_config_rejection_and_valid_verify_only` dùng đúng
  `demo/model.pt` (`542458551` bytes, SHA-256
  `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`). Cả config
  6-head không provenance và có provenance/hash tính lại đều raise **ValueError**:
  `PhoBERT config mismatch for num_attention_heads: expected 12, got 6`.
  Guard xác nhận không tới model construction; model root tạm chưa được tạo.
- Sau hai ca âm, config đúng chạy verify-only thành công với cache HF tạm trống
  và socket bị chặn trong toàn bộ import: `status=verified_only`,
  `activated=false`, `inference_ready=true`, 207 keys, tokenizer roundtrip pass,
  parity batch 1/2/8 và đảo thứ tự pass, max logit difference
  `1.9073486328125e-06`. Không tạo model root/pointer. Version kiểm chứng tạm:
  `neu-phobert-mtl-ed-s42-e10-11a775370745`.

## Thay đổi F2 và bằng chứng export từ API sau restart

`test_real_phobert_checkpoint_import_and_fullstack_browser_smoke` giữ nguyên luồng
quick inference, import CSV, batch inference, review Sentiment độc lập, export lọc
và đầy đủ, restart API/worker, inference mới, desktop/mobile. Test bắt response
POST tạo full export từ chính UI, đối chiếu download link và bytes tải xuống với
GET trước restart. Sau restart lấy lại đúng path trên origin mới, kiểm HTTP 200,
CSV UTF-8 BOM, Content-Disposition, bytes bằng nhau, parse 3 dòng và nhãn/model
provenance. Sau thêm/phân tích dòng thứ tư, GET export cũ lại và kiểm snapshot vẫn
là 3 dòng với bytes nguyên vẹn. Không tạo export thay thế sau restart.

Bằng chứng lượt chốt:

- Export ID `1ccbe5cc-37ef-4041-a77e-5b22494d67a7`, path
  `/api/v1/exports/1ccbe5cc-37ef-4041-a77e-5b22494d67a7`, do UI tạo ở cổng `62906`.
- API/worker restart trên cùng runtime/SQLite, API mới ở cổng `49673`.
  GET cùng path trả **200** cả ngay sau restart lẫn sau append/inference.
- Snapshot SHA-256 `70415cdc8b9f72286dd9477244b085cf604591fb3d2d5dc342b4601a103d172e`,
  byte-for-byte equality ở cả hai lần. Snapshot 3 dòng; dataset hiện tại 4 dòng.
  Dòng đã review giữ Sentiment corrected/effective `3`, Topic effective `4`,
  prediction gốc, schema `neu-v1`, model ID/version/run/revision đúng.
- Không phát hiện lỗi storage/API; F2 chỉ sửa test và tài liệu.

## Lệnh thực chạy và kết quả chốt

Tất cả dùng `.venv` của workspace; các số dưới đây được chạy sau thay đổi code/test
cuối cùng, không dùng lại baseline của review trước.

| Lệnh | Kết quả |
|---|---|
| `.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference tests/test_research.py -q` | **109 passed, 2 deselected**, 16 warnings, 40.38s |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -q` | **163 passed, 2 deselected**, 17 warnings, 111.17s |
| `.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q --basetemp=C:\Users\Admin\AppData\Local\Temp\phobert-f1-f2-audit-i14n4rsc\real-final` | **2 passed, 163 deselected**, 3 warnings, 51.44s |
| `.\.venv\Scripts\python.exe -X utf8 scripts/model_status.py --model-root runtime/models --profile neu --load` | Exit **0**, `available=true`, `load_verified=true`, version production giữ nguyên |
| `git diff --check` | Exit **0**; chỉ cảnh báo chuyển line endings |

Không fail/skip. Hai real-model tests vẫn opt-in; mặc định chỉ deselect, không xóa
hoặc skip assertion. Warnings là Starlette/httpx, SentencePiece và Transformers
tokenization deprecation. Không rebuild frontend vì không đổi source/build
contract; browser dùng dist hiện có. Trong quá trình phát triển còn chạy nhóm
config/import (**53 passed, 2 deselected**) và lượt real-model trước bổ sung báo
cáo chẩn đoán (**2 passed, 158 deselected**); bảng trên là kết quả cuối cùng.

## Bảo toàn dữ liệu và giới hạn

Đã chụp checksum trước thực thi và đối chiếu lại: `runtime/models/neu/current.json`
cùng toàn bộ **14 file** thuộc bundle
`neu-phobert-mtl-ed-s42-e10-617f852a3fff` không đổi; checkpoint, prepared config và
provenance cũng không đổi. Các file có sẵn ngoài phạm vi sửa giữ nguyên checksum.
Import activating chỉ chạy với model root tạm; database/config/log/port test đều
cô lập, chỉ dừng process do tests tạo. Không restart app đang sử dụng.

Snapshot trước/sau và báo cáo JSON chẩn đoán lưu tạm ở
`C:\Users\Admin\AppData\Local\Temp\phobert-f1-f2-audit-i14n4rsc`:
`before.json`, `after.json`, `real-final/test_real_phobert_config_rejec0/{config-rejections.json,valid-verify-only.json}`,
`real-final/test_real_phobert_checkpoint_i0/export-persistence.json`.
Không còn tiêu chí F1/F2 chưa kiểm chứng. Lượt này không chạy lại đánh giá dataset
benchmark: verify-only ghi `dataset_verification=not_requested`. Giữ underthesea
`approximate`, OOF `reported/not audited`, NEU format 2 và UIT unavailable.

---

# Báo cáo sửa lỗi sau code review PhoBERT R1–R4 (2026-11-10)

Ngày 2026-11-10, Windows local, workspace `F:\DPL_NEU-ESC` (nhánh `webapp`). Thực thi toàn bộ yêu cầu sửa lỗi R1–R4 trong `docs/PHOBERT_REVIEW_FIX_PROMPT_2026-11-10.md`:
- **R1**: Chuẩn bị cấu hình encoder `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1` (`config.json` thuần cấu trúc, tuyệt đối không tải pretrained weights) qua `scripts/model_prepare_phobert.py` và `scripts/setup-local.ps1 -WithModelRuntime`; cho phép `scripts/model_import_phobert.py` chạy hoàn toàn offline kể cả khi Hugging Face cache trống (`--encoder-config` hoặc `source/encoder`), báo lỗi rõ nếu thiếu/sai cấu trúc, và đưa toàn bộ `encoder_cfg.to_dict()` vào `pipeline_digest` / `model_version` / `provenance.encoder_config`.
- **R2**: Tách rạch ròi trạng thái kiểm chứng dataset (`"not_requested"` khi không truyền `--data-dir` và `"passed"` khi kiểm chứng đầy đủ); đường dẫn `--data-dir` truyền tường minh nhưng thiếu/sai hash/thiếu cột/sai số dòng/sai logits/sai nhãn đều hủy ngay với mã thoát khác `0` và không tạo/đổi bundle; `services/inference/registry.py` từ chối manifest giả mạo trạng thái dataset fail/chưa pass khi được yêu cầu.
- **R3**: Tách `pipeline_digest` (weights, tokenizer, full `encoder_cfg.to_dict()`, preprocessing, `model_info`, `training_config`, `source_metrics`, `importer_sha256`) khỏi `verification_identity`; import lại có `--data-dir` sau bản import chưa kiểm chứng dataset sẽ tạo thư mục `versions/<new-version>/` bất biến mới, giữ nguyên version cũ và chỉ cập nhật `current.json` nguyên tử sau khi mọi kiểm tra pass; `--verify-only` không ghi `model_root` hay `current.json`, `--stage-only` không cập nhật `current.json`.
- **R4**: Mở rộng bài kiểm thử chấp nhận đầu-cuối opt-in `@pytest.mark.real_model` (`test_real_phobert_checkpoint_import_and_fullstack_browser_smoke`) chạy với `HF_HOME` tạm trống + `HF_HUB_OFFLINE=1` + `--encoder-config` chuẩn bị sẵn, kiểm chứng đầy đủ: Quick Analysis thật -> import CSV 3 dòng có metadata -> batch inference thật -> chỉnh sửa độc lập nhãn Sentiment trong `ItemDetail` (giữ nguyên Topic và prediction AI gốc) -> xuất CSV lọc (`review_status=partial`, 1 dòng) và CSV đầy đủ (3 dòng) -> khởi động lại API & worker tách process trên cùng runtime -> xác minh bền vững dữ liệu/review/export -> Quick Analysis sau restart -> batch inference sau restart (`4/4 kết quả đã lưu`) -> kiểm tra responsive desktop `1440px` và mobile `390px` trên workspace dataset sống (`/#/datasets/{dataset_id}`), `/#/research` và `/#/help` (khi UIT unavailable).

Giữ nguyên toàn bộ thay đổi chưa commit trước đó, checkpoint gốc `demo/model.pt` (`542.458.551` bytes, SHA-256 `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`), bundle hiện hành `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff` cùng `runtime/models/neu/current.json`, và tiến trình app local trên cổng `8765`.

## 1. Bảng xử lý findings R1–R4

| Finding | Trạng thái | File sửa/tạo chính | Regression chứng minh |
|---|---|---|---|
| R1 | Resolved | `scripts/model_prepare_phobert.py` (mới), `scripts/model_import_phobert.py`, `scripts/setup-local.ps1`, `docs/LOCAL_APP.md`, `docs/MODEL_WORKFLOW.md` | `test_r1_offline_import_with_empty_hf_cache_and_prepared_config` (chặn socket mạng + `HF_HOME` trống), `test_r1_missing_or_incompatible_encoder_config_fails_cleanly_without_moving_pointer`, `test_r1_prepare_phobert_config_offline_from_local_cache_and_validation` |
| R2 | Resolved | `scripts/model_import_phobert.py`, `services/inference/registry.py`, `docs/MODEL_WORKFLOW.md` | `test_r2_dataset_verification_semantics_and_strict_rejection` (7 tình huống: không `--data-dir` -> `"not_requested"`; CLI `--data-dir` không tồn tại; thư mục trống; sai SHA-256 CSV; sai alignment nhãn/hàng `val_set.csv`; sai thứ tự `val_ids` trong `logits.npz`; `--data-dir` hợp lệ pass) và kiểm tra cột `predictions.csv` trong `_evaluate_optional_data` |
| R3 | Resolved | `scripts/model_import_phobert.py`, `docs/MODEL_WORKFLOW.md` | `test_r3_reimport_verification_immutability_and_pointer_safety` (`--verify-only` không ghi `model_root`; import chưa verify -> `--stage-only` có `--data-dir` không đổi `current.json` -> activate tạo version mới bất biến, giữ version cũ, cập nhật `current.json` nguyên tử, đổi `logits.npz` tạo version mới) |
| R4 | Resolved | `tests/inference/test_phobert_import_and_preprocessing.py` | `test_real_phobert_checkpoint_import_and_fullstack_browser_smoke` (`@pytest.mark.real_model`): offline import thật, Quick Analysis, import CSV, batch inference, review độc lập Sentiment/Topic, export lọc & đầy đủ, restart API+worker tách process, post-restart Quick & batch inference, desktop `1440px` + mobile `390px` |

## 2. Lệnh kiểm thử thực tế và kết quả R1–R4

```powershell
npm.cmd --prefix apps/web run build
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference tests/test_research.py -q
.\.venv\Scripts\python.exe -X utf8 scripts/model_status.py --model-root runtime/models --profile neu --load
.\.venv\Scripts\python.exe -X utf8 scripts/model_status.py --model-root runtime/models --profile all
.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 scripts/model_import_phobert.py --source demo --encoder-config runtime/cache/phobert-base-v2 --data-dir data/cache/neu --verify-only --report-out runtime/validation/phobert-neu-verification.json
git diff --check
```

- **Chuẩn bị cấu hình encoder offline (`runtime/cache/phobert-base-v2`)**: đã tạo trước đó bằng `scripts\model_prepare_phobert.py --out runtime\cache\phobert-base-v2 --source demo` cho `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1` (`config_sha256`: `26d21a304fdea8fada88e7c6b7c7fef15c902c690bfb0fa47f60bdb61c68307a`, `checkpoint_verified: true`, `checkpoint_sha256`: `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`); trong lượt xác minh cuối cũng đã có unit test offline `test_r1_prepare_phobert_config_offline_from_local_cache_and_validation` pass.
- **Frontend build (`apps/web`)**: `tsc -b && vite build` exit `0`, `84 modules`, JS `351.84 kB` (gzip `104.42 kB`), CSS `27.97 kB` (gzip `6.51 kB`) trong `3.92s`.
- **Kiểm chứng checkpoint thật + dataset NEU (`--verify-only`, `runtime/validation/phobert-neu-verification.json`)**: exit `0`, `status: "verified_only"`, `model_version: "neu-phobert-mtl-ed-s42-e10-33b586a07240"`, `activated: false`, `dataset_verification.status: "passed"` trên `3.305` dòng validation (`strict_state_dict_keys: 207`, `parity.max_abs_logit_difference: 1.9073486328125e-06`, `offline_socket_blocked: true`; CPU FP32 processed Sentiment Acc `0.840242`, Macro-F1 `0.760056`, Topic Acc `0.802118`, Macro-F1 `0.664933`; đối chiếu FP16 lịch sử `100.00%` Sentiment / `99.94%` Topic; adapter `underthesea 9.5.0` trên `val_set.csv` thô trùng `96.52%` Sentiment / `95.46%` Topic so với processed).
- **Trạng thái runtime (`model_status.py`)**: `--profile neu --load` exit `0` (`available: true`, `load_verified: true`, giữ nguyên `model_version: "neu-phobert-mtl-ed-s42-e10-617f852a3fff"`); `--profile all` exit `2` như kỳ vọng (`neu` `available: true`, `uit` `available: false`).
- **Targeted inference + research (`tests/inference` + `tests/test_research.py`)**: **63 passed, 1 deselected** (`30.27s`).
- **Full-stack acceptance với checkpoint thật (`pytest -m real_model -q`)**: **1 passed, 117 deselected** (`47.68s`).
- **Full default test suite (`pytest -q`)**: **117 passed, 1 deselected** (`113.93s`), tổng cộng **118 ca pass** khi tính cả `real_model`.
- **`git diff --check`**: exit `0` (sạch lỗi khoảng trắng).

---

# Báo cáo tích hợp PhoBERT MTL-ED & cập nhật theo paper — đợt gốc (2026-11-10)

Ngày 2026-11-10, Windows local, workspace `F:\DPL_NEU-ESC` (nhánh `webapp`). Thực thi kế hoạch `docs/PHOBERT_WEBAPP_HANDOFF_2026-11-10.md`: tích hợp checkpoint thật `demo/model.pt` (`phobert-mtl_ed-s42`, `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1`, best epoch 10, `max_length=128`) vào `runtime/models/neu` (bundle format `2`), bổ sung adapter tách từ offline `underthesea==9.5.0`, và đồng bộ nội dung nghiên cứu/giao diện theo bản thảo `Springer_Nature_LaTeX_Paper/paper.tex`. Profile `uit` tiếp tục giữ nguyên `unavailable` vì chưa có checkpoint UIT riêng.

## 1. Checkpoint, bundle và tính toàn vẹn provenance

- **Nguồn checkpoint**: `demo/model.pt` (`542.458.551` bytes, SHA-256 `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`), `demo/model_info.json`, `demo/run/{config.json,metrics.json,logits.npz,predictions.csv}` và `demo/tokenizer/`.
- **Bundle đã nạp vào runtime**: `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff` (trỏ qua `runtime/models/neu/current.json`), `format_version: 2`, `architecture: "roberta"`, `len(tokenizer) == config.vocab_size == 64001`.
- **Parity batch/order**: sai khác logit tuyệt đối tối đa giữa batch size 1, 2, 8 và thứ tự đảo ngược trên CPU FP32 là `1.9073486328125e-06` (`< 1e-4`).
- **Provenance OOF trung thực**: `oof.status = "reported"`, `oof.audited = false` vì 30 checkpoint/prediction teacher không đi kèm trong `demo/`; hệ thống không tạo provenance giả.

## 2. Ba mức kiểm chứng inference NEU

1. **Đối chiếu FP32 CPU với FP16 T4 lịch sử trên dữ liệu đã tách từ sẵn (`*_set_processed.csv`)**:
   - Tập validation (`3.305` dòng): Sentiment `max_diff=0.051344`, `mean_diff=0.001059`, tỷ lệ trùng nhãn `100.00%`, Accuracy `0.840242` (lịch sử `0.840242`), Macro-F1 `0.760056` (lịch sử `0.760056`); Topic `max_diff=0.034556`, `mean_diff=0.000942`, tỷ lệ trùng nhãn `99.94%`, Accuracy `0.802118` (lịch sử `0.802118`), Macro-F1 `0.664933` (lịch sử `0.664518`).
   - Tập test (`6.613` dòng): Sentiment `max_diff=0.034852`, `mean_diff=0.001061`, tỷ lệ trùng nhãn `99.97%`, Accuracy `0.836383` (lịch sử `0.836080`), Macro-F1 `0.779974` (lịch sử `0.779627`); Topic `max_diff=0.037861`, `mean_diff=0.000939`, tỷ lệ trùng nhãn `99.97%`, Accuracy `0.793740` (lịch sử `0.793740`), Macro-F1 `0.635641` (lịch sử `0.634985`).
2. **So sánh adapter triển khai `raw -> underthesea 9.5.0` với `*_set_processed.csv` gốc**:
   - Adapter `underthesea_word_tokenize` (`format="text"`, ghim SHA-256 3 file `ws_crf_vlsp2013_20230727/{dictionary.bin,features.bin,models.bin}`, lazy-load khi inference) giữ nguyên text thô trong SQLite, không strip emoji/dấu câu/chữ hoa.
   - Do NEU gốc có một số quy tắc tách câu/dấu chấm khác (ví dụ `tp.hcm` -> `tp . hcm`), trên tập validation (`3.305` dòng) `underthesea 9.5.0` đạt trùng nhãn `96.52%` Sentiment (Acc `0.836611`, Macro-F1 `0.749203`) và `95.46%` Topic (Acc `0.794554`, Macro-F1 `0.648010`); trên tập test (`6.613` dòng) đạt trùng nhãn `96.72%` Sentiment (Acc `0.830939`, Macro-F1 `0.770619`) và `96.02%` Topic (Acc `0.785725`, Macro-F1 `0.617434`). Vì vậy manifest ghi `preprocessing.equivalence = "approximate"` và hiển thị cảnh báo rõ ràng trên UI.
3. **Benchmark CPU thực tế (`runtime/validation/phobert-neu-benchmark.json`)**:
   - Máy đo: AMD64 Family 25 Model 80 (16 luồng logic, `torch` 8 threads), `torch==2.14.1+cpu`, `transformers==4.44.2`, `underthesea==9.5.0`.
   - `cold_first` (1 dòng đầu tiên, gồm nạp model + bộ tách từ): `5,447 s` (`0,18 dòng/s`, RSS `1.256,8 MiB`, peak working set `1.723,0 MiB`).
   - `warm_single` (1 dòng): `61,7 ms` (`16,21 dòng/s`, RSS `1.256,8 MiB`).
   - `batch_10`: `213,6 ms` (`46,81 dòng/s`, RSS `1.268,0 MiB`).
   - `batch_100`: `1,643 s` (`60,86 dòng/s`, RSS `1.283,5 MiB`).
   - `batch_500`: `8,859 s` (`56,44 dòng/s`, peak working set `1.723,0 MiB`).

## 3. Lệnh kiểm thử và kết quả

```powershell
npm.cmd --prefix apps\web run build
.\.venv\Scripts\python.exe -X utf8 scripts\model_import_phobert.py --source demo --model-root runtime\models --profile neu
.\.venv\Scripts\python.exe -X utf8 scripts\model_status.py --model-root runtime\models --profile neu --load
.\.venv\Scripts\python.exe -X utf8 scripts\model_status.py --model-root runtime\models --profile all
.\.venv\Scripts\python.exe -X utf8 scripts\model_benchmark.py --model-root runtime\models --profile neu --text-file <file> --out runtime\validation\phobert-neu-benchmark.json
.\.venv\Scripts\python.exe -m pytest tests\inference tests\test_research.py -q
.\.venv\Scripts\python.exe -m pytest -m real_model -q
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

- Frontend build (`apps/web`): `84 modules`, JS `351,84 kB` (gzip `104,40 kB`), CSS `27,97 kB` (gzip `6,51 kB`), exit `0`.
- `tests/inference` + `tests/test_research.py`: **58 passed** (`14,21 s`).
- `@pytest.mark.real_model` (`test_real_phobert_checkpoint_import_and_fullstack_browser_smoke`): **1 passed** (`25,61 s`), chứng minh import `demo/model.pt` thật, chạy API + worker tách process, Quick Analysis thật, import CSV + batch inference thật và kiểm tra UI Playwright ở cả desktop `1440px` và mobile `390px`.
- Full default suite (`pytest -q`): **112 passed, 1 deselected** (`86,59 s`), tổng cộng **113 ca pass** không lỗi.

---

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
