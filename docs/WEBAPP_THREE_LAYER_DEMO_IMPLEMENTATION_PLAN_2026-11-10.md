# Kế hoạch demo webapp ba lớp: Prediction, Interpretability, Decision Support

Ngày khảo sát: 2026-11-10, Asia/Saigon. Workspace: `F:\DPL_NEU-ESC`, Windows/PowerShell. Repository: https://github.com/AI-Peak/neu-esc-reproduction.

**Tài liệu bàn giao cho Gemini thực thi.** Người dùng đã đổi nơi thực thi từ chat Codex sang Gemini. Gemini cần quyền đọc/sửa repository và chạy kiểm thử local; tài liệu không phụ thuộc công cụ riêng của Codex hoặc lịch sử hội thoại. Lượt lập kế hoạch này chỉ khảo sát và tạo tài liệu này, chưa triển khai tính năng.

**Bổ sung phân công theo yêu cầu người dùng:** khuyến nghị Gemini điều phối cùng tối đa ba subagent theo mục I2–I7, nếu harness thực tế hỗ trợ. Mục tiêu là có kiểm thử và review độc lập với người viết implementation, đồng thời giữ một owner cho mỗi file. Nhiều agent không tự bảo đảm output tốt hơn; nghiệm thu vẫn dựa vào contract, bằng chứng và kết quả tích hợp. Bản cập nhật này chỉ sửa kế hoạch/prompt, không khởi động agent thực thi hoặc sửa source.

Câu chuyện demo: “Có một tập phản hồi sinh viên. Người phụ trách nên xem chủ đề nào trước, và kiểm tra kết quả AI bằng cách nào?”

Luồng đích: nhập CSV minh họa → inference thật → chủ đề cần chú ý → danh sách đã lọc → phản hồi có tín hiệu cần xem lại → điểm nhãn và thử bỏ một đoạn → người dùng sửa nhãn → thống kê nhãn hiệu lực cập nhật → xuất CSV snapshot.

## A. Hiện trạng đã xác minh và khoảng trống

### A1. Phạm vi bằng chứng của lần khảo sát

- Git: nhánh `webapp`, HEAD `a0cebad8d625c68ca4df755de27a249e2b8ba134`. `git status --porcelain=v1 --untracked-files=all` rỗng trước khi viết tài liệu. Khác baseline người dùng: worktree hiện sạch; lần thực thi vẫn phải khảo sát lại và giữ mọi thay đổi mới.
- Không tìm thấy `AGENTS.md` ở gốc repo, các thư mục con được quét ngoài `.git`/môi trường/dependencies, hoặc `F:\AGENTS.md`. Gemini kiểm tra lại trước khi sửa.
- Đã đọc phần liên quan trong `PRODUCT.md`, `DESIGN.md`, `docs/LOCAL_APP.md`, `docs/MODEL_WORKFLOW.md`, `docs/VALIDATION_REPORT.md`, `docs/PHOBERT_WEBAPP_HANDOFF_2026-11-10.md`; khảo sát frontend, API, storage, worker, inference và các regression tests ở A3.
- Chỉ đọc source/metadata và dùng Python standard library với `-B` để kiểm CSV validation. Không import `services.api.main`, không tạo `Store`, không mở/migrate database production, không khởi động app, inference hoặc test suite.
- Các số `163 passed, 2 deselected`, `2 passed, 163 deselected` và `load_verified=true` là **bằng chứng lịch sử** trong báo cáo, không phải kết quả mới của tài liệu này.

### A2. Artifact và validation thực tế

| Hạng mục | Đã quan sát | Giới hạn |
|---|---|---|
| Pointer production | `runtime/models/neu/current.json` → `neu-phobert-mtl-ed-s42-e10-617f852a3fff` | Không thay pointer; đọc lại khi thực thi. |
| Bundle | `runtime/models/neu/versions/neu-phobert-mtl-ed-s42-e10-617f852a3fff`, format 2, schema `neu-v1`, model ID `neu-phobert-mtl-ed-s42` | Đã đọc manifest, chưa load model hoặc hash lại toàn bộ bundle. |
| Checkpoint | `demo/model.pt`, 542458551 bytes | SHA-256 trong manifest và baseline: `754892a782dec389b041abc5f923573c091b8e2801dd0f7be57f718ae88700a8`; chưa tính lại hash file lớn trong lượt này. |
| Prepared config | `runtime/cache/phobert-base-v2/config.json`, 678 bytes | Chưa chạy lại validator/load. |
| Pipeline | `underthesea==9.5.0`, `word_tokenize(..., format="text")`, tokenizer slow, giới hạn 128 token gồm special tokens; CPU FP32/eval/inference mode cho PhoBERT | `equivalence=approximate`; không tương đương tuyệt đối pipeline nghiên cứu. |
| OOF | Manifest `status=reported`, `audited=false` | Không bổ sung tuyên bố audit. |
| UIT | Thư mục `runtime/models` chỉ có `neu`; không có pointer UIT | Chưa có checkpoint UIT; giữ nhập/rà soát thủ công. |
| Validation raw | `data/cache/neu/val_set.csv`: 3.305 dòng, cột `text,sentiment,classification` | Đã đọc số dòng, nhãn và hash; chưa chạy scores mới. |
| Validation processed | `data/cache/neu/val_set_processed.csv`: 3.305 dòng, cùng thứ tự nhãn sentiment/topic | Cột nhãn được lưu dạng chuỗi số như `0.0`; cần parse số nguyên hợp lệ, không dùng index chữ tùy ý. |
| Hash validation raw | `0b2567fe5374cf9b8d22de92ce71d3f9bfa036dffac46fa6f7a5650e85c81169` | Tính lại trong lượt khảo sát; khớp hằng số importer. |
| Hash validation processed | `948578e4b92df56117fd38d8edaee8d98f11adbd38611d6faee655008adea626` | Tính lại trong lượt khảo sát; khớp manifest. |
| Historical logits | `demo/run/logits.npz` tồn tại, 2486323 bytes | Là logits nghiên cứu/processed, không dùng thay scores của raw pipeline để chọn ngưỡng. |
| Báo cáo trên đĩa | `runtime/validation/phobert-neu-verification.json` ghi version `neu-phobert-mtl-ed-s42-e10-33b586a07240` | Khác pointer production. Bundle active có báo cáo validation nhúng nhưng không có đánh giá heuristic mới; phải tạo báo cáo mới có identity chính xác. |

`docs/PHOBERT_WEBAPP_HANDOFF_2026-11-10.md` là kế hoạch lịch sử: câu “runtime/models trống” đã lỗi thời. Các prompt sửa F1/F2 cũng là lịch sử, không phải backlog của lần triển khai này.

### A3. Bản đồ tái sử dụng và khoảng trống

| Code hiện tại | Semantics đã kiểm từ code | Hành động |
|---|---|---|
| `apps/web/src/Workspace.tsx` | Tổng quan, table phân trang, filter chung, tab `Cần rà soát`, nguồn nhãn, chọn run; Query invalidation sau job/review | Thêm bảng chủ đề trước biểu đồ; thêm filter/tín hiệu riêng. |
| `ItemDetail.tsx` | Native dialog, prediction và scores, sửa text tạo revision, duyệt riêng hai task, optimistic conflict, undo/history | Thêm lý do tín hiệu và phần khám phá thu gọn; không viết lại review form. |
| `QuickAnalysis.tsx` | Job tạm, polling 1 giây, thêm riêng text vào dataset | Tái sử dụng ý tưởng job tạm/polling, không gọi quick-analysis hai lần để so sánh. |
| `types.ts`, `api.ts`, `ui.tsx` | Kiểu dữ liệu, helper query/filterBody, ApiError, Loading/ErrorNotice/Badge/dialog focus | Mở rộng additive và dùng component hiện có. |
| `services/api/main.py` | `/api/v1`, Pydantic `extra=forbid`, lỗi `{code,message,details?}`; create run, jobs, summary, review, export | Mở rộng Filters và thêm API sensitivity. Không inference nặng trong request. |
| `services/storage/db.py::item` | `effective[task]` = review khác `unreviewed` của đúng revision/schema nếu có, nếu không dùng AI của view hiện tại. Reference không fallback thành effective. | Dùng lại một resolver nhãn cho list/summary/attention/export. |
| `Store.query_items` | Lọc backend, materialize tối đa 500 items rồi sort; hiện có nhiều truy vấn mỗi item, chưa phải SQL aggregation tối ưu | Tổng hợp ở backend trên cùng danh sách đã resolve một lần. Không fetch mọi item lên frontend, chưa cần viết lại toàn bộ bằng SQL. |
| `Store.summary` | Count sentiment/topic riêng và cross chỉ khi có đủ hai nhãn; trả `run_id` đúng giá trị filter, có thể null | Mở rộng response, giữ các trường cũ. |
| `Store.query_items` / `needs_review` | `review_count<2 OR error OR truncated OR max(sentiment_scores)<0.6 OR max(topic_scores)<0.6` | **Đã có heuristic**, khác giả định “chưa tự đánh dấu”. Giữ nguyên điều kiện legacy; bổ sung top-2 margin và trạng thái riêng. |
| Run và revision | Không chọn run: mọi item hiện tại + prediction từ run mới nhất, chỉ khi khớp revision; không fallback run cũ. Chọn run: membership/text/revision cố định theo `run_items`. | Áp dụng thống nhất cho cả ba lớp; thêm metadata giải thích view. |
| Review trong run lịch sử | Review lấy bản mới nhất của revision đó, không phải snapshot review tại thời điểm chạy; sửa review bị chặn nếu text revision đã cũ | Không gọi run lịch sử là snapshot mọi dữ liệu. Chỉ export là snapshot bất biến. |
| `Store.export/export_bytes` | CSV BOM, chống công thức Excel, lưu `csv_blob` bất biến cùng items/filter snapshot trong SQLite | Giữ header/cột và bytes export cũ; thêm filter signal nhưng chưa thêm cột CSV. |
| `services/worker.py` | Worker đơn, batch mặc định 8; priority quick=1/bulk=0; lease/attempt fencing; yield giữa batch; cancel/retry/recovery | Sensitivity dùng một job tạm hai item, xử lý cặp atomically trong cùng inference call. |
| `Store.cleanup/expire_quick` | TTL 900 giây sau terminal, job active được bảo vệ, cleanup định kỳ worker ≤30 giây; lock có thể trì hoãn | Dùng TTL cho sensitivity; cleanup/cascade/backup phải bao phủ metadata mới. |
| `registry.py` | Cache tối đa một model, status kiểm inventory/dependencies, predict khóa RLock, preprocessing + logits + softmax thật | Thêm identity guard và diagnostics tùy chọn; giữ đường predict mặc định. |
| `architecture.py`, `preprocessing.py`, `phobert_config.py` | Forward CLS → Linear → SiLU → LayerNorm → 2 heads; preprocessing pinned; validator semantic PhoBERT | Không đổi forward, label schema hoặc transform. Giữ F1. |
| `tests/api`, `tests/integration`, `tests/e2e`, `tests/inference` | Tests review/source/conflict, run/revision, export snapshot, jobs/leases/TTL, browser và model thật | Mở rộng quanh các ranh giới đã có; không coi test double là model thật. |

Cảnh báo thao tác: cuối `services/api/main.py` có `app = create_app()`, và `Store.__init__` tạo schema/cleanup. Chỉ import app trong môi trường đã đặt `FEEDBACK_RUNTIME` tạm. `tests/conftest.py` đã cô lập module-level app trước collection; giữ cơ chế này.

## B. Phạm vi làm và không làm

Làm theo thứ tự: (1) Chủ đề cần chú ý, (2) tín hiệu và lọc rà soát, (3) thử bỏ một đoạn để khám phá độ nhạy, (4) nối demo và kiểm chứng. Các bước 1–2 không đòi migration; bước 3 có migration additive nhỏ.

Giữ prediction thật, quick analysis, CSV import, batch inference, duyệt độc lập, export, cả schema NEU/UIT và bundle ViSoBERT format 1/PhoBERT format 2. Demo dùng NEU. Một dòng vẫn chỉ có một sentiment và một topic.

Không làm: LLM/chatbot/cloud, deploy, training/recalibration, LIME/SHAP, heatmap tự động, giải thích nhân quả, tách câu, multi-label/ABSA, clustering hay tự tóm tắt vấn đề, thay model để đạt câu chuyện đẹp, redesign giao diện, hệ thống quyền nhiều người dùng. Softmax là **điểm chưa hiệu chuẩn**, không phải xác suất đúng. Benchmark nghiên cứu không phải chất lượng của CSV demo.

## C. Quyết định sản phẩm và kiến trúc

### C1. Bộ lọc, nguồn nhãn và phạm vi dữ liệu chung

1. Dùng đúng `Store.item/query_items`, không dựng một bộ resolver khác cho tính năng mới. Tách helper thuần `selected_labels(item,label_source)` nếu cần giảm lặp, giữ kết quả cũ.
2. Mọi phép tổng hợp dùng cùng filter: `q`, sentiment, topic, review_status, review_signal mới, label_source, run_id. Phân trang/sort không thay số đếm; không tự bỏ filter sentiment để tạo tỷ lệ “đẹp”.
3. Không chọn run = `revision_scope=current`, `resolved_run_id` là run mới nhất. Chọn run = `revision_scope=run`, resolved ID bằng run chọn. Giữ `run_id` cũ (nullable) và thêm metadata mới, không đổi nghĩa trường cũ.
4. Đọc items, resolved run/status và tổng hợp trong cùng SQLite read transaction. Không gọi lại resolver N lần cho các biểu đồ. Giữ thông báo “Kết quả tạm thời” nếu run active; nếu lỗi/hủy/interrupted, nêu số dòng đã có kết quả và số lỗi/chưa xử lý.
5. `effective` hiển thị nguyên văn “Đã duyệt nếu có, còn lại AI”. Một dòng có thể kết hợp sentiment do người duyệt với topic AI. Không gọi đây là “toàn bộ nhãn đã duyệt”.
6. Sửa review làm mới item/list/summary/datasets và signals phụ thuộc review. Nguồn AI không thay đổi do sửa review, trừ membership khi có filter review. Chuyển run/refetch không tự nâng revision nháp hoặc xác nhận model mới.

### C2. Chủ đề cần chú ý

Đặt đầu phần Tổng quan, sau dòng tổng số và trước biểu đồ hiện có. Dùng bảng gọn; 10 chủ đề NEU hoặc 4 UIT tối đa, không thêm biểu đồ trang trí.

Với tập sau filter `F`, nguồn nhãn `L`, chủ đề `t`:

```text
topic_count(t) = số i thuộc F có L.topic = t
n(t) = số i thuộc F có L.topic = t VÀ L.sentiment hợp lệ
negative(t) = số i thuộc F có L.topic = t VÀ L.sentiment = key Negative/negative
toxic(t) = số i thuộc F có L.topic = t VÀ L.sentiment = key Toxic (nếu schema có)
negative_rate(t) = negative(t) / n(t), hoặc null nếu n(t)=0
missing_sentiment(t) = topic_count(t) - n(t)
```

