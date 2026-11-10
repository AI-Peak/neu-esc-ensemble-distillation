# Fix review PhoBERT import và hoàn thiện nghiệm thu model thật

Bạn đang làm việc trong repo `F:\DPL_NEU-ESC`, Windows, PowerShell. Hãy thực thi sửa lỗi trong tài liệu này đến khi đạt tiêu chí nghiệm thu; không chỉ đưa ra đề xuất. Nếu không có quyền đọc/sửa repo hoặc chạy terminal, nói rõ ngay.

## 1. Bối cảnh và phạm vi

Webapp đã tích hợp PhoBERT MTL-ED cho NEU với importer, bundle format 2, adapter underthesea, registry và UI. Review mới xác nhận model thật chạy được nhưng phát hiện ba lỗi ở quy trình import/cài đặt và một khoảng trống kiểm thử end-to-end.

Chỉ sửa các vấn đề R1–R4 bên dưới cùng code/tài liệu/test trực tiếp liên quan. Không làm lại webapp, không mở rộng tính năng nghiên cứu, không train lại, không tải teacher ensemble, không push code/weights, không deploy. Không sửa paper LaTeX.

Trước khi sửa:

- Đọc AGENTS.md nếu có, `git status`, diff hiện tại và code thực tế. Nhánh ở lần review là `webapp`, HEAD `0068fe6`; có nhiều file modified/untracked của lượt triển khai trước. Những thay đổi này phải được giữ.
- Không reset, checkout đè, clean hoặc xóa các file untracked để có working tree sạch. Không commit/amend khi chưa được yêu cầu.
- Đọc `docs/PHOBERT_WEBAPP_HANDOFF_2026-11-10.md` để hiểu kiến trúc; tài liệu này thu hẹp phạm vi công việc mới vào findings review.
- Đọc `scripts/model_import_phobert.py`, `services/inference/registry.py`, `services/inference/preprocessing.py`, `scripts/setup-local.ps1`, `docs/MODEL_WORKFLOW.md`, `tests/inference/test_phobert_import_and_preprocessing.py`, `tests/conftest.py` và E2E tests hiện có.
- Số dòng ở review có thể thay đổi. Tìm theo hàm/hành vi, không sửa mù theo line number.

## 2. Trạng thái và bằng chứng đã có

- Checkpoint: `demo/model.pt`, 542458551 bytes.
- SHA-256: `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`.
- PhoBERT revision: `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1`.
- Profile NEU: 4 sentiment, 10 topic; checkpoint seed 42, epoch 10, max_length 128.
- Bundle ở lần review: `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff`, current pointer đang trỏ vào bundle này. Đọc lại pointer trước khi thao tác.
- Bundle hiện tại có report processed validation và raw adapter validation; không được kết luận bundle này chưa kiểm dữ liệu chỉ vì importer có thể bỏ qua kiểm chứng trong tình huống khác.
- Adapter underthesea 9.5.0 được đánh dấu `approximate`; OOF provenance là `reported`, `audited: false`. Giữ cách trình bày trung thực này.
- ViSoBERT format 1 vẫn cần tương thích; UIT chưa có checkpoint riêng và phải tiếp tục unavailable.
- Review đã chạy: 58 tests inference/research pass; 1 opt-in real-model browser test pass; frontend build pass; `model_status --profile neu --load` pass. Đây là baseline, không được báo như kết quả sau sửa.
- `.venv` hiện tái sử dụng system-site-packages. Kết quả pass trên máy hiện tại không chứng minh cài mới không phụ thuộc cache hoặc package toàn cục.

## 3. R1 — Import thất bại trên máy không có cache PhoBERT

### Hiện tượng đã xác nhận

`scripts/model_import_phobert.py` gọi `AutoConfig.from_pretrained("vinai/phobert-base-v2", revision=PHOBERT_REVISION, local_files_only=True)` nhưng source `demo` chưa có encoder config và setup/hướng dẫn chưa chuẩn bị nó.

Với cache Hugging Face trống, lời gọi này phát sinh OSError vì thiếu `config.json`. Máy hiện tại chạy được nhờ cache có sẵn.

### Yêu cầu sửa

