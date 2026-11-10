# Kế hoạch tích hợp checkpoint PhoBERT và đối chiếu paper

Ngày lập: 2026-11-10. Workspace: `F:\DPL_NEU-ESC`. Đây là kế hoạch bàn giao cho chat mới; chưa triển khai các thay đổi bên dưới.

## 1. Mục tiêu và phạm vi

Đưa checkpoint PhoBERT MTL-ED hiện có vào Feedback Workspace để phân loại thật văn bản tiếng Việt ở profile NEU: một encoder, hai đầu sentiment/topic. Hoàn thành luồng nhập câu/CSV → phân tích → lọc → rà soát → xuất CSV → restart vẫn giữ dữ liệu. Đồng thời sửa thông tin sản phẩm và báo cáo để phù hợp paper LaTeX mới nhất.

Giữ React + FastAPI + worker riêng + SQLite; local CPU là mục tiêu đầu tiên. Giữ giao diện và design system hiện có. Không train lại, không tải 30 teacher, không deploy hosting, không push weights lên GitHub. UIT vẫn có schema và báo cáo nhưng chưa được bật inference khi chưa có checkpoint riêng. Không dùng checkpoint NEU cho UIT.

## 2. Trạng thái đã kiểm chứng

| Hạng mục | Bằng chứng |
|---|---|
| Git | Nhánh `webapp`, HEAD `0068fe6`; đã chứa `origin/main` `a0e61bf`. Fetch gần nhất không có commit main mới. Kiểm tra lại khi thực thi. |
| Checkpoint | `demo/model.pt`, 542458551 bytes; file local bị gitignore. |
| SHA-256 checkpoint | `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8` |
| Nội dung weights | Đã đọc bằng `torch.load(..., map_location='cpu', weights_only=True)` trong `.venv-modelcheck`; dict 207 tensors, 135601166 phần tử, tất cả hữu hạn. |
| Kích thước | Embedding `[64001,768]`; position embedding `[258,768]`; heads sentiment `[4,768]`, topic `[10,768]`. |
| Metadata | `demo/model_info.json`: PhoBERT-base-v2, MTL-ED, seed 42, best epoch 10, max_length 128. |
| Backbone revision | `vinai/phobert-base-v2@86cd7fd4c148980922ac11a2cf5e257f2ba639e1`. |
| Tài nguyên | `demo/tokenizer/`; `demo/run/config.json`, `metrics.json`, `epochs.jsonl`, `predictions.csv`, `logits.npz`, log và kernel_info. |
| Giới hạn xác minh | Đọc tensors thành công chưa chứng minh đúng logits, tokenizer, preprocessing hoặc chất lượng checkpoint. Dung lượng khớp log không thay cho hash xác thực nguồn. |
| Registry hiện tại | `runtime/models` trống; cả NEU/UIT unavailable. Registry chỉ chấp nhận ViSoBERT + raw text + manifest format 1 có OOF audit. |
| Runtime | Launcher dùng `.venv`, khác môi trường `.venv-modelcheck` đã dùng để kiểm tra weights. Cần xác minh dependency ở đúng môi trường launcher. |
| Kiểm thử cũ | Sau merge: 91 tests pass, chưa chạy E2E/Windows lifecycle trong lượt đó. Báo cáo 105 tests ở ngày 06/11 là lịch sử, không coi là kết quả của thay đổi mới. |

Các tài liệu cũ nói không có weights/logits hoặc chưa có webapp đã lỗi thời. Không dùng những câu đó để phủ nhận file thực tế.

## 3. Điều chỉnh hướng sản phẩm theo paper

Nguồn nội dung chính: `Springer_Nature_LaTeX_Paper/paper.tex`. Đối chiếu số liệu với CSV và code phân tích; nếu không khớp thì ghi rõ, không tự sửa paper cho khớp app.