- Xác định ID Negative bằng schema/key (`NEU=2`, `UIT=0` hiện tại), không hardcode `2` cho mọi profile. `Toxic` **không** cộng vào tử số Negative; vẫn nằm trong mẫu số sentiment hợp lệ. Hiển thị count Toxic riêng cho NEU.
- Chỉ thiếu topic: không xếp được vào chủ đề, đếm `missing_topic_count`. Có topic nhưng thiếu sentiment: có dòng chủ đề, tỷ lệ `—` nếu n=0, đồng thời hiện số chưa đủ nhãn. Thiếu cả hai chỉ thuộc nhóm missing topic, không đếm hai lần trong partition tổng.
- Lỗi/unprocessed không tự loại toàn dòng: với nguồn AI thường không đủ nhãn nên bị loại khỏi mẫu số; với effective, hai nhãn thủ công hợp lệ vẫn được tính. Cảnh báo lỗi vẫn giữ riêng. Reference không được dùng bù mẫu số.
- Thứ tự mặc định cố định: `negative_count DESC`, rồi `eligible_count DESC`, rồi `topic_id ASC`. Không thêm risk score. Giải thích: ưu tiên nhiều phản hồi tiêu cực; hòa thì ưu tiên nhóm có nhiều nhãn hợp lệ.
- Hiển thị các chủ đề có `topic_count>0`, kể cả 0 Negative; chủ đề không có dữ liệu không tạo dòng. Không negative ở bất cứ nhóm nào: “Chưa có phản hồi gán nhãn Tiêu cực trong phạm vi đang xem.” Không kết luận không có vấn đề.
- `n<5` gắn “Ít dữ liệu”; ngưỡng 5 là quy ước hiển thị, không phải mức đủ đại diện hay kiểm định thống kê. Vẫn hiện `1/1 · 100,0%` cùng cảnh báo, không giấu hoặc nâng hạng theo tỷ lệ. `n=0` không hiện 0%.
- Không tạo excerpt được lựa chọn theo score. Nút **Xem N phản hồi tiêu cực** đi tới list với topic + Negative, giữ mọi filter còn lại, page=1, source_row ASC (tie item_id ASC). Đây là đường dẫn chứng xác định và có thể kiểm tra.
- Nếu filter sentiment hiện tại khác Negative, negative_count=0 và nút disabled. Không tự thay filter để lộ dữ liệu ngoài phạm vi. Copy “Tỷ lệ trong phạm vi bộ lọc hiện tại”; khi có filter sentiment, thêm “Đang lọc cảm xúc; tỷ lệ không mô tả toàn bộ bộ phản hồi.”
- Nhãn chính: “Chủ đề cần chú ý”; cột “Chủ đề”, “Tiêu cực”, “Có đủ hai nhãn”, “Tỷ lệ tiêu cực”, “Toxic” (NEU), “Xem phản hồi”. Không ghi nguyên nhân, khẩn cấp hay đại diện toàn trường.

### C3. Tín hiệu tự động và trạng thái rà soát

Giữ nguyên `review_status=needs_review` và tab hiện có: đó là hàng chờ legacy gồm cả chưa duyệt, lỗi, truncation và top1<0.6. Không thay predicate bằng policy mới. Có thể đổi copy option thành “Cần rà soát (quy tắc hiện có)” và giải thích đầy đủ.

Thêm đối tượng **Tín hiệu model** tính từ prediction của view, tách hai task:

```text
Sắp scores giảm dần, hòa theo label_id tăng dần.
top1 = score cao nhất; top2 = score thứ hai; margin = top1 - top2.
LOW_TOP1 nếu top1 < top1_min.
SMALL_MARGIN nếu margin < margin_min.
flagged = LOW_TOP1 OR SMALL_MARGIN.
```

- Bắt đầu bằng `top1_min=0.60`, `margin_min=0.15` cho mỗi task của mỗi profile, trạng thái **experimental**. Top1 kế thừa mức heuristic đang có, margin là giá trị khởi đầu dễ giải thích; không tuyên bố tối ưu hoặc có cùng ý nghĩa thống kê giữa 4 và 10 lớp.
- Lưu trong file versioned mới `services/review_policy.json`, ID `review-signals-v1`, cấu hình riêng `neu-v1` và `uit-v1`, task riêng. Module `services/review_signals.py` validate rồi tính; API trả policy ID/hash/thresholds, frontend không tự tính lại. Thay policy đòi version mới và báo cáo mới, không có slider tự điều chỉnh trong demo.
- Điều kiện strict `<`, không `<=`; không làm tròn trước so sánh. Scores phải đúng số nhãn, hữu hạn, thuộc [0,1], tổng sai lệch tối đa 0.001 như worker. Sai dữ liệu → `unavailable/INVALID_SCORES`, thiếu prediction → `unavailable/NO_PREDICTION`, không coi là clear hoặc bịa 0.0. Không thay predicate legacy trong đợt này.
- `truncated` là warning đầu vào riêng; không là bằng chứng model phân vân. Item có thể vừa clear theo score vừa truncated. Lỗi inference và chưa có prediction cũng hiện riêng.
- Tính khi đọc, không thêm cột prediction/review, không backfill database, không chạy model để gắn cờ. Cùng prediction + policy luôn cho cùng tín hiệu; dùng chung helper cho detail/list/filter/summary/export snapshot.
- Tín hiệu là đặc tính dự đoán AI, không phụ thuộc `label_source`. Khi xem effective, copy “Tín hiệu tính từ dự đoán AI gốc của lần đang xem”.

**Sau rà soát:** scores và reasons không biến mất. Tách `review_relation` cho mỗi task: `unreviewed`, `current_prediction`, `manual`, `other_prediction`. `confirmed/corrected` với source_prediction_id khớp prediction đang xem → current_prediction; null → manual; khác → other_prediction. Đây là mô tả quan hệ, không sửa record review.

`addressed(task)` = review khác unreviewed của đúng text revision/schema và relation thuộc current_prediction/manual. `pending_signal_review` = có task flagged chưa addressed, hoặc truncated và chưa addressed đủ cả hai task. Lỗi/chưa inference đi qua trạng thái riêng/legacy, không bị gọi là score uncertainty.

Người đã duyệt đủ có thể vẫn thấy tín hiệu ở filter `model_uncertain`, nhưng rời filter `pending_signal_review`. Run mới/model mới: scores lấy từ prediction mới; review cũ của cùng revision vẫn ảnh hưởng effective đúng contract cũ, nhưng review gắn prediction cũ không tự xác nhận tín hiệu mới. Manual review không gắn prediction tiếp tục áp dụng cho cùng văn bản. Text revision mới không kế thừa prediction/review/signals của revision cũ. Xem run lịch sử giữ tín hiệu của prediction lịch sử.

**Bộ lọc mới `review_signal`:** `all`, `model_uncertain` (ít nhất một task flagged), `sentiment_uncertain`, `topic_uncertain`, `truncated`, `pending_signal_review`. Kết hợp AND với các filter cũ. Trong tab rà soát có nút “Có tín hiệu, chưa đối chiếu” dùng `review_status=all, review_signal=pending_signal_review`, chỉ đổi filter khi người dùng bấm; badge lý do và trạng thái người duyệt ở hai vùng riêng.

**Đánh giá ngưỡng:** chạy một công cụ offline mới trên `val_set.csv` raw bằng đúng bundle/pipeline đang deploy được copy vào model root tạm. Không đưa processed text qua underthesea lần nữa; không dùng logits.npz thay scores raw. Kiểm hash, row count, nhãn 0–3/0–9 và alignment với processed; không cần đọc/chạy test set cho công việc này.

Policy v1 được cố định trước phép đo; báo cáo descriptive, chưa tự tune. Với mỗi task và union: số hợp lệ, số lỗi inference, fraction flagged, error rate toàn tập, error rate nhóm flagged, error rate nhóm không flagged, error capture (`số lỗi bị flag / tổng lỗi`), lift (`error_rate_flagged / error_rate_all`), breakdown theo lớp và reason, truncation riêng. Mẫu số 0 → null. Gold là nhãn validation, không phải review demo. Ghi model/version/manifest hash, preprocessing/resource hash, policy/hash, split/hash, runtime và lệnh thực chạy. Validation từng dùng chọn epoch nên không trình bày như đánh giá độc lập cuối cùng.

Nếu thiếu artifact hoặc không đo được, giữ experimental và nêu “Chưa đánh giá ngưỡng trên validation của pipeline này”; không tuyên bố đã calibrated. Nếu kết quả kém, báo trung thực và giữ trong thử nghiệm, không đổi ngưỡng theo 24 câu demo. Tuning sau này cần protocol lựa chọn và tập kiểm tra ngưỡng tách riêng bên trong validation theo nhóm văn bản trùng, khóa trước khi đánh giá; không thuộc mốc demo này, tuyệt đối không chọn trên test set.

**CSV v1:** chưa thêm cột signal/threshold/sensitivity. CSV giữ header và semantics cũ; người dùng vẫn lọc theo signal rồi xuất đúng membership. Snapshot lưu policy đầy đủ/hash và filter đã dùng trong JSON nội bộ `exports.filters` (metadata dành riêng, không truyền ngược vào validator filter) cùng items đã resolve. GET export chỉ trả bytes cũ, không tính lại signal hoặc rerun filter. Nêu trên dialog xuất: “CSV giữ các cột hiện có; tín hiệu tự động không có cột riêng.”

### C4. Khám phá dự đoán: quyết định thực thi

**Cách tính:** một lần bấm tạo cặp baseline + variant. Luôn tính lại baseline từ đúng raw text revision đang xem bằng model active được ghim khi enqueue; chạy cả hai trong **một** `registry.predict` call với cùng loaded model/preprocessor, CPU FP32/eval/inference_mode. Không trừ điểm variant mới khỏi prediction lưu của model cũ. Nếu source prediction khác model active, hiện “Tính lại cả hai văn bản bằng model hiện tại; dự đoán đã lưu không thay đổi.” Ngay cả cùng model, gọi baseline là “Văn bản gốc · chạy lại cho thử nghiệm”.

Source revision phải còn là revision hiện tại khi submit. Xem historical run với cùng revision thì được thử; historical revision đã stale thì disabled “Chuyển về văn bản hiện tại để thử”. Nếu text đổi sau enqueue, job vẫn là snapshot cũ, response báo source_stale; không áp vào item mới, không tự hiển thị như kết quả hiện tại.

**Chọn đoạn chính xác:**

- Desktop: chọn trực tiếp trên vùng raw text chỉ chứa một text node, `white-space: pre-wrap`; lấy Range offsets UTF-16 chỉ nếu cả đầu/cuối nằm trong node đó. Không suy ra offsets từ `innerText`, DOM đã highlight hoặc chuỗi đã trim. Chọn qua nhiều vùng → hướng dẫn dùng ô nhập.
- Mọi thiết bị/bàn phím/mobile: ô “Nhập đoạn cần bỏ (đúng như văn bản gốc)” + danh sách occurrence dạng radio với ngữ cảnh trước/sau. Một occurrence được tự chọn; nhiều occurrence phải chọn rõ “Lần 1/3”, “Lần 2/3”…; không replace-all. Tìm cả occurrence chồng lấn nếu có, nhưng chỉ nhận biên grapheme hợp lệ.
- Request có `start_utf16`, `end_utf16` (nửa mở [start,end)), `selected_text`, revision ID/hash. Python chuyển offsets UTF-16 sang code point bằng bảng cumulative UTF-16; từ chối offset nằm giữa surrogate pair. Sau đó kiểm biên grapheme bằng `regex` `\X`; không cắt dấu tiếng Việt tổ hợp, emoji ZWJ, modifier hoặc cặp cờ.
- `regex==2026.9.29` đã có trong model lock, chưa có API requirements. Đưa đúng version này thành dependency trực tiếp API và cập nhật lock API có kiểm soát để endpoint không phụ thuộc tình cờ vào việc cài model. Không cần thêm frontend package; dùng `Intl.Segmenter` để preview, backend quyết định cuối cùng.
- Không NFC/NFD/casefold/trim/collapse whitespace trước so đoạn. So khớp byte/nội dung Unicode chính xác. Variant = `text[:start_cp] + text[end_cp:]`; giữ nguyên mọi ký tự còn lại, kể cả newline, nhiều space. Không chèn space tự động. Preview cho thấy nếu hai từ dính nhau; người dùng có thể chọn lại gồm khoảng trắng.
- Cả original và variant ≤5.000 code point. Selected span không rỗng/không chỉ whitespace. Variant trắng/rỗng hoặc không còn chữ/số (Unicode category L/N) → 422, không enqueue. Đây là validation riêng của experiment; không thay `check_text` hay import cũ.

**Truncation và tokenization:** slow tokenizer + underthesea chưa có raw-character offset mapping được kiểm chứng. Không tô “vùng model đã đọc” hoặc kết luận đoạn ở cuối chắc chắn bị bỏ qua. Cả baseline/variant trả token_count_before_truncation và truncated. Diagnostics mới so sánh chính xác chuỗi token IDs thực sự đưa vào forward (bỏ padding bằng attention_mask, giữ special tokens) của hai đầu vào. Thu bằng hook/nhánh tùy chọn ngay ở `run_logits`, không tokenize lại bằng pipeline khác; không trả token IDs ra UI/log.

- Token inputs bằng nhau: `model_input_equal=true`, giải thích “Sau tiền xử lý và cắt ngắn, đầu vào model của hai văn bản giống nhau.” Không kết luận đoạn không có nghĩa; có thể do segmentation hoặc truncation.
- Token inputs khác nhau và có truncation: “Bỏ đoạn có thể đổi cách tách từ và đưa phần văn bản phía sau vào giới hạn 128 token.” Không cô lập toàn bộ delta thành tác dụng riêng của cụm từ.
- Không làm offset mapping mới trong v1. Nếu không thu được diagnostics đáng tin cậy, không giả `equal`; phải fail test chức năng diagnostics trước nghiệm thu sensitivity.

**So sánh điểm:** với từng task và từng label ID `k`, `delta[k]=variant.scores[k]-baseline.scores[k]`. Bảng cùng nhãn gồm điểm gốc, điểm sau bỏ, chênh lệch (đơn vị điểm trên thang 0–1, hiển thị 3 chữ số, không gọi % xác suất đúng). Mặc định nổi bật label dẫn đầu baseline và label dẫn đầu variant; phần mở rộng hiển thị toàn bộ 4/10 nhãn. Không lấy `max_after-max_before` rồi gọi đó là thay đổi điểm một nhãn. Delta tính bằng số đầy đủ, chỉ làm tròn khi render.

Luôn hiện: **“Thử nghiệm độ nhạy: thay đổi đầu vào có thể làm thay đổi nghĩa; đây không phải bằng chứng chắc chắn về nguyên nhân model dự đoán.”** Không có nút “Áp dụng biến thể”; review tiếp tục thao tác trên item gốc.

### C5. Job, giới hạn, lưu tạm