1. Tách rõ chuẩn bị tài nguyên với import/inference offline. Chọn cách triển khai gọn nhất: chuẩn bị config đúng revision ở bước setup rõ ràng, rồi truyền đường dẫn local vào importer; hoặc đóng gói config đã xác minh cùng source nếu phù hợp repo. Không đoán config chỉ từ tensor shapes.
2. Bước chuẩn bị có thể dùng mạng nhưng chỉ lấy config cần thiết từ revision đã pin, không tải toàn bộ pretrained weights. Ghi nguồn/revision/checksum và kiểm config phù hợp checkpoint.
3. Importer phải dùng được khi cache Hugging Face trống, miễn là source/config đã chuẩn bị đủ. Không ngầm tải config trong request API, worker hoặc thao tác inference.
4. Nếu thiếu config, báo lỗi có chỉ dẫn thực thi cụ thể; không để người dùng chỉ nhận traceback khó hiểu.
5. Ghi nhận đầy đủ config thực dùng trong bundle/inventory/version identity, không chỉ `model_type` và `vocab_size`. Kiểm tương thích model/tokenizer bằng các kiểm tra đang có.
6. Cập nhật quy trình cài mới trong MODEL_WORKFLOW/LOCAL_APP và setup script nếu có liên quan. Một người có checkpoint + source assets và môi trường mới phải làm theo được.

### Test bắt buộc

- Test import với cache HF rỗng và config local đã chuẩn bị; không monkeypatch AutoConfig theo cách vô tình bỏ qua lỗi cache này.
- Test thiếu config, config sai loại hoặc không phù hợp: lỗi rõ, không publish/activate, pointer cũ không đổi.
- Sau chuẩn bị, chặn mạng và xác minh import/load/inference hoạt động. Không xóa cache thật của người dùng để test; dùng cache/env tạm hoặc subprocess được cô lập.

## 4. R2 — Dữ liệu kiểm chứng sai vẫn cho publish/activate

### Hiện tượng đã xác nhận

Trong `_evaluate_optional_data`, khi một processed CSV thiếu hoặc sai SHA-256, code trả `{"executed": false, "reason": ...}`. Importer vẫn đặt `verification.passed = true`, publish và activate.

Review dùng synthetic source + một thư mục `data_dir` tồn tại nhưng trống: report ghi thiếu `train_set_processed.csv`, song registry vẫn báo available. CLI còn chuyển đường dẫn `--data-dir` không tồn tại thành `None`, làm mất thông tin người dùng đã yêu cầu kiểm dữ liệu.

### Yêu cầu sửa

1. Định nghĩa rõ ba trạng thái: không yêu cầu kiểm dataset; yêu cầu và kiểm thành công; yêu cầu nhưng thiếu/sai dữ liệu hoặc comparison thất bại.
2. Khi caller truyền `data_dir` hoặc người dùng chỉ định `--data-dir`, đường dẫn không tồn tại, thiếu file, hash sai hay dữ liệu không hợp lệ phải làm import fail với exit nonzero. Không tự chuyển sang chế độ không kiểm.
3. Chốt semantics mặc định CLI rõ ràng, nhất quán với API Python. Có thể để dataset verification optional khi không truyền đường dẫn, nhưng phải ghi `not_requested`/trạng thái tương đương. Không mô tả đã kiểm historical/raw quality nếu chưa chạy. Không thêm cờ bypass để nuốt lỗi kiểm chứng được yêu cầu.
4. Trước khi đánh giá historical logits, kiểm shape, row count, IDs/order và label arrays tương ứng; không chỉ so mảng theo vị trí rồi mặc định khớp.
5. Khi có đánh giá raw adapter, xác minh nguồn raw CSV và alignment với processed CSV/IDs. Không nhận file raw tùy ý cùng số dòng rồi dùng nhãn processed để tính chất lượng mà không kiểm.
6. Nếu dữ liệu được yêu cầu không hợp lệ, không publish version hoàn chỉnh, không đổi pointer cũ, không để staging rác. Cleanup chỉ trong staging của thao tác hiện tại.
7. Báo cáo phải phân biệt structural/checkpoint parity, historical dataset verification và raw adapter comparison. Có thể giữ inference readiness riêng, nhưng không dùng một `passed: true` mơ hồ thay cho những kiểm tra chưa thực hiện.

### Test bắt buộc