| Nội dung paper | Tác động lên webapp |
|---|---|
| Sections 2.2–2.3: student có cùng kiến trúc plain MTL; lúc inference chỉ chạy student | Giữ inference một model. Không thêm teacher ensemble, SMART, MLM, gamma hoặc số teacher thành nút chỉnh lúc dự đoán. |
| Dataset section: PhoBERT cần segmented text; NEU dùng file processed của tác giả, UIT mới dùng underthesea 9.5.0 | Không gán underthesea 9.5.0 là pipeline NEU gốc. Phải kiểm chứng riêng đường raw text → segmentation → PhoBERT. |
| Kết quả NEU tốt ở metric tổng thể, nhưng Toxic F1 thấp hơn SMART | Định vị công cụ hỗ trợ đọc/rà soát phản hồi; không quảng bá như bộ phát hiện Toxic tốt nhất. Giữ sửa nhãn bằng người và không coi các câu không gắn Toxic là đã được xác nhận an toàn. |
| NEU 15 seeds, UIT 10 seeds; chọn epoch bằng validation macro-F1 | Tách benchmark nhiều seed khỏi checkpoint seed 42 đang chạy. Không dùng mean benchmark làm accuracy của phiên phân tích. |
| Holm correction: NEU 40, UIT 32, OOF/in-sample 8 comparisons | Tài liệu cũ ghi chưa hiệu chỉnh là lỗi thời. Không dùng p-value thô để tuyên bố khác biệt có ý nghĩa theo paper mới. |
| UIT: topic accuracy cải thiện so baseline mạnh nhất; sentiment không khác biệt có ý nghĩa sau correction | Không nói ED vượt mọi baseline trên mọi metric/dataset. UIT có báo cáo không có nghĩa UIT đã có model local. |
| Main results không áp logit bias; bias là phân tích phụ và không phải calibration | Bản tích hợp đầu không thêm bias, temperature hoặc đổi threshold để làm kết quả đẹp hơn. |
| Chi phí inference một student; chi phí teacher khoảng 16 GPU giờ | Đo CPU local riêng; không chuyển số giờ train hoặc tốc độ GPU paper thành lời hứa latency webapp. |

Hướng chính giữ nguyên: bộ phản hồi → phân tích → rà soát → xuất. Tab nghiên cứu là phụ, không đổi trang chủ thành dashboard trình diễn paper. Với artifact hiện có, ưu tiên PhoBERT NEU trước; giữ hỗ trợ ViSoBERT cũ cho artifact tương lai.

## 4. Bản đồ code cần đọc/sửa

| File | Trách nhiệm dự kiến |
|---|---|
| `services/inference/architecture.py` | Dùng lại Linear → SiLU → LayerNorm → hai heads; hỗ trợ config PhoBERT đã pin. |
| `services/inference/registry.py` | Validate theo format/backbone, load offline, preprocessing, cache, provenance và status. |
| `services/inference/export.py` | Giữ exporter training ViSoBERT format 1 tương thích; tái dùng tiện ích parity/publish khi phù hợp. |
| `services/inference/preprocessing.py` (mới) | Adapter raw ViSoBERT và segmented PhoBERT; lazy load, kiểm tài nguyên, lỗi có cấu trúc. |
| `scripts/model_import_phobert.py` (mới) | Import checkpoint có sẵn thành artifact versioned, kiểm chứng trước khi activate. |
| `scripts/model_verify_phobert.py` (mới hoặc tích hợp importer) | Kiểm logits/labels, source data, tokenizer và raw preprocessing; xuất report tái lập được. |
| `scripts/model_status.py` | Thêm `--profile neu|uit|all`, giữ mặc định all; load probe đúng profile. |
| `scripts/model_benchmark.py` | Đo warm/cold, throughput, peak RAM với preprocessing thực. |
| `services/api/main.py`, `services/worker.py` | Chủ yếu giữ contract; chỉ sửa khi metadata/error mới cần đi qua API/worker. |
| `services/research.py` | Mở rộng nguồn baseline và kết luận có nguồn, tách checkpoint metrics khỏi nghiên cứu. |
| `apps/web/src/App.tsx`, `QuickAnalysis.tsx`, `Workspace.tsx`, `ItemDetail.tsx`, types liên quan | Thông tin model, readiness, giới hạn preprocessing và nghiên cứu; giữ bố cục cũ. |
| `requirements-model*.txt`, setup scripts | Pin thêm segmenter và dependency sau khi kiểm Windows/Python tương thích. |
| `tests/inference/`, `tests/api/`, `tests/e2e/` | Regression format/backbone/preprocessing và một luồng dùng checkpoint thật tách khỏi test doubles. |
| `PRODUCT.md`, `docs/PROJECT_UNDERSTANDING.md`, `docs/MODEL_WORKFLOW.md`, `docs/LOCAL_APP.md`, `docs/VALIDATION_REPORT.md` | Cập nhật trạng thái và cách cài/chạy đúng thực tế. |