- Tái sử dụng dataset tạm chứa đúng hai item và một run/job. Thêm một bảng metadata `sensitivity_experiments` để định danh cặp; không giả làm hai quick jobs độc lập. Dữ liệu tạm không xuất hiện trong danh sách dataset bền, summary, run history hoặc export của dataset gốc.
- Tạo temp dataset/items/run/job/context trong **một transaction**. Refactor hẹp helper storage cho phép dùng connection đang mở; không gọi nối tiếp các public method tự mở transaction rồi để lại orphan khi lỗi.
- Worker nhận diện bằng record trusted trong bảng mới. Đọc đủ hai item và gọi predict một lần dù `Worker(batch_size=1)`; không chia cặp qua batch khác nhau. Kiểm IDs, shape/finiteness, frozen model identity và diagnostics; commit cả hai hoặc không commit gì. Cancel/lease invalid sau inference → discard cặp, không publish partial comparison. Progress 0/2 → 2/2; lỗi có thể failed=2 nhưng không có kết quả so sánh.
- Job priority=1 như quick; bulk vẫn yield ở ranh giới batch. Không tăng số encoder hoặc chạy inference trong API. Giữ heartbeat trong lúc nạp model/chạy, attempt fencing, cancel queued/running, recover interrupted.
- Ghim identity gồm profile/schema/model_id/model_version + SHA-256 manifest + digest preprocessing spec/resource hashes. Registry check expected identity **bên trong cùng lock trước khi load/infer**, không chỉ status ở API. Artifact đổi khi job chờ → lỗi `MODEL_IDENTITY_CHANGED`; không tự activate model cũ hoặc dùng model khác để tiếp tục.
- Giới hạn vận hành ban đầu: một sensitivity job active cho mỗi source item; tối đa 4 sensitivity jobs active toàn runtime; tối đa 10 lần tạo mới/phút toàn runtime. Kiểm atomically trong transaction; idempotent retry cùng key không chiếm quota mới. Các con số là bảo vệ demo local, không phải SLA. Batch inference/quick giữ semantics cũ.
- Idempotency-Key bắt buộc với POST create: cùng key/body trả cùng job khi record còn TTL; khác body 409. Không có cache suy luận chia sẻ giữa các thí nghiệm trong v1. Polling ≈1 giây; không tự enqueue khi người dùng gõ.
- Hash idempotency phải bao gồm item_id trên path và toàn bộ body. Replay record còn sống được trả từ snapshot đã có, kể cả nguồn/model hiện đã đổi, kèm source_stale thích hợp; không enqueue lại hoặc kiểm quota như yêu cầu mới. Kiểm lại key trong transaction để chặn race. Lỗi readiness hiện tại không được làm mất khả năng đọc/replay kết quả cũ. UI giữ cùng key khi retry do mất response; chỉ tạo key mới cho một ý định chạy mới.
- Source phải là item của dataset bền, không phải quick item hoặc một experiment khác. Request không được tạo chuỗi experiment lồng nhau qua IDs temp.
- TTL 15 phút sau terminal, bao gồm completed/error/cancelled/interrupted; retry hợp lệ bỏ expires_at trong khi active. Cleanup có thể chậm theo nhịp worker/SQLite. Không lưu sang browser localStorage/sessionStorage; React Query dùng gcTime ngắn (≤60 giây) và bỏ result khi đóng/đổi item. Đây là xóa logical theo vòng đời app, không hứa xóa forensic khỏi WAL/backup hệ thống.
- Đóng panel/đổi lựa chọn: tăng generation, hủy polling và gửi cancel best-effort cho job active; không cho response cũ cập nhật panel mới. Nếu cancel không tới do mất mạng, TTL vẫn dọn sau terminal. Đổi selection không tự tạo job thay thế.
- Source dataset bị xóa: xóa temp dataset liên quan trong cùng transaction trước source; worker mất lease/job không được commit. Text/review mới không sửa kết quả experiment; text mới làm result stale, review mới chỉ cập nhật trạng thái nguồn.
- Retry dùng endpoint jobs cũ nhưng kiểm identity đóng băng + source revision còn hiện tại; không chạy lại cặp đã completed. Interrupted/cancelled/error chỉ retry khi chưa có cả hai predictions và guard còn đúng. Nếu model/revision đổi, tạo thử nghiệm mới có thông báo.
- Khi retry được chấp nhận, xóa lỗi/diagnostics của attempt thất bại, reset expiry như quick và giữ nguyên context nguồn/selection/execution. Lần hoàn tất mới không mang error_code từ lần trước. `source_stale` so sánh revision và text hash; model active đổi là thông tin riêng, không gọi văn bản stale chỉ vì model đổi.
- Không log raw text/selected_text/token IDs hoặc exception message chứa text; lỗi inference chỉ có mã + loại lỗi an toàn. Backup loại tất cả temp datasets và metadata cascade; không đưa experiments vào export CSV bền. Không gọi dịch vụ ngoài máy.

## D. Luồng UI và luồng dữ liệu

### D1. Luồng dữ liệu khuyến nghị

```text
Workspace Filters (run + label_source + review_signal + các filter cũ)
  -> GET items / summary
  -> Store: snapshot read -> resolve revision/prediction/review -> signals -> filter
  -> cùng rows: pagination cho list; counts/cross/attention cho summary
  -> UI Tổng quan / Danh sách

ItemDetail save review
  -> PUT review (expected_revision + expected_review_revision + source_prediction_id)
  -> append review history -> invalidate item/list/summary/datasets
  -> effective counts đổi; AI scores/signals giữ, pending-review relation đổi

SensitivityPanel chọn một occurrence -> preview exact variant -> bấm Chạy thử
  -> POST sensitivity-experiments (source identity + span + idempotency)
  -> validate -> transaction tạo temp dataset 2 item + run/job + context
  -> worker claim/lease -> registry identity guard -> cùng preprocess/forward cho cặp
  -> validate/commit cặp trong temp storage -> terminal/TTL
  -> GET experiment -> UI baseline/variant/same-label delta + warnings
  -> không mutate source item/predictions/reviews/summary/export

Export từ filter hiện tại
  -> resolve rows/signals một lần + policy snapshot -> CSV BLOB bất biến
  -> GET cùng export ID sau review/restart/append vẫn trả đúng bytes
```

### D2. UI, copy, responsive, accessibility

Giữ `DESIGN.md`: trắng/cobalt, Segoe UI/system font hỗ trợ tiếng Việt, component/control đang có, divider và bảng. Không đổi palette/font, không thêm animation trình diễn. Motion chỉ cho trạng thái và tôn trọng reduced-motion.

| Vùng | Hành vi chính | Trạng thái và copy |
|---|---|---|
| Tổng quan | Bảng chủ đề ở đầu, nguồn nhãn + bộ lọc vẫn chung | Loading dùng Loading; không có nhãn: “Chưa đủ nhãn để tính theo chủ đề. Chạy phân tích hoặc duyệt nhãn thủ công.”; lỗi có Retry; partial có badge và counts. |
| Danh sách | Hai nhóm badge: “Model phân vân: cảm xúc/chủ đề”, “Đầu vào bị cắt ngắn”; review badge giữ riêng | Missing scores: “Chưa có tín hiệu điểm”; không tô an toàn màu xanh khi unavailable. Filter “Tín hiệu model” độc lập filter trạng thái duyệt. |
| Tab rà soát | Giữ legacy, thêm nút/filter pending signal; giải thích tại sao một dòng vẫn nằm ở đây sau review | “Đã đối chiếu tín hiệu của dự đoán này” hoặc “Đã duyệt ở dự đoán khác”; không tự đổi nhãn người duyệt. |
| Chi tiết | Sau “Dự đoán AI gốc” và trước “Rà soát của bạn”, phần thu gọn “Khám phá dự đoán” | Lý do top1/margin trong details “Vì sao được đánh dấu?”; “Ngưỡng thử nghiệm, chưa hiệu chuẩn”. |
| Chọn đoạn | Exact input + occurrence radio luôn có; selection trực tiếp là tiện ích desktop | Empty: “Chọn hoặc nhập một đoạn có trong phản hồi”; invalid inline, focus ô lỗi; xem preview trước submit. |
| Chờ job | Nút “Chạy thử khi bỏ đoạn” disabled trong submit/active, có “Hủy thử nghiệm” | “Đang chờ worker”, “Đang nạp model”, “Đang so sánh hai văn bản”; không giả tiến độ %. |
| Kết quả | Original/variant text, leading label cả hai task, bảng cùng nhãn, cảnh báo cố định | Equal input có giải thích riêng; label không đổi vẫn là kết quả hợp lệ; không tô thay đổi như bằng chứng đúng/sai. |
| Cancel/lỗi/expired | Không render nửa cặp | “Đã hủy thử nghiệm”; “Thử nghiệm bị gián đoạn”; “Kết quả tạm đã hết hạn, chạy lại nếu cần”; Retry phải qua identity/source guard. |
| Text/model đổi | Loại bỏ kết quả đang hiển thị của selection cũ; thông báo nguồn đã đổi | Không tự chạy lại hoặc ép điểm cũ vào text mới. Model khác source thì baseline được tính lại và ghi rõ. |

Desktop 1440px/laptop 1024px: bảng chủ đề đủ cột, phần thử nghiệm trong dialog sẵn có, tránh modal lồng modal. Mobile 390px và 320px: bảng chủ đề thành từng dòng có nhãn số liệu; trước/sau xếp dọc; bảng điểm gọn hoặc scroll trong vùng riêng, không tràn body. Nút nhập đoạn/occurrence dùng được bằng cảm ứng; không phụ thuộc thao tác bôi đen khó trên điện thoại.

Heading có thứ bậc; button/link semantic cho dẫn chứng; radio có fieldset/legend; mọi select/input có label; nhãn lỗi liên kết aria-describedby. Loading/completion dùng aria-live polite không đọc lại toàn bảng mỗi poll. Focus khi lỗi đến vùng phù hợp; dialog Escape/focus restoration giữ `useDialogFocus`. Không chỉ dùng màu cho lý do/delta. Phím Tab/Enter/Space đi hết luồng mà không cần drag chọn chữ. Nếu text đang có nháp sửa, khóa tạo experiment tới khi người dùng lưu hoặc hủy nháp.

## E. Hợp đồng API, type và schema

Các đoạn JSON sau là **ví dụ hợp đồng với số liệu tổng hợp/điểm giả định để giải thích format**, không phải output model hoặc bộ demo đã chạy. ID ngắn là placeholder, implementation dùng UUID thật. Các field mới trong response hiện có là additive; body/query lạ vẫn bị từ chối như hiện tại.

### E1. Filters, Item, Summary

Thêm `review_signal` vào Pydantic Filters, TS Filters/defaultFilters, `query`, `filterBody`, session-state hydration, activeFilterCount và Bỏ lọc. Mặc định `all`. Filter không hợp lệ → HTTP 422 `INVALID_FILTER`. ExportInput kế thừa field này; `scope=all` bỏ nó cùng các filter membership khác, giữ run_id/label_source như hiện tại.

Item thêm `review_signals`; Prediction TS bổ sung `run_id`, `created_at` mà backend đã trả khi lấy item. Không nhét derived signals vào payload prediction đã lưu.

```json
{
  "review_signals": {
    "policy_id": "review-signals-v1",
    "policy_hash": "<sha256>",
    "experimental": true,
    "prediction_id": "p1",
    "sentiment": {
      "state": "flagged", "top1_label_id": 2, "top2_label_id": 0,
      "top1": 0.55, "top2": 0.40, "margin": 0.15,
      "reasons": ["LOW_TOP1"], "review_relation": "unreviewed"
    },
    "topic": {
      "state": "clear", "top1_label_id": 4, "top2_label_id": 2,
      "top1": 0.80, "top2": 0.10, "margin": 0.70,
      "reasons": [], "review_relation": "current_prediction"
    },
    "truncated": false,
    "pending_signal_review": true
  }
}
```

Đây là giá trị toán học minh họa, test equality ngưỡng phải dùng fixtures kiểm soát floating point; không suy ngưỡng từ số đã làm tròn ở UI. `state=unavailable` có top1/top2/margin/IDs null, reason NO_PREDICTION hoặc INVALID_SCORES. `truncated=null` nếu không có prediction. TS dùng union/nullable rõ, không ép `as` để che thiếu field.

GET `/datasets/{id}/summary?...` giữ tất cả trường cũ, thêm:

```json
{
  "resolved_run_id": "r1",
  "revision_scope": "current",
  "run_status": "completed",
  "attention": {
    "ranking_rule": "negative_count_desc,eligible_count_desc,topic_id_asc",
    "small_sample_threshold": 5,
    "negative_label_id": 2,
    "toxic_label_id": 3,
    "filtered_count": 9,
    "eligible_count": 7,
    "missing_topic_count": 1,
    "missing_sentiment_with_topic_count": 1,
    "topics": [
      {"topic_id": 4, "topic_count": 6, "eligible_count": 5,
       "negative_count": 3, "toxic_count": 1, "negative_rate": 0.6,
       "missing_sentiment_count": 1, "small_sample": false},
      {"topic_id": 2, "topic_count": 2, "eligible_count": 2,
       "negative_count": 1, "toxic_count": 0, "negative_rate": 0.5,
       "missing_sentiment_count": 0, "small_sample": true}
    ]
  },
  "review_policy": {
    "id": "review-signals-v1", "hash": "<sha256>", "experimental": true,
    "schema_id": "neu-v1",
    "sentiment": {"top1_min": 0.60, "margin_min": 0.15},
    "topic": {"top1_min": 0.60, "margin_min": 0.15}
  }
}
```

Invariant: `filtered_count = eligible_count + missing_topic_count + missing_sentiment_with_topic_count`; attention eligible bằng denominator.cross. UIT toxic_label_id/toxic_count=null để phân biệt “không có nhãn Toxic” với 0. ItemPage cũng thêm resolved_run_id/revision_scope để frontend không phải đoán current mode; `run_id` cũ giữ nguyên.

Detail cần thresholds: thêm GET `/review-policy?profile=neu` trả cùng resolved policy; profile lạ 422 `INVALID_PROFILE`. Không có API ghi policy. Query cache theo profile/policy hash; version/thresholds trong summary/detail phải khớp. Cấu hình policy hỏng là lỗi cấu hình, không âm thầm fallback.

### E2. Tạo và đọc sensitivity experiment

POST `/api/v1/items/{item_id}/sensitivity-experiments`, HTTP 202; header `Idempotency-Key: <uuid>` bắt buộc.

```json
{
  "revision_id": "rev1",
  "expected_revision": 1,
  "text_sha256": "<sha256-utf8-cua-raw-text>",
  "run_id": null,
  "source_prediction_id": "p1",
  "selection": {"start_utf16": 9, "end_utf16": 16, "text": "rất tốt"}
}
```

Ví dụ offsets hợp lệ cho raw text `Dịch vụ: rất tốt.`. Client có thể tính SHA-256 bằng Web Crypto; backend tính lại. `run_id=null` nghĩa view hiện tại; nếu có run ID thì phải thuộc dataset và revision đang xem. `source_prediction_id` bắt buộc có mặt nhưng nullable khi chưa có prediction; so với Store.item của view trong transaction. Prediction mới xuất hiện/đổi run từ lúc mở detail → 409 SOURCE_CONTEXT_CHANGED, refetch rồi người dùng bấm lại. Không nhận baseline scores, variant text hay model path từ client.

Response 202:

```json
{
  "experiment_id": "j1", "job_id": "j1", "status": "queued",
  "source": {"item_id": "i1", "revision_id": "rev1", "revision": 1,
             "text_sha256": "<hash>", "selected_run_id": null,
             "resolved_run_id": "r1", "prediction_id": "p1"},
  "selection": {"start_utf16": 9, "end_utf16": 16, "text": "rất tốt"},
  "baseline_text": "Dịch vụ: rất tốt.", "variant_text": "Dịch vụ: .",
  "execution": {"profile": "neu", "schema_id": "neu-v1",
                "model_id": "neu-phobert-mtl-ed-s42", "model_version": "<active-version>",
                "manifest_sha256": "<hash>", "preprocessing_sha256": "<hash>",
                "mode": "cpu-fp32-eval", "baseline_recomputed": true,
                "source_model_changed": false},
  "expires_at": null
}
```

GET `/api/v1/sensitivity-experiments/{experiment_id}` trả context trên và status/progress/error/source_stale/result. Trạng thái dùng cùng jobs: queued/loading_model/running/completed/completed_with_errors/failed/cancelled/interrupted. Chỉ completed có đủ cặp validated mới có result; các trạng thái khác result=null.

```json
{
  "experiment_id": "j1", "job_id": "j1", "status": "completed",
  "completed": 2, "total": 2, "failed": 0,
  "source_stale": false, "expires_at": "<UTC-ISO8601>",
  "error": null,
  "result": {
    "baseline": {"text": "<raw>", "prediction": "<Prediction day du ca 2 task>"},
    "variant": {"text": "<variant>", "prediction": "<Prediction day du ca 2 task>"},
    "model_input_equal": false,
    "comparison": {
      "sentiment": {
        "baseline_label_id": 2, "variant_label_id": 0,
        "scores": [
          {"label_id": 0, "before": 0.10, "after": 0.60, "delta": 0.50},
          {"label_id": 1, "before": 0.10, "after": 0.10, "delta": 0.00},
          {"label_id": 2, "before": 0.70, "after": 0.20, "delta": -0.50},
          {"label_id": 3, "before": 0.10, "after": 0.10, "delta": 0.00}
        ]
      },
      "topic": "<cung cau truc, du 10 nhan NEU hoac 4 UIT>"
    },
    "warnings": ["SENSITIVITY_NOT_CAUSAL"]
  }
}
```

GET luôn trả lại source/selection/execution đã đóng băng; ví dụ cuối rút gọn các trường đó để dễ đọc. Prediction dùng schema hiện tại gồm model/schema, sentiment/topic label_id+scores, token_count_before_truncation, truncated, warnings, duration_ms; không dùng string placeholder trong implementation. Warnings thêm INPUT_TRUNCATED_BASELINE/VARIANT, MODEL_INPUT_UNCHANGED, TOKEN_WINDOW_MAY_CHANGE theo diagnostics. source_stale là trạng thái nguồn hiện tại, không sửa snapshot bên trong result.

Cancel/retry: giữ POST `/jobs/{job_id}/cancel` và `/retry`; thêm guard riêng cho experiment ở C5. GET jobs thêm `kind: analysis|quick|sensitivity`; quick result cũ giữ nguyên Item, sensitivity result để null và đọc qua endpoint riêng, không trả nhầm baseline đầu tiên như quick result. Type mới `SensitivityExperiment` tách khỏi `Job.result` cũ; không mở union thành any.

### E3. Validation và lỗi

| HTTP / code | Khi nào | UI |
|---|---|---|
| 422 VALIDATION_ERROR | Sai shape/type/extra fields, thiếu header bắt buộc, expected_revision<1 | Lỗi có cấu trúc; không enqueue. |
| 404 NOT_FOUND | Item/run/experiment không có; experiment hết TTL hoặc source đã bị xóa | “Không còn kết quả tạm hoặc phản hồi nguồn”; không hứa phân biệt expired với ID chưa tồn tại. |
| 422 RUN_DATASET_MISMATCH | Run không thuộc dataset | Refetch/chọn run đúng. |
| 422 INVALID_EXPERIMENT_SOURCE | Source thuộc dataset tạm/experiment | Chọn phản hồi trong dataset bền. |
| 409 REVISION_CONFLICT | Revision/hash không khớp current hoặc view historical stale | Tải nội dung mới, giữ review draft theo flow cũ. |
| 409 SOURCE_CONTEXT_CHANGED | Source prediction ID khác view server | Tải lại dự đoán trước khi chạy. |
| 422 INVALID_SELECTION | Rỗng/whitespace, out-of-range, text không khớp, biên UTF-16/grapheme sai | Đánh dấu ô/chọn đoạn; details.reason dùng mã, không lặp toàn raw text. |
| 422 EMPTY_VARIANT / NON_LEXICAL_VARIANT | Bỏ hết/blank hoặc chỉ còn dấu câu/emoji không chữ số | Yêu cầu đoạn ngắn hơn. |
| 422 TEXT_TOO_LONG | Original/variant vượt 5.000 code point | Không cắt ngầm. |
| 409 MODEL_UNAVAILABLE | Profile không có bundle/dependencies hợp lệ | Giữ đọc/rà soát thủ công. |
| 409 IDEMPOTENCY_CONFLICT | Cùng key khác request | Dùng key mới chỉ cho ý định submit mới. |
| 409 EXPERIMENT_IN_PROGRESS | Item đã có experiment active | Trả existing_job_id, cho xem/hủy job đó. |
| 429 EXPERIMENT_LIMIT | Quota active/rate toàn runtime | details.retry_after_seconds nếu xác định được; không retry loop vô hạn. |
| 409 MODEL_IDENTITY_CHANGED / JOB_NOT_RETRYABLE | Retry sai version/manifest hoặc trạng thái không được retry | Tạo thử nghiệm mới có thông báo. |
| Job error_code MODEL_IDENTITY_CHANGED / INFERENCE_FAILED / INVALID_PAIR_RESULT | Lỗi sau khi đã nhận 202 | GET trả 200 với trạng thái terminal và error object an toàn; result=null, không biến thành request 500. |

HTTP lỗi dùng envelope hiện tại `{code,message,details?}`. Giữ `jobs.error` string an toàn cũ cho tương thích; endpoint experiment chuyển metadata lỗi thành `{code,message}`. Không mất generic cancellation/recovery error khi chuyển loại response.

### E4. Migration và tương thích

Không migration cho attention/signals/export filtering. Sensitivity thêm **MIGRATION_2**, không sửa MIGRATION_1 đã áp dụng:

```sql
CREATE TABLE sensitivity_experiments (
  job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
  temporary_dataset_id TEXT NOT NULL UNIQUE REFERENCES datasets(id) ON DELETE CASCADE,
  source_dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
  source_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  source_revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
  baseline_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  variant_item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
  context_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX sensitivity_source_item ON sensitivity_experiments(source_item_id);
CREATE INDEX sensitivity_source_dataset ON sensitivity_experiments(source_dataset_id);
CREATE INDEX sensitivity_created ON sensitivity_experiments(created_at);
```

context_json là schema version 1: source snapshot IDs/revision/text hash, selected/resolved run, source prediction identity, selection UTF-16 + code point, frozen execution identity, request hash, sanitized error_code nếu có. Baseline/variant text nằm ở temp revisions; không nhân bản toàn văn vào context/log. Experiment ID chính là job ID, không thêm queue thứ hai.

Phân biệt phần context bất biến (source/selection/execution/request hash) với phần attempt diagnostics/error. Chỉ worker/cleanup được sửa metadata attempt; không rewrite source snapshot khi review, text hoặc model thay đổi. Kết quả GET có thể thêm `active_model_changed` bằng cách đối chiếu identity hiện tại, nhưng không yêu cầu model active còn sẵn sàng để đọc kết quả đã lưu.

Store migration chạy từng version trong transaction và hỗ trợ khởi tạo đồng thời API/worker như trước. `/health.database_version` phải đọc version thực tế, không giữ hardcode 1. Code mới đọc DB v1 bằng migration additive; không hứa binary cũ hiểu experiment mới hoặc hỗ trợ downgrade. Không xóa dữ liệu để rollback: dùng backup và checkout phù hợp trong runtime mới.

Expiry xóa temp dataset → jobs/items/context cascade. Xóa source dataset phải xóa temp dataset liên quan trước khi FK source cascade, tránh để dataset tạm orphan không còn mapping. `Store.cleanup` cũng dọn idempotency operation `sensitivity` khi result job đã hết TTL. Idempotency chỉ bảo đảm trong vòng đời record; POST lại sau cleanup là một job mới. `backup_local.py` hiện xóa temporary datasets bằng FK ON và dọn idempotency không thuộc datasets/runs; thêm regression chứng minh table mới bị xóa theo, không giả định suông.

Không cho public mutation APIs chỉnh text/review/add/copy/run/export hoặc xóa riêng temp dataset/item của sensitivity qua ID đoán từ job: trả 409 `EXPERIMENT_READ_ONLY`, cancel qua jobs. Internal cleanup/delete-source được phép. Kiểm guard bằng table ownership, không dựa vào metadata do người dùng import; không ảnh hưởng quick-analysis cũ.

Giữ cột/header CSV, review history, prediction payload cũ, API hiện tại và export bytes. Mọi field mới response additive; filter mới phải đi xuyên list/summary/export, không bị `extra=forbid` chặn. Type Job/Item không buộc dữ liệu cũ phải có diagnostics mới. Không thêm metadata mới vào production bundle để phục vụ experiment; lưu identity trong DB tạm.

## F. Task triển khai theo phụ thuộc

Các tên module mới dưới đây là khuyến nghị cụ thể. Được điều chỉnh cách chia file nếu giữ đủ contract/tests và giải thích trong báo cáo. Không dùng cơ hội này để refactor toàn app hoặc xử lý lại prompt cũ.

### T00 — Chụp baseline và cô lập thực thi

- **Mục tiêu:** bảo toàn bản đang chạy tốt trước khi thay source.
- **File/module:** đọc Git, model pointer/manifest, `tests/conftest.py`, launcher; ghi bằng chứng vào thư mục audit riêng dưới `%TEMP%`, chưa sửa runtime production.
- **Tiên quyết:** đọc tài liệu này và AGENTS áp dụng; xác nhận workspace thật từ filesystem, không mặc định môi trường Gemini giống Codex.
- **Triển khai:** chụp HEAD/branch/status, staged/unstaged diff và danh sách/hash file modified/untracked ban đầu; không stash/reset/clean. Ghi SHA-256 checkpoint, prepared config/provenance, pointer và toàn bộ file bundle active. Ghi inventory production runtime read-only; nếu database đang hoạt động thì không so hash file đang có ghi như bằng chứng xâm phạm. Mọi test dùng runtime/model root/port tạm; `FEEDBACK_RUNTIME` phải được đặt trước mọi import app ngoài pytest. Không chạy setup/importer mặc định vào production.
- **Nghiệm thu:** có baseline và đường dẫn test root riêng; model identity được biết; mọi thay đổi có sẵn được nhận diện để tránh ghi đè; nếu app đang mở thì không dừng/restart nó.
- **Tests:** đọc `test_runtime_isolation.py` và chạy targeted khi bắt đầu test code; không cần chạy full suite chỉ để chụp baseline.
- **Rủi ro/giữ phạm vi:** import app tự migrate/cleanup; mọi lệnh Python có side effect phải dùng runtime tạm. Nếu có thay đổi đồng thời không thuộc task, dừng sửa vùng đó và báo người dùng, không tự revert.

### T01 — Tổng hợp chủ đề ở backend

- **Mục tiêu:** summary có attention đúng nhãn/filter/run mà không thêm fetch toàn dataset trên browser.
- **File/module:** `services/storage/db.py`, mới `services/analytics.py`, `services/api/main.py`; mới `tests/api/test_attention.py` (hoặc phần test có tên rõ trong file hiện có).
- **Tiên quyết:** T00.
- **Triển khai:** helper resolver nguồn nhãn; helper thuần aggregate_attention(rows, profile); dùng rows đã query một lần. Đọc resolved run metadata trong cùng snapshot; thêm attention/resolved_run_id/revision_scope/run_status theo E1. Không thay fields cũ hoặc sort/filter legacy. Tính denominator trên label hợp lệ, không exclude manual rows chỉ vì lỗi model. Evidence là route/filter list, chưa thêm endpoint snippets.
- **Nghiệm thu:** n=0→null; Toxic giữ riêng; tie xác định; schema UIT dùng negative=0; summary/list/export cùng membership; attention eligible = cross denominator. Với n<5 cảnh báo đúng; không đưa reference vào effective.
- **Tests:** table-driven thiếu 1/2 nhãn, lỗi + manual review, empty dataset/filter, mixed effective sources, Negative/Toxic, n=0/1/4/5, tie. Integration current/historical/new revision/new run partial, mismatch dataset/run 422. Kiểm filter sentiment làm tỷ lệ conditional đúng copy/metadata.
- **Rủi ro/giữ phạm vi:** N+1 hiện tại tối đa 500; chỉ đo và cải thiện nếu gây vấn đề thực, không thêm ORM/SQL engine hay rewrite storage trong task này.

### T02 — UI chủ đề và dẫn chứng

- **Mục tiêu:** mở Tổng quan là biết nhóm nào có nhiều phản hồi Negative trong phạm vi đang xem.
- **File/module:** `apps/web/src/Workspace.tsx`, `types.ts`, mới `TopicAttention.tsx`, `styles.css`; `tests/e2e/test_three_layer_demo.py` mới.
- **Tiên quyết:** T01.
- **Triển khai:** render bảng theo C2/D2 dùng labels từ profile; key topic_id. Dẫn chứng set topic/sentiment/source_row asc/page=1 và chuyển items, giữ nguồn/run/q/review filters. Disabled khi count=0. Không thêm fetch items?page_size=500. Query summary hiện có đã bị invalidate từ review/job, tận dụng thay vì local recompute.
- **Nghiệm thu:** click count=N → list total=N, đúng nguồn/run; sửa chỉ sentiment rồi đổi effective/AI cho kết quả dự kiến; 390px không tràn body; keyboard mở list được; no-label/partial/error không render bảng số giả.
- **Tests:** browser desktop/mobile dùng test registry có scores/labels kiểm soát; một case sửa topic làm item chuyển nhóm; một case clear filters. TypeScript build.
- **Rủi ro/giữ phạm vi:** người dùng lọc Negative có thể nhìn 100%; phải hiện rõ conditional denominator, không âm thầm bỏ filter.

### T03 — Policy tín hiệu và semantics tương thích