- data_dir không được truyền: semantics optional đúng như tài liệu, không claim historical pass.
- Explicit data_dir không tồn tại; thư mục trống; thiếu CSV; CSV sai hash: đều fail, pointer cũ và bundle cũ còn nguyên.
- Historical logits sai shape/IDs/order/labels; raw CSV sai nguồn hoặc alignment: fail trước khi publish.
- Đường dữ liệu hợp lệ tạo report đúng trạng thái và nguồn hash.
- Có regression ở CLI để không mất explicit data-dir intent khi parse arguments.

## 5. R3 — Import lại bỏ qua yêu cầu kiểm chứng mới

### Hiện tượng đã xác nhận

Khi `published.exists()` và không verify_only, importer validate bundle cũ rồi trả `already_installed`, có thể activate ngay. `_evaluate_optional_data` không được gọi.

Do đó lần đầu import không có dataset, lần sau cung cấp `--data-dir` sẽ không bổ sung kiểm chứng. Review thay verifier bằng một hàm ghi nhận lời gọi và xác nhận nó không được gọi, trong khi kết quả vẫn `activated: true`.

### Yêu cầu sửa

1. Idempotency không được bỏ qua yêu cầu verification mới. Khi explicit data_dir được truyền, phải chạy kiểm chứng trên input đã xác minh hoặc chứng minh có report cache phù hợp chính xác với nguồn dữ liệu, logits và verifier hiện tại.
2. Metadata/config/metrics/verification inputs thay đổi phải được phát hiện; không trả provenance cũ chỉ vì weights/tokenizer giống nhau. Tách identity pipeline inference và identity verification nếu cần, nhưng thiết kế phải rõ và có tests.
3. Ưu tiên bundle version đã publish là immutable. Nếu cần lưu report cập nhật, tạo version/revision mới hoặc report có ID/hash riêng tham chiếu chính xác bundle. Không sửa in-place metadata/manifest mà các run cũ đang tham chiếu.
4. Chỉ activate sau khi các kiểm tra được yêu cầu thành công. Thất bại phải giữ pointer đang dùng, kể cả khi version đích đã tồn tại và pointer hiện đang trỏ version khác.
5. `--verify-only` không sửa runtime model-root/current pointer; `--stage-only` không activate. Giữ lại hành vi idempotent cho trường hợp source và yêu cầu kiểm chứng thực sự giống nhau.
6. Response import lần đầu/lặp/verify/stage có trường nhất quán cho trạng thái kiểm chứng; caller không phải đoán report bị thiếu là đã pass hay bị skip.
7. Cập nhật hướng dẫn: người dùng biết cách chạy kiểm chứng bổ sung cho model đã cài, và kết quả được lưu ở đâu.

### Test bắt buộc

- Lần 1 import không dataset; lần 2 truyền dataset hợp lệ: verifier thực sự chạy và report được lưu theo thiết kế.
- Lần 2 truyền dữ liệu sai: import fail; không activate bundle đích và không thay pointer đang dùng.
- Đổi một verification input liên quan: không reuse stale report.
- Import lại cùng input và yêu cầu: idempotent, không ghi đè/xóa version cũ.
- verify-only/stage-only không thay current pointer trong cả nhánh mới và nhánh already-installed.

## 6. R4 — Hoàn thiện acceptance flow với checkpoint thật

### Khoảng trống hiện tại

`test_real_phobert_checkpoint_import_and_fullstack_browser_smoke` đã chạy model thật cho Quick Analysis và CSV batch, mở Research/Help, kiểm mobile home. Tuy nhiên chưa thao tác review, export hoặc restart dù comment mô tả luồng có review/export.

### Yêu cầu bổ sung

Mở rộng opt-in real_model test hoặc thêm test riêng, dùng checkpoint thật, API/worker riêng process, runtime tạm và cổng riêng:

1. Import CSV tiếng Việt tối thiểu hai dòng có metadata, chạy inference thật; xác nhận prediction có model ID/version của bundle đã kiểm.
2. Mở chi tiết một dòng, sửa/xác nhận sentiment hoặc topic; kiểm hai task độc lập và AI prediction gốc không bị ghi đè.
3. Xuất CSV và đọc file thực tải về. Kiểm raw text/metadata giữ nguyên, nhãn AI/nhãn review và model/run/revision provenance chính xác; kiểm filter nếu flow có chọn xuất tập lọc.
4. Restart các process do test tự tạo trên cùng runtime; kiểm dataset, prediction và review còn tồn tại; kiểm export trước restart không bị thay nội dung.
5. Chạy thêm câu hoặc batch nhỏ sau restart, xác nhận model thật được nạp và worker xử lý bình thường.
6. Kiểm ít nhất một màn hình có dữ liệu/kết quả thật ở mobile 390px, không chỉ trang home. Desktop 1440px; không page errors hoặc body overflow.
7. UIT vẫn unavailable. Thiếu model/resource có thông báo đúng; không fallback sang synthetic predictor.
8. Cleanup process trong finally, giữ log chẩn đoán khi thất bại. Không tắt app trên cổng 8765 của người dùng hoặc thao tác database thật để làm test.