Tên file mới là đề xuất; có thể gộp nếu implementation gọn hơn mà vẫn giữ được các ranh giới kiểm chứng.

## 5. Thứ tự thực thi

### Bước A — Kiểm kê và chốt dữ liệu đầu vào

1. Đọc AGENTS.md nếu có, Git status, HEAD và tài liệu này. Giữ mọi thay đổi hiện có. Không reset/reclone mất webapp hoặc model local.
2. Kiểm file checkpoint bằng size + SHA-256 bên trên. Đọc metadata, config và metrics, kiểm chúng cùng dataset/setup/seed/best_epoch; không chọn seed mới theo test.
3. Lập inventory/hash cho tokenizer và run outputs. Kiểm khả năng đọc tokenizer với version Transformers thực tế: tokenizer được lưu từ Transformers 4.57.6, runtime repo đang pin 4.44.2. Kiểm tương thích trước khi quyết định upgrade; tránh nâng toàn bộ dependency vô cớ.
4. Tìm config encoder đúng revision trong cache. Nếu thiếu, chỉ tải config/tài nguyên cần thiết từ revision đã pin trong bước chuẩn bị; không tải pretrained weights để thay fine-tuned weights.
5. Lấy processed NEU CSV từ nguồn được runner pin (DATA_URL/AUTHOR_COMMIT), kiểm SHA-256 trong `demo/run/config.json` và runner. Lưu ở thư mục chuẩn bị gitignored. Không sửa dữ liệu gốc hoặc các hash để vượt kiểm tra.
6. Kiểm ID/order/label map của processed CSV với `logits.npz` và `predictions.csv`. Bản raw local dùng CRLF có thể cần bản copy LF để so checksum theo cơ chế `model_prepare_data.py`.

Đầu ra: inventory có hash, phiên bản runtime, nguồn config và các thiếu hụt cụ thể. Không kết luận provenance đã xác thực chỉ từ log.

### Bước B — Khôi phục model và kiểm chứng trên processed input

1. Khởi tạo encoder từ config đúng revision, không gọi tải weights; dùng kiến trúc `build_model` và schema NEU. Nạp checkpoint `weights_only=True`, CPU, `strict=True`; kiểm toàn bộ keys/shapes/finite, không chỉ hai heads.
2. Kiểm vocab/token IDs/padding và tokenizer PhobertTokenizer. ViSoBERT có ngoại lệ vocab +2; không áp máy móc ngoại lệ đó cho PhoBERT.
3. Dùng `use_fast=False`, truncation 128 kể cả special tokens, padding theo batch, eval + inference_mode; đối chiếu chính xác với runner.
4. So tokenizer sau save/reload: token IDs phải khớp; kiểm ảnh hưởng line endings ở `bpe.codes`, không sửa tokenizer tùy tiện.
5. Chọn tập validation cố định theo ID trước khi xem kết quả; so output `.pt` với bundle safetensors dự kiến theo batch 1/2/8, đảo thứ tự, độ dài hỗn hợp và truncation. Đây là export/reload parity.
6. So với historical logits trên processed validation; sau khi chốt pipeline mới chạy test để xác nhận checkpoint. Dùng labels/IDs đúng thứ tự, báo max/mean logit error, label agreement, accuracy/macro-F1/per-class F1.
7. Phân biệt CPU FP32 hiện tại và GPU FP16 lịch sử. Không đòi bitwise equality vô điều kiện, không nới tolerance sau khi xem test để che lỗi. Với export/reload FP32 có thể dùng tolerance hiện tại `atol=2e-5, rtol=1e-4`; với historical FP16 cần định nghĩa và ghi rationale riêng trước final test.
8. Kiểm mapping labels bằng data/README + profiles + runner; không suy ra thứ tự nhãn chỉ từ số lớp.