- **Mục tiêu:** đánh giá uncertainty riêng từng task, tách human review.
- **File/module:** mới `services/review_policy.json`, `services/review_signals.py`; `services/storage/db.py`, `services/api/main.py`; mới `tests/test_review_signals.py`, `tests/api/test_review_signals.py`.
- **Tiên quyết:** T00; tích hợp sau T01 để dùng chung resolver/snapshot.
- **Triển khai:** policy version/hash immutable trong một process; strict schema/threshold validation; tính top1/top2/margin/reasons và review_relation/pending. Thêm filter enum + `/review-policy`; Item/summary thêm data. Export lọc đúng rows, lưu resolved policy metadata nội bộ nhưng không đổi cột CSV. Giữ nguyên predicate legacy needs_review, kể cả trường hợp đã duyệt mà top1 vẫn thấp.
- **Nghiệm thu:** prediction/policy không đổi → reasons không đổi sau review; pending đổi theo relation, đúng khi source_prediction_id khác/null; no prediction không thành clear; invalid scores có trạng thái unavailable; legacy URL/filter cho cùng membership như trước khi thêm feature; export scope=all bỏ signal filter.
- **Tests:** top1 và margin tại/dưới/trên threshold, tie nhãn, label count/scores malformed/NaN, missing pred; confirm/correct/manual/unreview/undo; chuyển run/model, cùng revision hoặc revision mới. API list-summary-export parity khi kết hợp AND filters. Old CSV header/bytes unchanged khi tải lại sau đổi policy.
- **Rủi ro/giữ phạm vi:** không gộp pending mới vào needs_review; không xóa/ghi trạng thái review khi tính flag; không áp threshold của một schema vào schema khác.

### T04 — UI tín hiệu và hàng chờ đối chiếu

- **Mục tiêu:** người dùng chọn được dòng đáng xem và hiểu vì sao được gắn cờ.
- **File/module:** `Workspace.tsx`, `ItemDetail.tsx`, `types.ts`, `api.ts`, `styles.css`; `tests/e2e/test_three_layer_demo.py`.
- **Tiên quyết:** T03 và T02.
- **Triển khai:** Filters thêm default/hydrate cho session cũ; badge signal và review ở hai chỗ riêng; filter “Tín hiệu model”; nút pending ở tab review. Details hiển thị top1/top2/margin + thresholds/policy experimental, cảnh báo truncation riêng. Invalidate review relation sau save/undo/restore; không thay logic draft/source/conflict đã có. Bỏ lọc xóa cả filter mới; filterBody giữ field cho exported filtered scope.
- **Nghiệm thu:** reviewer duyệt một task không đánh dấu task khác đã duyệt; manual review và review từ run khác hiển thị rõ; filtered list có thể rỗng sau save và selection/next/page được xử lý hợp lệ; `all` mặc định cho session cũ.
- **Tests:** browser chọn model_uncertain vs pending khác nhau sau review; trạng thái copy khi không có prediction; save-next khi item rời filter; hai tab conflict không mất bản nháp; keyboard/mobile, build TS.
- **Rủi ro/giữ phạm vi:** không trình bày model_uncertain như detector sai nhãn/mỉa mai; không thêm confidence gauge hoặc phần trăm “độ chính xác”.

### T05 — Đo policy trên validation raw, không tune bằng demo

- **Mục tiêu:** có bằng chứng mức bao phủ và mức tập trung lỗi của heuristic đã khóa.
- **File/module:** mới `scripts/evaluate_review_signals.py`; test parsing/metrics bằng fixtures nhỏ; report JSON/Markdown trong test/audit runtime tạm; cập nhật báo cáo nghiệm thu sau triển khai.
- **Tiên quyết:** T03, có bundle copied read-only source trong model root tạm. Không phụ thuộc UI.
- **Triển khai:** CLI dự kiến `--model-root <temp> --profile neu --validation-csv data/cache/neu/val_set.csv --processed-validation-csv data/cache/neu/val_set_processed.csv --policy services/review_policy.json --out <temp>/review-signals-validation.json`. Chỉ cho split validation; validate hashes/order/labels. Chạy `ModelRegistry.predict` raw batch, frozen identity; không import checkpoint hoặc activate production. Tính metrics C3; report có counts/mẫu số và model/policy/runtime identity. Không chứa raw text hoặc teacher ensemble.
- **Nghiệm thu:** đủ 3.305 dòng hoặc báo rõ số failed, không âm thầm loại lỗi; policy dùng trong report đúng UI/backend; ngưỡng không bị chọn lại theo report hoặc 24 câu demo. Nếu chưa chạy được, đánh dấu “chưa đánh giá” và giữ experimental, không tạo số thay thế.
- **Tests:** metrics với zero errors/zero flags/zero correct, per-task vs union, parse `2.0` chỉ khi integer và finite, mismatched hash/row/labels, model identity đổi giữa batches → fail report không ghi success. Model thật chỉ chạy opt-in, tách khỏi default tests.
- **Rủi ro/giữ phạm vi:** raw validation khác phân phối feedback thật, checkpoint đã dùng validation chọn epoch; report là descriptive. T05 không chạy test set hoặc gọi importer `--data-dir` vì importer mặc định còn kiểm các split khác và có thể publish bundle.

### T06 — Selection validator và storage experiment

- **Mục tiêu:** một occurrence chính xác, Unicode an toàn, tạo cặp tạm atomically.
- **File/module:** mới `services/sensitivity.py`, `services/storage/db.py`, `services/api/main.py`, phần metadata của `services/inference/registry.py`, `requirements-api.txt`, `requirements-api.lock.txt`; mới `tests/test_sensitivity_selection.py`, `tests/api/test_sensitivity.py`.
- **Tiên quyết:** T00, contract C4/E2–E4; không cần đổi model.
- **Triển khai:** validator UTF-16→code point→grapheme, hash/source context, exact slice/variant validation; dependency regex pinned như C4. Migration2, helper insert dùng connection chung, trusted mapping, idempotency/quotas, GET context, readonly guards, delete/TTL/backup support. Endpoint create chỉ kiểm readiness/identity metadata rồi enqueue, không load torch/infer. Update health version thật.
- **Identity metadata:** thêm `ModelRegistry.execution_identity(profile)` trả identity đã validate như C5 mà không load encoder/segmenter. Route retry nhận diện sensitivity rồi lấy identity này; ordinary jobs vẫn dùng `registry.status` như cũ. Store không tự import torch/registry. T07 dùng lại cùng hàm/check identity dưới lock của inference, không tái định nghĩa digest ở API.
- **Nghiệm thu:** source text/prediction/review/run list/count không thay sau POST; lỗi bất kỳ không để temp orphan; concurrent submit cùng key chỉ một cặp; không xóa giữa grapheme; source delete xóa cả temp jobs; DB v1 dữ liệu cũ còn nguyên sau migrate.
- **Tests:** repeated/overlapping phrase, emoji trước span, surrogate boundary, dấu tổ hợp tiếng Việt, ZWJ/flag, newline CRLF, tab/multiple spaces, start/end, whole-text/whitespace/punctuation-only, source ID/hash conflict, quotas multithread. Atomic rollback sau từng bước tạo; concurrent API/worker migrate; stale idempotency sau expiry; readonly guard không ảnh hưởng quick.
- **Rủi ro/giữ phạm vi:** không dùng global replace, không tự normalize raw text, không nâng toàn bộ dependency graph. Regenerate API lock qua script hiện có trong môi trường phù hợp; review diff chỉ dependency cần thiết và closure tương ứng.

### T07 — Inference cặp cùng identity và worker

- **Mục tiêu:** baseline/variant cùng model/pipeline, kết quả có thể kiểm tra và không pollute dữ liệu thật.
- **File/module:** `services/inference/registry.py`, `services/worker.py`, `services/storage/db.py`, `services/sensitivity.py`; mới `tests/inference/test_sensitivity.py`, mở rộng `tests/integration/test_worker_boundaries.py` và API tests.
- **Tiên quyết:** T06.
- **Triển khai khuyến nghị:** giữ public `predict(profile,items)` cũ; thêm `predict_pair(profile,items,expected_identity)` nhận đúng 2 inputs và trả `{predictions, execution_identity, model_input_equal}`. Hai method gọi cùng đường preprocess/forward nội bộ; không copy pipeline. `run_logits` giữ return mặc định, thêm collector tùy chọn lấy input_ids đã mask tại chính batch forward; so sánh tuples trong bộ nhớ rồi bỏ, không lưu/log token IDs. Identity guard trong lock trước load/inference; output luôn trả identity thật đã dùng. Worker phát hiện mapping experiment, chọn đủ cặp dù batch_size=1, dùng validate_prediction sẵn có, lưu hai predictions + diagnostics/error metadata trong một fenced transaction.
- **Nghiệm thu:** model swap giữa enqueue/claim không sinh so sánh; baseline/variant cùng identity; IDs không lệ thuộc thứ tự output; cancellation/lease expired không commit; retry không nhân đôi; input-equal được đo từ model inputs, không đo từ raw string. Cặp không đổi source dataset và không rò vào quick result cũ. Không sửa architecture/preprocessor/validator config.
- **Tests:** test doubles đảo thứ tự/cặp thiếu/sai schema; failure giữa call/commit; batch_size=1; cancel trong inference; lease recovery và stale worker; interleave bulk/quick/experiment; TTL dưới backlog. Synthetic format1/format2 parity đường predict cũ so với mới, truncation cuối đoạn tạo equal input và bỏ ở đầu làm đổi window. Real-model parity riêng ở T11.
- **Rủi ro/giữ phạm vi:** refactor registry có thể làm lệch default call signatures/tests hoặc bypass F1; giữ test format1 + format2 + config semantic và offline loading. Không tăng số model trong RAM hay tạo background inference thread mới.

### T08 — UI khám phá độ nhạy

- **Mục tiêu:** thử nghiệm tương tác đủ loading/error/cancel/stale và kiểm được trên mobile.
- **File/module:** mới `apps/web/src/SensitivityPanel.tsx`, `ItemDetail.tsx`, `types.ts`, `api.ts`, `styles.css`; E2E mới.
- **Tiên quyết:** T07 và T04.
- **Triển khai:** panel thu gọn; stable single text node cho desktop selection; fallback input/radio occurrence; request preview exact variant, source hash; cache key gồm item/revision/view/selection/generation/job. Capture generation trước POST: ngay cả response POST tới muộn cũng không được attach job vào selection mới; gửi cancel job orphan best-effort. Hiển thị cả before/after, delta same-label, full scores thu gọn. Không reuse `QuickAnalysis` result có một item. Clear result khi close/change; ngăn tạo experiment khi nháp text chưa lưu.
- **Nghiệm thu:** keyboard/mobile không cần drag; repeated occurrence chỉ xóa cái được chọn; label leader đổi vẫn so đúng cùng nhãn; response cũ không xuất hiện trên item khác; review draft không bị mất; stale/model-changed được giải thích. No prediction vẫn có thể tính cặp mới nếu model sẵn sàng, nhưng không giả prediction gốc đã có.
- **Tests:** deferred POST/GET out-of-order, switch item/run/selection khi pending, cancel lỗi mạng, 404 TTL, unavailable UIT, stale revision, source prediction đổi, one failed half không render comparison. Viewports 1440/1024/390/320, keyboard focus, no console errors, no body overflow.
- **Rủi ro/giữ phạm vi:** không đưa experiment result vào review confirmation source; nút xác nhận AI vẫn dựa item.prediction gốc. Không tự sửa text nguồn hoặc lưu variant thành item mới.

### T09 — Snapshot, backup và regression tổng hợp

- **Mục tiêu:** chứng minh tính năng mới giữ dữ liệu cũ và được dọn đúng.
- **File/module:** tests API/integration/backup/runtime isolation, `scripts/backup_local.py` chỉ sửa nếu test chứng minh thiếu cleanup; app docs liên quan.
- **Tiên quyết:** T01–T08.
- **Triển khai:** fixture DB v1 có prediction/review/export trước migrate; so bytes old export sau migration + review + experiment + restart + append. Export theo new filter đóng băng policy/membership; đổi policy sau đó không rewrite bytes. Backup runtime có source+quick+experiment; restore runtime mới giữ durable state, không có temp/context/token text; source delete khi worker đang infer không commit lại. Không dùng DB production cho fixture.
- **Nghiệm thu:** no orphan rows/FK errors; quick/bulk lifecycle cũ còn đúng; exported header nguyên vẹn; không file model/pointer production đổi; đầy đủ C5/E4, bao gồm public readonly guards.
- **Tests:** `tests/test_backup.py`, `tests/test_runtime_isolation.py`, `tests/integration`, `tests/api`, regression e2e review source/conflict. F2 phải GET đúng export ID cũ sau restart và sau thêm dòng, không tạo export mới để thay thế phép kiểm.
- **Rủi ro/giữ phạm vi:** lifecycle/backup không bảo đảm bằng happy path; test cả interrupted/failed/cancelled. Không “sửa” tests cũ bằng bỏ assertions hoặc nới tolerance vô căn cứ.

### T10 — Dataset minh họa và kịch bản trình bày

- **Mục tiêu:** một demo liền mạch có dữ liệu thật chạy qua model, minh bạch giới hạn.
- **File/module:** mới `data/demo/three_layer_feedback_vi.csv`, `data/demo/README.md`, `docs/THREE_LAYER_DEMO_RUNBOOK.md`; nội dung H. Đây là đường dẫn được .gitignore hiện tại cho phép; không đặt weights/results vào repo.
- **Tiên quyết:** T02/T04/T08 đã kiểm bằng fixture; T11 cần dataset này.
- **Triển khai:** tạo đúng 24 câu H1, metadata sample_id và illustrative=true; CSV không có prediction/scores. Tách nhãn tham chiếu người viết trong README, chỉ import reference qua cơ chế mapping/source hiện có nếu thực sự muốn trình bày chúng. Dry-run inference thật để ghi run/version/thực tế flagged/label switches và chọn đường bấm theo quy tắc H2, không sửa dữ liệu/kết quả để tạo lỗi.
- **Nghiệm thu:** có thể đi toàn luồng 3–5 phút với model ấm sau rehearsal; không hứa cold load trong thời gian này. Có thao tác sửa nhãn rõ nguồn người dùng; số liệu sau review đúng; trường hợp không có dòng flagged/không flip vẫn có kịch bản trung thực.
- **Tests:** kiểm CSV parse UTF-8/BOM, 24 IDs riêng, ≤5000 ký tự mỗi dòng, không cột prediction; browser full journey. Không hardcode label prediction mong muốn trong real-model tests.
- **Rủi ro/giữ phạm vi:** nhãn tham chiếu của câu pha trộn là đề xuất có thể tranh luận; không gắn cho chúng “ground truth model”. Không dữ liệu cá nhân thật.

### T11 — Kiểm chứng cuối, model thật và bàn giao

- **Mục tiêu:** kết thúc bằng bằng chứng mới sau tất cả code changes.
- **File/module:** real-model test mới `tests/inference/test_three_layer_real_model.py` với marker; docs LOCAL_APP, PRODUCT nếu cần, report validation mới (không xóa phần F1/F2 lịch sử), runbook.
- **Tiên quyết:** T09/T10, T05 đã chạy hoặc được ghi rõ chưa đánh giá.
- **Triển khai:** build frontend; tests phù hợp G; real smoke dùng copy immutable bundle active vào runtime tạm để kiểm đúng production identity, không reimport thành phiên bản mới thay cho phép kiểm đó. Chạy regressions real-model F1/F2 hiện có tách riêng (chúng import vào temp roots). Thu evidence thực từ API/worker/browser; kiểm hash production artifact trước/sau; ghi pass/fail/skip, lệnh, ảnh, latencies, limitations.
- **Nghiệm thu:** ba lớp hoàn chỉnh, dữ liệu thật, browser desktop/mobile pass; no mutation production; cặp same identity; snapshot old export byte-identical; F1/F2 không regress. Nếu thiếu môi trường khiến real-model/browser chưa chạy thì phải ghi “chưa nghiệm thu” ở hạng mục đó, không gọi hoàn tất demo thật bằng tests double.
- **Tests:** default suite một lần cuối và real-model opt-in; không lấy baseline 163/2 làm bằng chứng của code mới. Nếu sửa sau suite, chạy lại nhóm chịu ảnh hưởng; không chạy lặp toàn bộ vô cớ.
- **Rủi ro/giữ phạm vi:** không commit/push/deploy, không start/stop production; chỉ dừng process do lượt test tạo. Không tự giải quyết thiếu artifact bằng tải backbone/weights mới.

