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