Nếu checkpoint không tái hiện hợp lý processed validation thì tìm lỗi config/tokenizer/architecture trước, chưa publish. Report phải phân biệt chứng cứ test kỹ thuật, parity historical và chất lượng raw deployment.

### Bước C — Chốt preprocessing cho văn bản người dùng

Đây là rủi ro lớn nhất. NEU processed của tác giả không chỉ thay dấu cách bằng dấu gạch dưới: tài liệu audit cũ ghi có các dòng khác ngoài segmentation. Paper cũng nói dữ liệu NEU đã được làm sạch và mở rộng viết tắt trước khi phát hành. Không khẳng định raw người dùng giống distribution benchmark.

1. Tìm pipeline gốc từ code/tài liệu tác giả đã pin. Nếu khôi phục được, pin công cụ, version, model resources và quy tắc normalization.
2. Nếu không khôi phục được đầy đủ, dùng adapter deployment xác định rõ; ứng viên đầu là underthesea 9.5.0 nếu chạy offline ổn trên Windows/Python mục tiêu. Đây là lựa chọn triển khai mới, không phải tuyên bố pipeline NEU gốc. Nếu không tương thích, ghi bằng chứng và chọn adapter khác có version cụ thể.
3. So raw-validation → adapter với processed-validation: exact text/token match, label agreement, metric/per-class delta. Dùng validation để chốt, không điều chỉnh theo test. Cố định adapter trước khi chạy đánh giá test.
4. Nếu không có historical equivalence, vẫn có thể hoàn thành demo local với adapter đã kiểm nhưng phải gắn trạng thái preprocessing `approximate`/tương đương và hiển thị giới hạn. Không gán benchmark paper cho đường raw này. Nếu lỗi kỹ thuật, chất lượng suy giảm chưa hiểu nguyên nhân hoặc tài nguyên thiếu thì chưa đánh dấu sẵn sàng.
5. Không bỏ emoji/dấu câu, lowercase hay đổi teencode theo suy đoán. Mọi biến đổi phải có version và test. Không tự động đoán văn bản có dấu `_` là đã segment.
6. Tách rõ đường internal processed input dùng để parity và đường production raw input được preprocess đúng một lần. Không mở công tắc bypass validation/preprocessing trong API public.
7. Giữ nguyên raw text trong database/export. Text đã preprocess chỉ là input nội bộ; token count/truncation tính sau preprocessing và trước truncation. Ghi policy trong manifest.
8. Test tiếng Việt có dấu, Unicode tổ hợp, emoji, xuống dòng, dấu `_`, câu ngắn/dài, teencode; xử lý output rỗng sau preprocessing như lỗi có thông báo. Kiểm lifecycle/cache/thread safety và không tải tài nguyên trong request.

Đầu ra: adapter + dependency pin + report giới hạn. Chỉ đưa copy hữu ích cho người dùng lên UI; tên thư viện/hash nằm trong chi tiết kỹ thuật.

### Bước D — Import artifact có version và provenance trung thực

Không dùng `demo/model.pt` như một ngoại lệ bỏ qua mọi validation. Import một lần vào bundle safetensors, rồi worker chỉ đọc bundle offline.

Layout đề xuất:

```text
runtime/models/neu/
  current.json
  versions/<version>/
    manifest.json
    model.safetensors
    encoder/config.json
    tokenizer/...
    preprocessing.json
    training_config.json
    source_model_info.json
    source_metrics.json
    parity.json
    verification.json
```