## G. Chiến lược kiểm thử và kiểm chứng

### G1. Ma trận bắt buộc

| Nhóm | Điều phải chứng minh | Bằng chứng |
|---|---|---|
| Aggregate unit | mẫu số thiếu nhãn, toxic riêng, manual + failed, sort/tie, n=0, n<5 | Fixtures nhỏ với counts tính tay; không chỉ assert implementation gọi đúng helper. |
| Signal unit | top1/margin strict thresholds, hai task, score invalid/missing, policy hash | Expected results kiểm độc lập; không bịa optimum. |
| Scope API | current vs historical, latest-run no fallback, source AI/effective, q + nhãn + review + signal | List IDs = filter membership, summary count = list.total = filtered export.row_count; pagination không đổi summary. |
| Review | task độc lập, same/other source prediction, manual null, revision conflict, undo/history | Predictions bất biến; effective thay; signals numerical bất biến; pending đúng. |
| Selection | occurrence, UTF-16, grapheme, CRLF, exact whitespace, empty/nonlexical | Assert exact variant bytes/code points và không mutate text nguồn. |
| API experiment | idempotency, rate/quota atomic, bad inputs, metadata identity, readonly guards | Không temp orphan sau failure; error envelope đúng. |
| Worker | pair atomic, cancel/lease/retry/recovery, priority, delete-source race | Không partial comparison/late commit/duplicate; không block event loop API. |
| Storage/backup | migration v1→v2, startup concurrency, TTL, snapshot/backup | Old predictions/reviews/CSV còn nguyên, temp không được backup, FK/integrity tốt. |
| UI | click-through, filter/source/run, save-next, stale results, modal focus, mobile fallback | Playwright 1440×960 và 390×844 bắt buộc, 1024/320 kiểm overflow/controls; ảnh được xem thật, không chỉ lưu. |
| Real model | pipeline thật, cùng frozen identity, same-label delta, input-equal/truncation diagnostics | Copy bundle active, inference offline, API + worker riêng, response/provenance/logs an toàn. Không assert câu bất kỳ phải flip. |
| Regression | quick/import/review/export/jobs, format1/2, config F1, snapshot F2 | Giữ tests hiện có, báo kết quả mới. |

Test top1/margin cần distribution chuẩn, sum≈1. Tests pipeline dùng synthetic encoder chỉ để chứng minh mechanics; không đem scores fixture vào demo. Label-order mapping theo schema được test cho NEU/UIT riêng.

### G2. Lệnh dự kiến cho lượt triển khai (chưa chạy trong lượt lập kế hoạch)

Đây là chỉ dẫn cho Gemini sau khi đã triển khai, không chạy trước lúc code tồn tại. Chạy PowerShell từ `F:\DPL_NEU-ESC`; dùng `.venv` hiện có nếu đủ dependency, không chạy setup-local/importer production theo thói quen.

```powershell
# Tạo root kiểm thử riêng; biến môi trường chỉ trong process shell của lượt test.
$demoAuditRoot = Join-Path $env:TEMP ('feedback-three-layer-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $demoAuditRoot | Out-Null
$env:FEEDBACK_RUNTIME = Join-Path $demoAuditRoot 'default-runtime'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

# Build trước browser tests; npm --prefix không thay thư mục làm việc.
npm.cmd --prefix apps/web run build

# Trong từng mốc: chạy đúng test file mới/đã sửa và regression phụ thuộc.
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/api tests/integration -q
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/inference/test_phobert_config.py tests/test_backup.py tests/test_runtime_isolation.py -q
.\.venv\Scripts\python.exe -X utf8 -m pytest tests/e2e -q

# Sau khi ổn định: default suite; marker mặc định loại real_model.
.\.venv\Scripts\python.exe -X utf8 -m pytest -q

# Model thật opt-in, root duy nhất để pytest không dọn nhầm thư mục khác.
.\.venv\Scripts\python.exe -X utf8 -m pytest -m real_model -q --basetemp (Join-Path $demoAuditRoot 'real-model-tests')
git diff --check
git status --short
```

Các nhóm đầu chạy khi đang phát triển, không bắt buộc chạy lại tất cả ngay trước full suite nếu không có thay đổi mới. Không dùng `--basetemp` trỏ vào một thư mục có công việc cũ. Không dọn audit root trước khi bằng chứng đã được bàn giao. Nếu cần phục hồi biến môi trường thì lưu/khôi phục giá trị trước lượt test, không sửa cấu hình máy toàn cục.

Chỉ chạy T05 sau khi copy bundle vào một `<audit>/validation-runtime/models/neu/versions/<active-version>` và tạo pointer **trong root tạm** cùng version. Copy file thật hoặc dùng cách copy không ghi xuyên về source; không hardlink/symlink rồi mutate. Không copy database người dùng để inference thử. Root source production dùng read-only; kiểm SHA-256 copy bằng manifest rồi load bản copy.

Real smoke mới phải kiểm đúng bundle đang active ở thời điểm bắt đầu, vì importer hiện tại có thể tạo version khác dù checkpoint giống nhau. F1/F2 regression cũ vẫn chạy riêng và được ghi rõ identity test riêng, không gọi version tạm của importer là production.

API/worker test phải bind cổng loopback rảnh do harness cấp, giữ PID/process handle/time tạo để cleanup đúng process. Không dùng cổng 8765 mặc định để thử vì có thể là AnkiConnect. Không tự gọi `stop-local.ps1` lên runtime thật. Manual rehearsal có thể dùng `start-local.ps1 -RuntimeDirectory <temp> -Port <free-port>` sau kiểm cổng; 8766 chỉ là ví dụ nếu rảnh, không được chiếm lại nếu đã có chủ.

### G3. Acceptance real-model chi tiết

1. Copy immutable active bundle và pointer vào runtime tạm; ghi version/manifest/checkpoint hash, dependency versions, máy CPU. Registry production không có fake fallback; test doubles chỉ trong tests.
2. Dùng dataset 24 câu do tác giả tạo, import và chạy model thật. Xác minh đúng schema, scores hữu hạn/tổng≈1, profile UIT vẫn unavailable. Không assert accuracy demo bằng nhãn tham chiếu chủ quan.
3. Tính attention trực tiếp từ response rows trong test, đối chiếu summary; click topic → đúng list IDs; đổi AI/effective rồi review một task có tác động dự kiến.
4. Chạy sensitivity với một substring thực sự tồn tại. Kiểm same execution identity ở cả predictions, exact variant, delta từng label bằng hiệu số từ response; không cần flip label. Kiểm source counts/text/prediction/review history/old export không đổi.
5. Một case dài có emoji/dấu tiếng Việt vượt 128 token: thử bỏ đoạn cuối và đầu; kiểm metadata/equality thực tế, không ép kết quả equal chỉ theo vị trí chữ. Same-input test riêng giữ cả hai texts giống nhau ở đường inference để kiểm parity, không bypass validation endpoint cho selection rỗng.
6. Cancel/worker restart và tải kết quả tạm còn TTL; source revision đổi → result stale. Tạo export qua UI, tải đúng export ID trước/sau restart và sau append, so bytes; không tạo snapshot thay thế.
7. Chụp/kiểm UI desktop/mobile và console errors. Báo test bị skip thiếu artifact/build/browser như thiếu nghiệm thu, không quy thành pass.

### G4. Performance và độ ổn định local

Đo trên dữ liệu tổng hợp 24, 100 và 500 dòng trong runtime tạm: summary/list/filter/export request time, payload size và số request, cold load, warm pair inference, queue wait, bulk xen sensitivity, memory nếu công cụ có sẵn. Ghi số mẫu, median/p95 khi đủ mẫu, CPU/RAM/runtime, text/token length; không suy SLA từ một lần chạy.

Quan sát UI vẫn thao tác/filter/cancel được khi worker bận; API không gọi torch forward; polling có backoff khi mất mạng; không fetch cả 500 rows để tính attention, không busy loop; không tạo nhiều job khi double-click. Với trần 500, chỉ tối ưu storage nếu phép đo phát hiện nghẽn thực và có regression giữ semantics. Nếu workload không phù hợp demo, công bố giới hạn đo được và giảm khối lượng rehearsal, không tạo loading giả hoặc sửa kết quả.

## H. Dữ liệu minh họa và kịch bản demo

### H1. Bộ 24 phản hồi do người viết tạo

Đây là dữ liệu minh họa được soạn cho demo, không lấy từ sinh viên thật, không có tên/email/mã sinh viên. **Bảng nhãn dưới là tham chiếu đề xuất của tác giả, chưa chạy model và không phải kết quả model.** Các câu pha trộn có thể có nhiều cách đọc, vẫn gán một nhãn mỗi task theo schema hiện tại. Mọi stats trình diễn phải đến từ run thật.

CSV tương lai: `sample_id,text,illustrative`; `illustrative=true`. Nhãn tham chiếu ở README riêng. Chỉ nếu cần hiển thị reference trong app mới thêm cột reference và dùng mapping rõ nguồn “Tác giả dữ liệu minh họa”; không đưa vào model inputs hay thay scores.

| ID | Văn bản | Sentiment tham chiếu | Topic tham chiếu | Vai trò |
|---|---|---|---|---|
| D01 | Giảng viên giải thích bài tập rõ ràng, mình hiểu cách làm ngay trên lớp. | Positive | Academic | Tích cực, nội dung rõ. |
| D02 | Lịch thi đổi sát ngày khiến mình không kịp sắp xếp việc học. | Negative | Academic | Phản hồi tiêu cực. |
| D03 | Bài tập tuần này gồm ba câu về phân tích dữ liệu. | Neutral | Academic | Thông tin trung tính. |
| D04 | Môn học rất bổ ích nhưng khối lượng bài tập dồn cuối kỳ quá nặng. | Negative | Academic | Pha trộn cảm xúc. |
| D05 | Học trực tuyến thật tuyệt, cứ đến phần quan trọng là mất tiếng. | Negative | Academic | Cách diễn đạt mỉa mai; không hứa model phát hiện. |
| D06 | Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc. | Negative | Service | Vấn đề dịch vụ. |
| D07 | Nhân viên thư viện hướng dẫn tìm tài liệu nhanh và rất nhiệt tình. | Positive | Service | Tích cực. |
| D08 | Nhà ăn phục vụ chậm, giờ nghỉ trưa gần hết mới nhận được suất ăn. | Negative | Service | Tiêu cực. |
| D09 | Thư viện mở cửa đến chín giờ tối trong tuần ôn thi. | Neutral | Service | Trung tính. |
| D10 | Phòng học sạch nhưng điều hòa hỏng nên buổi chiều rất nóng. | Negative | Service | Hai ý, giới hạn một topic. |
| D11 | Câu lạc bộ tổ chức buổi hướng dẫn viết CV hữu ích và dễ theo dõi. | Positive | Club & Events | Sự kiện tích cực. |
| D12 | Sự kiện bắt đầu muộn gần một giờ mà không có thông báo cho người tham gia. | Negative | Club & Events | Sự kiện tiêu cực. |
| D13 | Buổi sinh hoạt câu lạc bộ sẽ diễn ra vào chiều thứ sáu. | Neutral | Club & Events | Trung tính. |
| D14 | Hoạt động thú vị, chỉ tiếc phần trao đổi với khách mời quá ngắn. | Positive | Club & Events | Có ý kiến hạn chế. |
| D15 | Mô tả vị trí thực tập rõ ràng và ghi đầy đủ mức hỗ trợ cho sinh viên. | Positive | Jobs & Recruitment | Tích cực. |
| D16 | Tin tuyển dụng yêu cầu đóng phí trước khi phỏng vấn khiến mình lo ngại. | Negative | Jobs & Recruitment | Tiêu cực; không tự kết luận lừa đảo. |
| D17 | Đơn vị tuyển hai thực tập sinh phân tích dữ liệu trong tháng này. | Neutral | Jobs & Recruitment | Trung tính. |
| D18 | Mình cần hỏi thủ tục xin giấy xác nhận sinh viên gồm những gì. | Neutral | Help & Share | Câu hỏi. |
| D19 | Cảm ơn mọi người đã chia sẻ tài liệu ôn tập, phần ví dụ rất dễ hiểu. | Positive | Help & Share | Lời cảm ơn. |
| D20 | Mình tìm hướng dẫn đổi lớp mãi không thấy, ai có thể chỉ giúp không? | Negative | Help & Share | Câu hỏi + cảm xúc. |
| D21 | Tuần này mình cân bằng được việc học và nghỉ ngơi nên thấy nhẹ nhõm hơn. | Positive | Personal Affairs | Chủ đề ít mẫu. |
| D22 | Xe buýt đến muộn nhiều lần làm sinh viên phải chờ rất lâu. | Negative | Social Affairs | Chủ đề ít mẫu. |
| D23 | Thông báo: thời gian nhận hồ sơ học bổng kết thúc vào cuối tháng. | Neutral | News | Tin tức, ít mẫu. |
| D24 | Đồ vô dụng, có việc đơn giản vậy mà cũng làm không xong. | Toxic | Other | Minh họa phân biệt Toxic, không nhắm người thật. |

Không phải mọi topic phải xuất hiện trong predictions thực. Không thêm dự đoán cố định cho Spam/Other chỉ để phủ đủ bảng. Một test fixture riêng có thể bảo đảm phủ mọi nhãn để kiểm phần mềm; phải tách khỏi dataset demo thật.

### H2. Rehearsal và chọn đường đi xác định

- Trước buổi trình diễn, import đủ 24 câu, chạy model thật, ghi version/run/số dòng, thời gian cold/warm, attention thực, số flags, nhãn thực và lựa chọn đoạn sẽ thử. Không chạy inference trong chat lập kế hoạch này.
- Chọn topic đứng đầu theo ranking đã công bố, không chọn excerpt bằng điểm thuận lợi. Danh sách trong topic sắp source_row tăng dần. Để mở item có tín hiệu, chọn item đầu tiên thỏa filter trong danh sách; nếu không có thì bỏ riêng topic filter và chọn item đầu tiên trong toàn bộ filter pending. Hiển thị thay đổi phạm vi này.
- Chọn đoạn theo nội dung câu, không tìm kiếm tự động nhiều perturbations để chỉ trình bày lần flip. Runbook ghi đoạn thử và outcome thực sau rehearsal. Nếu không đổi nhãn/điểm gần như không đổi, giải thích đó là kết quả hợp lệ, mở bảng same-label và cảnh báo giới hạn.
- Trường hợp sửa nhãn: sau chạy thật, so với tham chiếu đề xuất và đọc lại nội dung; chọn disagreement đầu tiên theo source_row mà người trình bày giải thích được. Nếu model trùng tất cả tham chiếu, dùng câu nhiều ý và nói rõ “Tôi minh họa việc người phụ trách chọn nhãn theo cách đọc này”, không tuyên bố vừa phát hiện model sai. Vẫn thực hiện thao tác corrected thực, có note; không bịa trước câu nào model sẽ sai/điểm thấp.
- Không có flags không phải blocker; nói “Với ngưỡng hiện tại, chưa có dòng bị đánh dấu”, sau đó mở một câu pha trộn để xem bằng tay. Tuyệt đối không đổi ngưỡng hoặc prediction để buộc câu chuyện xảy ra.