Giữ marker `real_model` opt-in. Default CI không tự tải hoặc yêu cầu checkpoint thật. Không dùng synthetic model hay monkeypatch production registry cho acceptance này; các regression mechanics riêng vẫn dùng tiny fixtures để chạy nhanh.

## 7. Trình tự triển khai và kiểm thử

1. Xác nhận từng finding trên code hiện tại. Nếu đã được sửa từ sau review, nêu test/bằng chứng cụ thể thay vì sửa lại.
2. Viết regression thể hiện R1/R2/R3; chạy trên trạng thái trước sửa khi khả thi để xác nhận tests bắt đúng lỗi.
3. Sửa R1–R3 với phạm vi nhỏ, giữ hợp đồng ViSoBERT v1 và registry/worker hiện có. Kiểm sớm tests hiện tại để tránh regression.
4. Hoàn thiện R4. Không chỉ đổi comment hoặc hạ assertion để test xanh.
5. Cập nhật tài liệu và report kết quả mới; giữ số liệu lịch sử có nhãn ngày rõ, không biến chúng thành số đo lượt này.
6. Chạy targeted tests, build frontend nếu cần browser test, real-model acceptance và full default suite. Không chạy lặp full suite nếu không có thay đổi/failure mới.

Lệnh tham khảo, điều chỉnh theo file mới nhưng phải ghi chính xác lệnh thực chạy:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference tests/test_research.py -q
npm.cmd --prefix apps/web run build
.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 scripts/model_status.py --model-root runtime/models --profile neu --load
git diff --check
```

Test cài sạch/cache sạch dùng thư mục tạm. Không xóa cache đang dùng hoặc thay HOME/CODEX_HOME. Nếu cần biến môi trường cache, đặt trong subprocess test và khôi phục sau đó. Setup resource download là thao tác riêng với inference, không cần tải lại checkpoint đã có.

Không cần benchmark lại 500 dòng hoặc đánh giá lại toàn bộ test set khi thay đổi chỉ là quy trình import; chỉ làm khi code inference/preprocessing thay đổi hoặc có regression cần điều tra. Không tune preprocessing/tolerance theo test set.

## 8. Tài liệu cần cập nhật và tiêu chí hoàn thành

- MODEL_WORKFLOW/LOCAL_APP có quy trình từ source checkpoint đến bundle trên máy/cache sạch, gồm chuẩn bị encoder config và các chế độ verification.
- VALIDATION_REPORT có bảng R1–R4: lỗi, thay đổi, regression chứng minh, kết quả lệnh thực chạy. Sửa tên test/lệnh sai nếu thấy; không ghi các test chưa thực hiện là pass.
- Checkpoint nguồn còn nguyên SHA-256. Model bundle đang phục vụ không bị sửa in-place hay mất report đang có.
- R1: không phụ thuộc cache ngầm; import offline sau chuẩn bị thành công.
- R2: explicit dataset sai bị từ chối, không publish/activate.
- R3: yêu cầu kiểm chứng mới không bị nhánh idempotent bỏ qua; failure không đổi pointer.
- R4: model thật đi qua predict → review → export → restart → predict, có assertions trên dữ liệu/provenance thực.
- ViSoBERT v1 regression pass; NEU real-model pass; UIT unavailable đúng thực tế.
- Không sửa/xóa dữ liệu người dùng, không train/push/deploy, không làm giả provenance hoặc kết quả kiểm thử.

Khi trả lời cuối, trình bày các lỗi đã sửa, file chính, lệnh và kết quả thực tế, hạn chế còn lại. Nếu có phần chưa chạy được, nêu rõ lý do và tác động; không gọi toàn bộ nhiệm vụ hoàn tất khi còn thiếu tiêu chí bắt buộc.