1. Giữ format 1 ViSoBERT và tests hiện tại; tạo format 2 cho checkpoint import có discriminated backbone/preprocessing/provenance. Dispatch theo version, reject version/backbone không hỗ trợ; không làm lỏng format 1.
2. Manifest format 2 phải có architecture, profile/schema/canonical labels, backbone/revision, model ID/version, max_length, preprocessing policy/resource hashes, original checkpoint hash, file inventory SHA-256, dependency versions và verification summaries.
3. Ghi seed 42, best epoch 10, selection criterion/score từ run; phân biệt runner hash lịch sử với hash code importer hiện tại. Kiểm cross-file consistency của config/metrics/model_info.
4. OOF targets và validation artifact chưa có local. Có thể lưu hash/30 sources được khai trong config/kernel_info với trạng thái `reported`, không tạo `validated: true` giả. Import dựa trên checkpoint + metadata consistency + inference verification; ghi rõ chưa independently audited training OOF. OOF không phải dependency inference runtime.
5. Mức bằng chứng training và readiness inference là hai trường riêng. Thiếu audit OOF không tự động có nghĩa weights không chạy được; ngược lại load được weights không chứng minh training provenance đầy đủ.
6. Validate file hashes, path traversal, symlinks, unknown/unlisted files, model/head dimensions, backbone/tokenizer và preprocessing. Tài nguyên segmenter nằm trong bundle hoặc resource store local được pin/hash và kiểm readiness.
7. Publish vào staging; strict load/reload parity + structural verification thành công mới rename version và atomic replace `current.json`. Lỗi không thay pointer cũ. Giữ checkpoint nguồn nguyên vẹn.
8. Model version phải đổi khi weights/tokenizer/preprocessing đổi, để prediction/run provenance phản ánh pipeline đã dùng. Re-import bundle giống nhau có thông báo/idempotency rõ, không tự xóa version cũ.
9. Cung cấp verify-only/stage-only nếu cần chẩn đoán; không thêm cờ `--skip-validation` hoặc fallback model random.

CLI mục tiêu (chỉ chạy sau khi script được triển khai):

```powershell
.\.venv\Scripts\python.exe scripts/model_import_phobert.py --source demo --model-root runtime/models --profile neu
.\.venv\Scripts\python.exe scripts/model_status.py --model-root runtime/models --profile neu --load
```

### Bước E — Nối registry, worker và status

1. Registry hỗ trợ PhoBERT/Roberta config và ViSoBERT/XLM-Roberta theo metadata đã validate. Dùng lại architecture, không viết forward gần giống nhưng khác runner.
2. Cache một model đang dùng; lazy load model/segmenter. Status không load torch nặng và không chạy download; kiểm dependency/tài nguyên bằng metadata nhẹ. Tách readiness kiểm cấu trúc khỏi load_verified để không hứa model đã nạp khi mới kiểm manifest.
3. Giữ item_id/revision_id, order, schema, softmax scores, truncation, model ID/version và dữ liệu lỗi đã sanitize. Không log raw feedback qua exception.
4. Lỗi integrity/schema/head/preprocessing config là lỗi artifact; lỗi tài nguyên tạm thời không poison cache vĩnh viễn. Kiểm cả API registry và worker registry riêng process.
5. Runtime có NEU ready/UIT unavailable là trạng thái hợp lệ. Thêm `--profile` vào model_status để lệnh kiểm NEU exit 0 khi NEU pass; all vẫn báo UIT thiếu như hiện tại.
6. Giữ API/worker lifecycle và SQLite isolation. Chỉ sửa storage nếu có trường bắt buộc; thông thường model version + manifest đủ để truy vết preprocessing.
7. Cài dependency vào `.venv` launcher thật và xác minh import/load ở đó. Regenerate lock đúng môi trường, không sao chép danh sách dependency từ môi trường khác.

### Bước F — Điều chỉnh UI và báo cáo theo paper

Phạm vi là hoàn thiện luồng hiện có; không redesign. Giữ Segoe UI, nền sáng/cobalt, native controls, layout và breakpoint trong DESIGN.md. Thao tác chính vẫn là Phân tích, sau đó Rà soát và Xuất.