### H3. Kịch bản 3–5 phút (sau khi model đã được nạp trong rehearsal)

| Khoảng thời gian gợi ý | Thao tác | Lời dẫn / điều phải thấy |
|---|---|---|
| 0:00–0:40 | Giới thiệu local, import CSV 24 câu minh họa, chọn NEU, chạy phân tích thật | “Đây là dữ liệu do chúng tôi viết để minh họa. Mỗi dòng có một cảm xúc và một chủ đề.” Hiện tiến độ thực. Nếu máy chậm, chờ và nêu rõ, không cắt thành kết quả giả. |
| 0:40–1:25 | Tổng quan → Chủ đề cần chú ý → topic đầu bảng → Xem phản hồi tiêu cực | Nêu số Negative, mẫu số, nguồn “AI” hoặc “Đã duyệt nếu có, còn lại AI”, ít mẫu. “Đây là số liệu của bộ phản hồi này theo bộ lọc hiện tại.” |
| 1:25–2:05 | Filter tín hiệu, mở một dòng; xem top1/top2 và lý do | “Tín hiệu giúp ưu tiên kiểm tra; điểm này không phải xác suất model đúng.” Truncation được giải thích riêng nếu có. |
| 2:05–3:05 | Mở Khám phá dự đoán, chọn một occurrence, xem preview, chạy cặp | Đọc cùng một nhãn trước/sau, không so max khác nhãn. Đọc giới hạn thử nghiệm. Outcome có thể không flip, không ép diễn biến. |
| 3:05–4:05 | Sửa sentiment hoặc topic với note; lưu; quay Tổng quan | Chỉ task được sửa thay đổi; AI gốc giữ; effective count/nhóm cập nhật theo filters. Pending có thể giảm còn signal vẫn có. Nếu item rời filter, hiện lý do và đi về danh sách. |
| 4:05–4:45 | Xuất CSV lọc hoặc toàn bộ, tải snapshot | Nêu nguồn AI/review/effective, cột scores và warnings hiện có; sensitivity không được ghi vào dữ liệu nguồn. “File xuất là bản chụp tại lúc tạo.” |

Mốc thời gian là bố cục lời nói, không phải cam kết latency. Có thể trình diễn bộ đã phân tích thật từ rehearsal nếu cold load quá lâu, nhưng phải nói rõ đang xem run đã chạy, vẫn import/chạy batch mới khi muốn chứng minh live. H2 luôn giữ một thao tác review thực và một experiment thực trong luồng.

## I. Ưu tiên và mốc nghiệm thu

### I1. Các mốc sản phẩm

| Mốc | Task | Điều kiện kết thúc |
|---|---|---|
| M0 — Giữ baseline | T00 | Snapshot/read-only inventory, test root riêng, biết artifact active. |
| M1 — Decision Support | T01–T02 | Attention đúng mẫu số/filter/source/run và dẫn tới đúng phản hồi; responsive/keyboard. Có thể review độc lập trước phần interpretability. |
| M2 — Tín hiệu rà soát | T03–T05 | Flags riêng task, pending vs human review rõ, legacy unchanged, CSV snapshot đúng; validation report mới hoặc trạng thái chưa đánh giá rõ. |
| M3 — Khám phá độ nhạy | T06–T09 | Cặp cùng model/pipeline, Unicode an toàn, không sửa nguồn, đầy đủ cancel/TTL/migration/backup/old snapshot. |
| M4 — Demo thật | T10–T11 | Dataset minh họa + runbook, browser và real-model evidence mới, không thay production artifact. |

Không đổi thứ tự sản phẩm mặc định; kiểm logic backend luôn trước nghiệm thu UI tương ứng. Có thể chuẩn bị phần độc lập song song theo I4 sau khi contract đã chốt. Không bỏ dependency T00–T11 hoặc tự coi mốc hoàn tất chỉ vì một subagent báo xong. Không có ước lượng giờ/ngày thiếu cơ sở.

Nếu gặp thiếu validation/artifact: vẫn hoàn thành các task phần mềm độc lập và ghi giới hạn; không tự bật UIT, nhập model khác hoặc công bố model thật đã nghiệm thu. Nếu thiếu raw validation thì policy vẫn experimental, không hạ thành “đã đánh giá” bằng processed logits. Nếu real-model smoke không chạy được thì M4 còn thiếu, phải nêu rõ.

### I2. Mô hình điều phối được khuyến nghị

Dùng **một Gemini chính làm điều phối/tích hợp và tối đa ba subagent: Backend, Frontend, QA/Review**. Không chia ba lớp sản phẩm thành ba agent tự sửa full stack: các lớp cùng đi qua `db.py`, `main.py`, `Workspace.tsx` và `ItemDetail.tsx`, dễ gây xung đột hoặc đổi semantics không đồng bộ.

Ưu tiên subagent QA/Review có context riêng và không viết implementation mà nó review. Lợi ích chính là đối chiếu contract, thiết kế ca biên và tìm regression độc lập; tốc độ viết code chỉ là lợi ích phụ. Không cần tạo agent mới cho từng task, từng file hoặc từng lượt test. Không cho subagent tự tạo thêm subagent hoặc mở rộng phạm vi.

Gemini chính phải kiểm tra khả năng **native subagent** của harness trước khi phân công. Không mặc định mọi giao diện Gemini đều có tính năng này. Nếu không có, thực thi tuần tự cùng contract/checklist và báo rõ chưa có reviewer độc lập; không giả vờ đã có subagent, không tự cài framework hoặc gọi API bên ngoài để mô phỏng. Nếu chỉ có một slot subagent, ưu tiên dùng slot đó làm reviewer độc lập sau từng mốc, Gemini chính viết implementation tuần tự.

### I3. Ownership và trách nhiệm

Ownership áp dụng cho lượt triển khai tương lai, không cho lượt cập nhật tài liệu này. Tên role là trách nhiệm, không bắt buộc một model/version cụ thể.

| Vai trò | Được sửa | Trách nhiệm / giới hạn |
|---|---|---|
| Gemini chính — điều phối/tích hợp | Tài liệu `docs/`, `PRODUCT.md` nếu cần, `data/demo/`; nhật ký/bằng chứng trong audit root riêng | T00, chốt contract C–E, phân công, T10, duyệt mốc, T11 và báo cáo cuối. Giữ nguyên scope sản phẩm. Không đồng thời sửa file đã giao agent khác. |
| Backend | `services/**` trong phạm vi T01/T03/T06/T07; `requirements-api.txt`, `requirements-api.lock.txt`; `scripts/backup_local.py` chỉ khi regression chứng minh cần | Một owner xuyên suốt storage/API/worker/registry, migration, identity, TTL, snapshot và guards. `architecture.py`, transform preprocessing, `phobert_config.py`, schema labels và artifact production vẫn bị cấm đổi theo B/J1. Không sửa frontend, tests hay báo cáo của QA để làm test pass. |
| Frontend | `apps/web/src/**` cho T02/T04/T08 | Một owner cho Workspace/ItemDetail/types/api/styles và components mới. Dùng contract backend đã chốt; không tự đổi API hay schema. Không thêm mock/fake fallback trong production UI. Dependency/package/config build ngoài phạm vi phải báo điều phối trước. |
| QA/Review | `tests/**` liên quan, mới `scripts/evaluate_review_signals.py`; báo cáo/log/ảnh riêng trong audit root | Viết tests từ C–G, T05 và phần kiểm thử T01–T11, review implementation Backend/Frontend theo I6. Không sửa production code/dependency hoặc hạ assertion để che lỗi. Không thay model/policy để đạt tỷ lệ đẹp. |

Các file không thuộc bảng: mặc định chưa được giao; đề xuất cho điều phối nếu thật sự cần. Tài liệu hiện tại là spec chung, chỉ điều phối được cập nhật với lý do rõ; Backend/Frontend/QA không tự đổi công thức/ngưỡng/mẫu số/error semantics.

Task F vẫn giữ mục tiêu/dependency/acceptance. Mục “File/module” ở F là toàn bộ file có thể liên quan đến task, **không** trao quyền cho một agent sửa tất cả. Ví dụ T07: Backend sửa registry/worker/storage, QA sửa tests tương ứng; T02: Frontend sửa UI, QA sửa browser test. Task chỉ xong khi cả implementation và kiểm chứng được tích hợp.

Nếu cần đổi owner: owner cũ dừng sửa, gửi file list/hash và phần còn dang dở; điều phối ghi chuyển giao rồi owner mới đọc lại file mới nhất. Không có hai writer trên cùng file, kể cả khi dự định sửa các vùng khác nhau. Điều phối không tự “sửa nhanh” file agent còn đang viết. Thay đổi từ đồng đội đúng ownership là dự kiến; thay đổi không giải thích được hoặc có vẻ do người dùng thực hiện phải dừng ghi file đó và báo, không ghi đè.

### I4. Các đợt phân công và điểm tích hợp

| Đợt | Gemini chính | Backend | Frontend | QA/Review | Điều kiện qua đợt |
|---|---|---|---|---|---|
| 0 — Baseline/contract | T00; đọc lại repo; chốt C–E so với code mới; giao file ownership và audit roots | Chưa sửa; có thể đọc code được giao | Chưa sửa; đọc DESIGN/UI hiện có | Đọc acceptance, đề xuất ma trận ca biên | Có baseline, ownership và contract cụ thể; không còn điểm API mâu thuẫn chặn implement. |
| 1 — Attention | Giữ scope M1, phản hồi sai khác contract | T01 backend | T02 sau khi attention endpoint qua contract tests; có thể đọc/chốt UI trước đó | Tests T01 từ contract, rồi browser tests T02 và review M1 | M1 đạt, click count ra đúng membership, source/run/mẫu số được kiểm. |
| 2 — Signals | Chốt policy experimental; duyệt báo cáo M2 | T03 backend | T04 sau contract signal tests pass | Tests signals/review/export; viết script T05, chạy khi được cấp lượt inference riêng; review M2 | M2 đạt, legacy needs_review không đổi, AI signal tách human review. |
| 3 — Sensitivity foundation | Đối chiếu schema/identity/error lifecycle trước tích hợp | T06 rồi T07 cùng owner; không chia db/API/worker cho các writer khác | Chỉ chuẩn bị phần độc lập sau khi contract E2–E4 đã chốt; chưa nghiệm thu T08 | Selection/migration/job/identity tests và review boundary; ghi lỗi tái hiện được | Cặp cùng identity, atomic commit, Unicode/TTL/cancel/source safety qua tests; không còn lỗi contract chặn UI. |
| 4 — Flow integration | T10: dataset/runbook; không ghi kết quả model trước rehearsal | Sửa findings thuộc backend | Hoàn tất T08 và UI findings | T09; browser journey mới; review M3 trên code tích hợp | M3 đạt; CSV cũ, review history và source dữ liệu được bảo toàn. |
| 5 — Final verification | T11; khóa bản code được test, kiểm hash/bằng chứng, báo cáo cuối | Dừng sửa trong lúc kiểm; xử lý findings qua owner khi được điều phối | Build một bản xác định rồi dừng sửa trong lúc browser kiểm | Full default suite, T05 còn thiếu, real-model/F1/F2 tuần tự; review cuối | M4 đạt bằng bằng chứng mới trên bản tích hợp cuối, hoặc báo chính xác phần chưa nghiệm thu. |

Tối đa ba subagent hoạt động không có nghĩa phải luôn có ba writer bận. Ví dụ, Backend có thể bắt đầu T03 khi T01 đã chốt contract và Frontend đang hoàn thiện T02, nhưng không được sửa phá contract attention mà frontend/QA đang dùng. Chuẩn bị T08 trước T07 chỉ gồm layout/selection theo contract; không coi T08 hoàn tất hoặc bù API chưa có bằng fallback production.

QA có thể viết tests trước implementation từ ví dụ C–G; test fail do tính năng chưa có được ghi là pending, không phải pass. Mọi mock/double chỉ ở test harness. Không build/chạy nghiệm thu khi code phụ thuộc đang bị writer sửa giữa chừng; điều phối cấp một khoảng ổn định cho từng phép kiểm, rồi mở lại phần cần sửa.

### I5. Quy tắc workspace, tài nguyên và giao nhận

- Mặc định dùng cùng working tree và ownership không chồng lấn. Mỗi agent phải biết mình không làm việc một mình: không revert, format hàng loạt, restore file, xóa untracked hoặc thay nội dung thuộc owner khác. Không dùng `git add .`, auto-commit hoặc stash để bàn giao. Task chỉ bàn giao file/diff và bằng chứng.
- Trước khi giao việc, cung cấp cho subagent **spec và nội dung working tree hiện tại**, không chỉ HEAD. Tài liệu plan đang là file untracked trong baseline lượt cập nhật; agent trong checkout riêng có thể không thấy nó. Nếu harness bắt buộc checkout tách, điều phối phải cung cấp cả plan và snapshot mã hiện tại/baseline edits, đối chiếu file hashes và tích hợp patch chỉ trong vùng owned. Không tự giả định bản checkout từ HEAD đã bao gồm mọi thay đổi người dùng; chưa xác định được snapshot đúng thì dùng reviewer read-only hoặc thực thi tuần tự trên workspace hiện tại.
- Khi giao task, nêu rõ mục tiêu, ID, file được sửa, contract liên quan, dependency đã/chưa xong, acceptance/tests, việc cấm làm, artifact baseline và nơi đặt output. Chỉ gửi phần bối cảnh cần thiết cùng đường dẫn toàn plan; không yêu cầu agent tự suy lại sản phẩm.
- Mỗi agent dùng runtime/temp/log/output path riêng dưới audit root, đặt `FEEDBACK_RUNTIME` trước import app và không sửa biến môi trường toàn máy. Giữ PID/process handle của process mình tạo; không kill theo tên hoặc cổng mà không biết chủ.
- **Chỉ một lượt công việc inference nặng chạy tại một thời điểm:** validation T05, real-model suite, rehearsal và benchmark phải được điều phối xếp hàng. Không chạy nhiều model loaders/pytest ML đồng thời trên CPU để “tăng tốc”. Không dùng pytest-xdist trong kế hoạch này. Các unit tests nhẹ chỉ chạy song song khi không tranh shared files/build/runtime.
- Frontend owner chạy build ở điểm đã thống nhất; QA browser test dùng đúng bản build đó. Không `npm run build` cạnh một lượt browser acceptance đang đọc cùng `apps/web/dist`; không đổi dependency/lock hoặc chạy formatter toàn repo trong lúc agent khác đang làm.
- Handoff mỗi task phải có: ID, files changed, contract đáp ứng hoặc khác biệt, lệnh thực chạy và kết quả pass/fail/skip, đường dẫn evidence, vấn đề chưa giải quyết, hash/danh sách file ở thời điểm kiểm. Tách “đã chạy kiểm chứng” khỏi “suy ra từ code”. Không dùng “done” thay cho bằng chứng.
- Điều phối nhận handoff, đọc diff và ghép với contract/tests. Nếu harness chia checkout, kiểm input hashes trước áp patch; không overwrite snapshot mới hơn. Nếu cùng tree, thay đổi đã có trên đĩa, không copy lại bản cũ từ handoff. Test một phần của agent không thay cho kiểm tích hợp.
- Sau tích hợp cuối, ghi HEAD và hash các file thực tế được kiểm vì chưa commit. Nếu sửa tiếp, chạy lại nhóm test/review chịu ảnh hưởng và chỉ ra evidence nào đã cũ. Không dùng ảnh/build/results của revision trước để nghiệm thu source mới.

### I6. Review độc lập và tiêu chí quyết định

QA/Review nhận contract, diff/source hiện tại và output tests; phải tự đọc code đường đi quan trọng trước khi dựa vào giải thích của tác giả. Reviewer không cần độc lập với việc viết tests, nhưng phải độc lập với implementation production đang được review. Một self-review của Backend/Frontend không thay cho review này.

Mỗi lượt review tập trung vào rủi ro cụ thể:

1. M1/M2: mẫu số và Toxic, missing-label/error/manual semantics, source/run/revision, filter parity, needs_review cũ, policy/hash, review source/conflict và export bất biến.
2. M3: Unicode offsets/graphemes/CRLF, repeated occurrence, source/context/identity guard, pair atomicity, cancel/retry/lease, TTL/cascade/backup, readonly guards, kết quả muộn và không mutate nguồn.
3. M4: code/build được test có khớp bản bàn giao; model thật và fixtures tách biệt; F1/F2; production hashes; chưa có bằng chứng nào bị trình bày thành đã pass; mobile/keyboard và câu chữ không vượt quá dữ liệu.

Findings phải có mức độ, file:line hoặc endpoint, tình huống tái hiện, expected/actual theo contract và test cần có. Findings chưa tái hiện được phải ghi rõ là nghi vấn từ code. Không tạo findings chỉ để đủ số lượng; nếu không tìm thấy lỗi, nói rõ phạm vi đã đọc/đã chạy và gaps còn lại.

Điều phối chuyển findings cho đúng owner; QA thêm/giữ regression test rồi kiểm lại bản sửa. Không sửa production để tự đóng finding của mình. Lỗi P0/P1, lỗi dữ liệu/provenance và bất cứ lỗi nào vi phạm acceptance bắt buộc đều chặn mốc dù được đặt tên severity thấp hơn. Các đề xuất ngoài scope được ghi backlog, không tự đưa vào implementation. Không nới ngưỡng số học, bỏ assertions hoặc bỏ test để “xanh”.

Gemini chính chịu trách nhiệm cuối: kiểm việc đóng findings, review các điểm quan trọng của diff và bằng chứng tích hợp; không dùng đồng thuận của nhiều agent làm bằng chứng đúng. Cách tổ chức này giảm nguy cơ bỏ sót, không phải bảo đảm tuyệt đối về chất lượng.

### I7. Mẫu giao việc cho subagent

Điều phối điền đúng role/ID/files/dependencies từ I3–I4; không gửi template còn placeholder cho subagent.

```text
Bạn là subagent [Backend | Frontend | QA/Review] trong F:\DPL_NEU-ESC.
Task được giao: [ID và mục tiêu cụ thể].
Đọc plan docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md,
đặc biệt [các mục C/E/F/G liên quan] và I2–I6, cùng AGENTS.md áp dụng.
Contract đã chốt: [trường/API/schema và semantics liên quan].
Dependency đã hoàn thành: [...]. Chưa được dựa vào: [...].
Bạn chỉ được sửa: [danh sách file/module cụ thể theo ownership].
Bạn không làm việc một mình. Giữ thay đổi của người dùng và các agent khác;
không revert/ghi đè file ngoài phạm vi. Cần sửa file của owner khác thì gửi
đề xuất có vị trí/lý do cho điều phối, không tự sửa hoặc tạo thêm agent.
Giữ checkpoint/config/bundle/current.json, label schema, forward/preprocessing;
không thay production runtime, không commit/push/deploy/train.
Runtime/output riêng: [đường dẫn audit do điều phối cấp].
Acceptance: [các điều kiện kiểm được]. Tests: [nhóm/lệnh], chỉ chạy khi dependency
đã ổn định; inference nặng phải chờ lượt do điều phối cấp.
Kết thúc báo ID, files changed, contract differences, tests thực chạy/pass/fail/skip,
evidence paths, file hashes và vấn đề còn lại. Không gọi fixtures là model thật.
Nếu role QA/Review: review production code read-only, đưa findings có file/line,
tình huống tái hiện và ảnh hưởng; chỉ sửa tests/evaluation script được giao.
```

## J. Checklist hoàn tất và prompt bàn giao

### J1. Bảo toàn bản đã chạy tốt

- [ ] Đã đọc Git status/AGENTS lúc bắt đầu và giữ toàn bộ thay đổi có sẵn; không reset, clean, stash hoặc bỏ untracked để làm cây sạch.
- [ ] Không thay `demo/model.pt`, prepared config/provenance, active production bundle hoặc `runtime/models/neu/current.json`; hash trước/sau khớp.
- [ ] Không activate model khác để test; test roots/ports/data riêng; không import app ngoài sandbox runtime đã cấu hình.
- [ ] Không thay canonical labels, architecture forward hoặc preprocessing đã chốt; format 1/2 còn tương thích; UIT tiếp tục unavailable.
- [ ] Không mất prediction, revision, review history, export snapshot hay dữ liệu bền; migration additive, đã test DB v1 và concurrency.
- [ ] Chỉ dừng process do lượt test tạo; không chiếm cổng/dừng AnkiConnect hoặc app đang dùng.
- [ ] Không commit, push, deploy hoặc train khi người dùng chưa yêu cầu.

### J2. Sản phẩm và tính trung thực

- [ ] Attention cùng filter/run/source với list/export; missing-label denominator rõ; Toxic riêng; sort/ties và ít mẫu rõ.
- [ ] `needs_review` cũ giữ nguyên; top1/margin/reasons riêng task; missing/invalid scores không bị gọi an toàn.
- [ ] Human review tách AI signals; pending theo source prediction/revision; effective semantics không đổi.
- [ ] Policy version/hash/thresholds experimental được công bố; có report raw validation đúng identity hoặc giới hạn chưa đo; không dùng test/demo để tune.
- [ ] Sensitivity xác định một occurrence, Unicode/CRLF/whitespace chính xác; cặp cùng model và pipeline, baseline tính lại.
- [ ] Same-label delta đúng khi leader đổi; truncation/input-equal có giới hạn trung thực; không causal claim/heatmap giả.
- [ ] Job async có cancel/retry/recovery/identity fencing; không partial comparison; TTL/backup/source delete/readonly guards đúng.
- [ ] Source text/predictions/reviews/counts/exports không bị thí nghiệm sửa; kết quả muộn không gắn nhầm item/revision/selection.
- [ ] CSV cũ giữ header/semantics; filtered export theo signal đúng membership; GET snapshot cũ byte-identical sau restart/append/policy change.
- [ ] Desktop/mobile/keyboard và empty/loading/error/partial/stale states đã kiểm; build mới được dùng cho browser test.
- [ ] Data demo ghi rõ minh họa; reference không giả làm model; kịch bản có sửa nhãn do người dùng, không hứa trước câu cụ thể bị flag/flip.
- [ ] Có kết quả tests mới và report thực thi, phân biệt test doubles/real-model, nêu fail/skip/mục chưa nghiệm thu. F1/F2 là regressions đã được bảo vệ, không gọi lỗi còn mở.
- [ ] Đã ghi khả năng subagent thực tế, ownership và handoff; không có hai writer cùng file hoặc các lượt inference nặng tranh tài nguyên. Nếu không hỗ trợ subagent, đã báo fallback tuần tự trung thực.
- [ ] Có review độc lập trên bản implementation cuối khi harness hỗ trợ; findings vi phạm acceptance đã sửa và retest. Report agent không thay cho bằng chứng code/build/model được kiểm sau tích hợp.

### J3. Điểm chưa xác minh và cách đóng

| Chưa xác minh trong lượt lập kế hoạch | Gemini cần làm |
|---|---|
| Model/worker/browser đang hoạt động thế nào tại thời điểm thực thi | Kiểm environment/readiness bằng root tạm; không suy từ báo cáo 163/2 hoặc production load_verified lịch sử. |
| Hash checkpoint/bundle và readiness runtime hiện tại | T00 hash lại, T11 load bản copy đúng pointer và kiểm offline; không thay artifact nếu lỗi. |
| Coverage/error concentration của thresholds mới | T05 chạy validation raw đúng bundle/policy; thiếu điều kiện thì giữ experimental và nêu rõ chưa đo. |
| Latency/memory của cặp và tổng hợp 500 dòng | G4 đo thực tế, công bố điều kiện và giới hạn, không tạo SLA. |
| Predictions/flags/label flips trên 24 câu | Rehearsal H2 bằng model thật, ghi output và chọn luồng theo quy tắc; không chỉnh câu chỉ để ép flip. |
| Visual/browser behavior của tính năng chưa tồn tại | T02/T04/T08 browser tests và xem ảnh; khảo sát này chỉ dựa source/styles, chưa mở app. |
| Tính đại diện của validation cho phản hồi người dùng thực | Không thể chứng minh bằng repo; chỉ claim descriptive trên split đã biết, giữ human review và giới hạn phân phối. |

Các điểm này là công việc kiểm chứng, không phải câu hỏi sản phẩm cần hỏi lại người dùng. Quyết định sản phẩm thông thường đã chốt trong C–E.

### J4. Prompt đầy đủ cho Gemini

```text
Bạn là Gemini thực thi trong repository F:\DPL_NEU-ESC trên Windows/PowerShell.
Đọc docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md và AGENTS.md áp dụng.
Tài liệu này là nguồn quyết định sản phẩm/kiến trúc cho demo local ba lớp: Prediction,
Interpretability và Decision Support. Không cần lịch sử chat trước.

Bạn là agent chính điều phối và chịu trách nhiệm tích hợp/kiểm chứng cuối. Người dùng
đã cho phép dùng subagent trong lượt thực thi này. Nếu harness hỗ trợ native subagents,
dùng tối đa ba subagent Backend, Frontend, QA/Review theo ownership và các đợt I2–I7.
Giữ một owner xuyên suốt cho storage/API/worker/registry; một owner frontend; QA viết
tests và review độc lập, không tự sửa production implementation mà mình review.
Không chia ba lớp sản phẩm cho ba agent cùng sửa toàn stack. Không tạo agent lồng nhau.
Nếu chỉ có một slot, ưu tiên reviewer độc lập và tự thực thi tuần tự; nếu không có
subagent, báo rõ rồi thực thi tuần tự, không cài framework hay giả lập delegation.

Triển khai theo T00–T11 và nghiệm thu M0–M4: Chủ đề cần chú ý; tín hiệu top1/margin
riêng sentiment/topic cùng filter độc lập giữ semantics needs_review cũ; thử nghiệm
bỏ đúng một đoạn Unicode chạy baseline+variant cùng model/pipeline qua worker;
tích hợp dữ liệu minh họa, luồng review/thống kê/export và kiểm chứng thật.

Bắt đầu bằng khảo sát trạng thái mới và snapshot bảo toàn. Không reset/clean/revert
thay đổi của người khác. Không thay checkpoint, prepared config, production bundle,
current.json, label schema, forward hoặc preprocessing. Không coi các prompt F1/F2 cũ
là lỗi còn mở. Giữ ViSoBERT format 1 và PhoBERT format 2; UIT chưa có checkpoint riêng.

Trước mỗi đợt giao việc: chốt contract, dependency và file owner, cung cấp plan cùng
working tree hiện tại kể cả untracked/edits có sẵn. Không mặc định checkout từ HEAD
đã có đủ dữ liệu. Không để hai agent cùng sửa một file; muốn chuyển owner phải nhận
handoff và dừng writer cũ. Agent chỉ bàn giao diff/files/tests/evidence, không commit.
Bạn xử lý xung đột contract và yêu cầu sửa đúng owner; không ghi đè thay đổi đồng đội.

Chỉ thử trên runtime/model roots/data/ports tạm; không activate production model khác,
không khởi động/dừng app production, chỉ dừng process do chính lượt test tạo.
Không import services.api.main trước khi đặt FEEDBACK_RUNTIME tạm. Không commit,
push, deploy, train hoặc tải weights để thay thế artifact hiện có.

Chỉ chạy một lượt inference nặng tại một thời điểm, gồm validation, real-model tests,
rehearsal và benchmark; không pytest-xdist. Build frontend phải ổn định trước browser
acceptance. QA review theo I6, báo findings có file/line và tình huống tái hiện;
mọi lỗi vi phạm acceptance phải sửa/retest, không hạ test hoặc scope để tuyên bố pass.

Chủ động giải quyết lựa chọn triển khai thông thường theo plan. Nếu repo khác baseline,
đối chiếu code hiện tại, giữ edits mới và ghi khác biệt; chỉ hỏi khi thật sự không thể
giải quyết an toàn mà vẫn giữ phạm vi. Không mở rộng sang chatbot/LLM/LIME/SHAP/heatmap,
không fake prediction và không dùng test set để chọn thresholds.

Sau mỗi mốc chạy tests phù hợp. Cuối cùng build frontend, kiểm browser desktop/mobile,
chạy default suite và real_model opt-in trong root tạm; bảo vệ F1/F2 và CSV snapshot.
Khóa source/build trong lúc kiểm cuối, ghi hash của bản đã test; sau sửa phải cập nhật
evidence chịu ảnh hưởng. Không coi lời báo hoàn tất của subagent là nghiệm thu tích hợp.
Tạo báo cáo bằng chứng mới có lệnh/kết quả, model/policy identity, ảnh đã xem, đo performance
và mọi hạng mục chưa xác minh. Không gọi tests double là bằng chứng model thật.
Hoàn tất runbook demo 3–5 phút và kiểm hash artifact production trước/sau.
Trao đổi và viết tài liệu bằng tiếng Việt.
```

### J5. Trạng thái bàn giao của tài liệu này

Đã hoàn thành khảo sát source/metadata, kiểm raw/processed validation bằng standard library và chốt thiết kế. Theo yêu cầu tiếp theo của người dùng, đã bổ sung cách phân công subagent có ownership, các đợt tích hợp, review độc lập và cập nhật prompt Gemini; chỉ chỉnh tài liệu kế hoạch này. Chưa tạo dataset demo, code/schema/API mới, migration, dependencies, test mới hoặc kết quả model mới; chưa khởi động subagent triển khai. Không có yêu cầu Gemini phải sửa lại các công việc PhoBERT đã hoàn tất trước đây. Bước tiếp theo thuộc chat thực thi của người dùng.