1. NEU hiển thị model PhoBERT MTL-ED/version thật ở trạng thái/hướng dẫn. Phân biệt thiếu artifact, thiếu preprocessing resource, đang nạp, lỗi và sẵn sàng; vẫn cho import/manual review khi model thiếu.
2. UIT hiện rõ chưa có model phân tích. Giữ truy cập báo cáo UIT và dataset cũ; không biến báo cáo thành trạng thái sẵn sàng.
3. Với adapter không khớp pipeline lịch sử, ghi ngắn: "Văn bản được tách từ trước khi phân tích. Kết quả trên dữ liệu bạn nhập có thể khác benchmark nghiên cứu." Chi tiết kỹ thuật ở phần thu gọn, không rải đường dẫn/hash vào luồng chính.
4. Giữ cảnh báo softmax chưa calibration. Toxic là một nhãn hỗ trợ rà soát, không tự động kết luận về người viết; không tuyên bố ED tốt nhất cho Toxic. Giữ review hai task riêng và lọc/biểu đồ/export cùng nguồn nhãn.
5. Tab nghiên cứu hiện `services/research.py` chỉ lấy MTL và ED. Mở rộng để có baseline đúng phạm vi paper: NEU năm baseline/backbone và ED; UIT bốn baseline/backbone và ED. Có bộ lọc dataset/backbone/task/metric để bảng không tràn.
6. Lấy số liệu từ CSV đã kiểm, mean/sample std/count/seed IDs/source hash. Đối chiếu bảng LaTeX theo rounding. Không hardcode toàn bộ bảng từ paper mà bỏ provenance, và không bịa baseline single-task UIT.
7. Trình bày ba lớp thông tin riêng: benchmark lịch sử nhiều seed; metrics checkpoint seed 42 trên processed data đã kiểm; thống kê nhãn trong bộ phản hồi người dùng. Lớp cuối không phải accuracy vì thường không có ground truth.
8. Tóm tắt ED: teacher 30 models chỉ ở training; mỗi dòng train có 6 held-out predictions; student là một MTL model. Giữ giải thích ngắn, phần nghiên cứu chi tiết có thể mở rộng.
9. Nếu hiển thị significance, tái tính/đối chiếu từ per-run data với đúng Welch + Holm families (NEU 40/UIT 32; ablation 8 riêng), không chọn riêng vài test để correction. Không có dữ liệu đủ thì không hiển thị p-value tự suy đoán. Không đưa bias paired uncorrected p vào family chính.
10. Ưu tiên core model trước phần mở rộng research. OOF/in-sample comparison, biểu đồ per-class và bias là phần sau nếu không đủ dữ liệu, nhưng copy và kết luận chính phải đúng ngay. Main inference giữ logits gốc, không bias.

### Bước G — Kiểm thử và nghiệm thu

| Nhóm | Trường hợp bắt buộc | Bằng chứng |
|---|---|---|
| Import | Sai source hash, tokenizer/config không khớp, head sai, NaN/Inf, thiếu file, staging lỗi, import lặp | Tests cô lập, pointer không bị thay khi thất bại. |
| Registry | ViSoBERT v1 vẫn pass; PhoBERT v2 pass; version/backbone/schema không hỗ trợ bị reject; sửa file bị phát hiện | Regression tests; không bỏ các checks v1 để cho v2 đi qua. |
| Preprocessing | Một lần xử lý; câu biên; resource thiếu; raw gốc không đổi; count/truncation đúng | Unit/integration tests và report raw/processed validation. |
| Model thật | Strict load; checkpoint → safetensors reload; batch 1/2/8, reverse order; processed historical comparison | Report kèm SHA-256/model version/runtime; không gọi fixtures là evidence model thật. |
| API/worker | Quick analysis, CSV batch, cancel/retry, revision stale, review/export, worker restart | Runtime test riêng; API/worker process riêng và registry thật trong ít nhất một acceptance flow. |
| UI | NEU ready, UIT unavailable, loading/error; tiếng Việt dài; keyboard; mobile/desktop | Browser smoke ở 1440px và 390px; không overflow hoặc console error. |
| Offline | Setup xong thì model/config/tokenizer/segmenter không gọi mạng | HF offline flags và chặn/giám sát network trên inference flow, không dùng cache để che download ngầm. |
| Performance | Cold first, warm single, batch 10/100/500; peak RSS | Đo cùng preprocessing, không cam kết latency trước khi đo; điều chỉnh microbatch nếu cần, không đổi semantic. |
| Research | Mean/std/count/dataset/task đúng, không trùng seed, claim thống kê đúng scope | Tests nguồn dữ liệu và đối chiếu LaTeX/CSV. |

Chạy tests phù hợp sau từng phần; cuối cùng chạy build frontend và full suite một lần. Nếu thiếu browser/dependency, khắc phục nếu có thể và báo đúng phần chưa chạy. Không lặp full suite khi không có thay đổi mới.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/inference -q
npm.cmd --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Tests model thật cần opt-in/marker riêng vì checkpoint không ở Git/CI. Default suite không tải weights hoặc tạo fixture production. E2E hiện có dùng test double nên cần thêm một acceptance flow riêng chạy registry thật. Mọi test dùng runtime tạm, cổng riêng, không migrate/reset database người dùng.

Đo benchmark với file câu thử không nhạy cảm, lưu report ở `runtime/validation/`. Nêu CPU, thread settings, dependency versions, cold/warm definitions và batch sizes. Cuối cùng start/restart app qua scripts trên runtime chính khi không có job đang chạy, kiểm health worker và một câu mới; nếu có job, dùng runtime riêng và ghi rõ chưa restart bản đang sử dụng.

### Bước H — Tài liệu và bàn giao

1. Sửa PRODUCT.md và PROJECT_UNDERSTANDING.md: stack đã triển khai, checkpoint đã có, ưu tiên PhoBERT NEU, pipeline preprocessing đã chọn và giới hạn còn lại.
2. Sửa MODEL_WORKFLOW.md/LOCAL_APP.md: import command, model_status chọn profile, setup segmenter offline, file local gitignored, restore/rollback `current.json`, chuyển máy cần copy bundle.
3. Cập nhật claims thống kê cũ: paper hiện đã Holm-corrected; UIT sentiment không khác biệt có ý nghĩa với baseline mạnh nhất sau correction. Giữ báo cáo review cũ làm lịch sử, không sửa số test lịch sử thành kết quả hiện tại.
4. Ghi VALIDATION_REPORT mới: lệnh thực chạy, pass/fail/skip, hash, parity riêng từng mức, benchmark CPU, raw preprocessing limitation, OOF reported vs independently audited.
5. Không sửa paper LaTeX, upload model, publish dataset, commit/push hoặc deploy trong scope này nếu chưa có yêu cầu riêng.

## 6. Tiêu chí hoàn thành

- Checkpoint nguồn còn nguyên hash; bundle versioned được validate và activate nguyên tử.
- NEU nạp model thật, nhận câu raw mới và trả đủ sentiment/topic qua worker; UIT unavailable đúng thực tế.
- Strict load và export/reload parity pass; historical comparison có báo cáo, không lẫn với raw deployment quality.
- Preprocessing đã pin, chạy offline, provenance trung thực; chỗ không tái lập được pipeline NEU gốc được nêu rõ.
- Không có download/training/teacher ensemble trong request; không fallback giả.
- CSV → predict → review → export → restart hoạt động, giữ raw text, revisions và nguồn nhãn.
- App hiển thị checkpoint và benchmark đúng phạm vi paper; không gán mean nhiều seed cho model đang chạy hoặc tuyên bố ED tối ưu Toxic/UIT mọi metric.
- Bộ kiểm thử phù hợp và frontend build pass; có browser smoke model thật và số đo hiệu năng local. Các giới hạn chưa hoàn thành được liệt kê cụ thể.

## 7. Prompt để mở chat thực thi

```text
Hãy thực thi kế hoạch trong F:\DPL_NEU-ESC\docs\PHOBERT_WEBAPP_HANDOFF_2026-11-10.md.
Mục tiêu là tích hợp checkpoint local demo\model.pt vào webapp để profile NEU chạy PhoBERT MTL-ED thật, và cập nhật nội dung app theo paper LaTeX hiện có.
Đọc trạng thái thực tế trước khi sửa; giữ nhánh webapp, dữ liệu và thay đổi đang có. Không train lại, không push weights/code hoặc deploy. Giữ ViSoBERT v1 tương thích và UIT unavailable nếu chưa có artifact riêng.
Thực hiện đầy đủ kiểm chứng checkpoint, preprocessing, bundle, registry/worker, UI, tests và tài liệu. Chạy inference offline sau setup. Phân biệt benchmark paper, metrics checkpoint, và chất lượng trên raw input; không tạo OOF provenance giả hoặc dùng test doubles để tuyên bố model thật chạy.
Tự xử lý các lựa chọn kỹ thuật thường lệ theo kế hoạch; chỉ hỏi khi thiếu thông tin thực sự cần thiết. Báo kết quả thực đo và giới hạn còn lại.
```
