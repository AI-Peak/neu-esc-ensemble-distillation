# Contract attribution và network local · Codex 12/11/2026

Contract này mô tả implementation hiện hành, thay thế bản Gemini v1. Bằng chứng nghiệm thu ở `CODEX_WEBAPP_FIX_REPORT_2026-11-12.md`; contract không tự chứng minh test đã đạt.

## Nguồn và phép tính

Bảng giải thích **prediction AI nguồn**, kể cả khi người dùng đã sửa nhãn review. Raw snapshot là `item.text` server đã lưu; UI submit hiện trim đầu/cuối trước POST. Không normalize raw để render; UTF-16 offsets và SHA-256 lấy trên snapshot này, giữ whitespace bằng pre-wrap và text nodes.

Resolve `positive`/`negative` qua key case-insensitive của profile, ánh xạ vector qua thứ tự schema. NEU: Neutral0/Positive1/Negative2/Toxic3; UIT: negative0/neutral1/positive2. Target mặc định theo prediction: Positive/Negative -> `100*(p_positive-p_negative)`; nhãn khác -> `100*p_predicted`. Điểm là softmax chưa hiệu chuẩn. Polarity dùng xanh/đỏ nghiêng; label score dùng xanh lam/nâu và tăng/giảm điểm chính nhãn, kể cả Toxic.

Permutation Shapley **ước lượng K=8** (seed42, method2.0, grouping `raw_grapheme_compounds_v2`). Mask ID và special token policy lấy từ tokenizer. Không xóa token, không kéo phần ngoài cửa sổ đọc vào. Baseline che mọi content token; special tokens và attention positions giữ nguyên. Group partition bao phủ content IDs, gồm dấu câu/stopword. Mapping dùng NFD chỉ để đối chiếu raw grapheme, không đổi input model. Token fragments chung grapheme (combining mark, surrogate/skin tone/ZWJ) ghép cùng group. Phủ định/tăng cường ghép khi chắc chắn; >24 groups được gộp liền kề deterministic, không bỏ token. Pipeline chưa hỗ trợ hoặc truncation/mapping không chắc trả unsupported. Profile raw tokenizer chưa hỗ trợ attribution nhưng giữ prediction; UIT production thiếu checkpoint vẫn unavailable, không fallback NEU.

Cộng float64: `D=sum(phi)`, `B+D=f(x)`; cột cuối là **Tổng đóng góp D**. Residual nội bộ <=1e-6 điểm phần trăm. Full-input coalition phải khớp **cả vector sentiment và topic** của prediction: mỗi head max_abs_diff<=1e-5, label/schema khớp; target tolerance suy ra polarity0.002, label0.001 điểm phần trăm. Không clamp dấu/tổng hoặc dùng số bù. K=8/additivity không chứng minh nhân quả hay exact Shapley; masked inputs khác phân phối tự nhiên.

Prediction mới lưu execution_identity ngay trong registry forward: profile/schema/model/version, manifest SHA256, preprocessing SHA256, mode `cpu-fp32-eval`. Loaded bundle phải khớp identity trước/sau forward. Dữ liệu cũ thiếu provenance phải phân tích lại (409 PROVENANCE_REQUIRED), không tự nhận identity hiện tại. API không load torch/encoder.

## HTTP và vòng đời attribution

- POST `/api/v1/quick-analysis/{source_job_id}/attribution`, header **Idempotency-Key UUID bắt buộc**, body đúng `{source_prediction_id,target}`.
- Target strict: `{kind:"polarity_margin"}` hoặc `{kind:"label_score",label_id:<int thuộc profile>}`. Bool/float/âm/ngoài miền/field lạ bị từ chối422.
- 202 queued/running; 200 completed cache hợp lệ. Mỗi UUID riêng có handle riêng, kể cả completed cache. Cùng UUID cùng payload/source giữ handle; đổi payload/source409. Transport retry giữ UUID; terminal failure/cancel/new generation/target tạo UUID mới. Không coalesce in-flight giữa tab/handle.
- GET `/api/v1/attributions/{id}`: status queued/running/completed/failed/cancelled/unsupported. Completed gồm source, method, coverage, groups, aggregate, progress, error. Source IDs/revision/hash/execution_identity được freeze; GET kiểm lại source trước và sau registry inspection. Cache chỉ từ completed hợp lệ cùng full source/method/target signature.
- POST `/api/v1/attributions/{id}/cancel`: revoke lease và đánh dấu cancelled atomically nếu đang queued/running. Terminal trả trạng thái **thực tế**; completed không đổi và handle khác không bị tác động. POST/cancel kiểm same-origin (scheme/hostname/port; localhost alias chuẩn), không CORS rộng.
- HTTP404 không có nguồn/handle,410 biết nguồn hết hạn,409 nguồn/revision/model đổi hoặc chưa ready,422 request sai,429 queue đầy. Unsupported có mã/lý do ngắn, không có bảng tổng0 giả.

Migration **v4** nối tiếp migration3 không sửa schema đã áp dụng: attribution source/cache/checkpoint/compute/expiry, coalition vector evidence, network jobs. Prediction provenance ở payload mới; không backfill dữ liệu cũ bằng model hiện tại. Source prediction/run/count/export chỉ đọc, attribution không thành prediction giả.

Queue attribution tối đa10, một worker/encoder và concurrency attribution1; worker.lock chống hai process cùng runtime. Microbatch8 yield lease/progress để quick prediction được xử lý trước batch tiếp. Deadline compute60s bắt đầu claim đầu tiên, không tính chờ queue và không reset sau yield/resume; bounded source expiry. Cache reusable completed tối đa100, TTL<=900s và source expiry; handles/idempotency độc lập còn tới expiry. Cache hit không gia hạn source. Cleanup/source FK cascade/lease+attempt fencing ngăn worker muộn publish.

Checkpoint signature chứa full input IDs/groups/source identity/target/method/baseline/seed/budget. Mỗi mask unique/job; INSERT OR IGNORE và progress COUNT không đếm lặp. Resume kiểm signature, từng scalar khớp vector target, full two-head parity. Kiểm source sau inference, trước batch commit và completion transaction; không giữ transaction qua model forward. Model identity kiểm trước/sau mỗi microbatch và publication.

Client capture generation/source/target trước await cho POST/GET/cancel/retry; response POST cũ vẫn lấy handle và best-effort cancel đúng handle. Abort HTTP không chứng minh server hủy. Validator trước render kiểm source IDs/revision/SHA/model/schema/target, execution identity, finite values, raw slices, grapheme boundaries, partition và aggregate/parity. Dữ liệu lỗi chỉ hỏng attribution, prediction giữ lại. Poll700ms; lỗi network/5xx thử lại hữu hạn2 lần (3 requests/đợt), hồi phục GET giữ handle, không tạo prediction mới. Terminal/404/410/409/422 dừng poll. Progress fields historical tên completed_batches/total_batches hiện đếm **coalitions**, UI không bịa phần trăm.

Cancel recovery dùng request epoch và terminal guard: nếu server đã completed, GET khôi phục phải qua validator; phản hồi/lỗi từ poll cũ không được che kết quả này, kể cả trong lúc validation đang await.

## Bảng và tương tác

Desktop4 cột50/21/15/14, teal trắng; tổng cùng bảng. Top6 theo abs(phi), rồi thứ tự raw; mở đủ theo raw. Meter mỗi group abs(phi)/max(abs(phi_all_groups)); toàn0->0. Aggregate Các từ còn lại chỉ số, không meter. Mobile nguyên văn trên, hai cột từ/trọng số, tổng sau mọi dòng; method disclosure đóng mặc định. Keyboard/touch chọn hai chiều, focus rõ. Giữ font local Be Vietnam Pro/routes/import/review/export.

## Dataset summary, network và dẫn chứng

**Phạm vi demo cập nhật theo người dùng:** `#/demo` chỉ đọc summary/network/evidence của `item.dataset_id` và `run_id` thuộc prediction quick mới nhất hợp lệ, dùng nhãn AI. Một item giữ toàn văn nhập, có thể gồm nhiều câu; không tự tách câu hoặc cộng dồn các lần nhập. Không chọn dataset bền; edit/clear/profile change hoặc gửi văn bản mới sẽ bỏ scope cũ. Query key theo dataset/run/source/snapshot và response cũ không được thay kết quả mới. Không còn dataset selector hay thao tác lưu câu trong demo. API dataset/workspace nhiều câu và lựa chọn nguồn nhãn vẫn được giữ như dưới đây.

**Donut demo: Tỷ trọng đóng góp của cụm từ.** Chỉ dùng cùng attribution snapshot completed đã qua validator với bảng (source job/prediction/item/revision/text hash, profile/schema/model/execution identity, target và generation). Với toàn bộ groups gốc: `P=sum(max(phi,0))`, `N=sum(max(-phi,0))`, `M=P+N`; hai lát là `100*P/M` và `100*N/M`. `D=P-N=sum(phi)` vẫn là Tổng đóng góp trong bảng, giữ dấu và không clamp. “Các từ còn lại” là aggregate hiển thị, không cộng lại. Baseline, target_output, softmax, số lượng nhóm và summary counts không là lát biểu đồ. Không phát request/forward mới để tính tỷ trọng.

Polarity target dùng “Nghiêng tích cực” (xanh) / “Nghiêng tiêu cực” (đỏ); label_score dùng “Tăng điểm [tên nhãn]” (xanh lam) / “Giảm điểm [tên nhãn]” (nâu), resolve tên bằng label ID trong profile/schema. Dấu của contribution diễn tả chiều đóng góp vào target, không gán nhãn độc lập cho từ; tăng Toxic không được gọi tích cực. Tâm donut chỉ ghi “Đóng góp từ ngữ”. Đây là chart thông tin với SVG role img, mô tả screen reader và legend có chữ; không có handler lọc evidence, button/tabIndex/aria-pressed/cursor pointer.

Tỷ lệ tính ở full precision sau khi chia contribution cho max(abs(phi)) để tránh underflow/overflow ở tổng độ lớn. Chỉ hiển thị một chữ số thập phân: làm tròn số phần nghìn phía tăng, phía giảm lấy phần bù nguyên để cộng thành100,0%. Không tăng diện tích lát nhỏ bằng min-width/gap giả. Phía khác0 nhưng làm tròn0,0% có chú thích “Dưới0,05% trước làm tròn”. Mọi phi=0 hiển thị “Chưa có đóng góp khác0 để tính tỷ trọng”; không tạo lát trung tính hoặc50/50. Số không finite, tổng không finite, source/aggregate sai bị validator từ chối; tolerance tổng/residual giữ1e-6. Loading/error/unsupported/cancel giữ prediction và không render chart thay thế từ nhãn; retry/cancel recovery dùng nguyên ownership/idempotency/request epoch hiện hành. Chart độc lập với thời gian tải/lỗi summary.

Tỷ trọng là độ lớn đóng góp của Shapley K8 ước lượng, không phải tỷ lệ từ, xác suất cảm xúc hay kết luận nhân quả. Báo cáo mới: [CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md](CONTRIBUTION_DONUT_FIX_REPORT_2026-11-12.md).

Topic/evidence cùng dataset/profile/run/revision/source và normalized base filters. Click topic vẫn lọc evidence, không đổi base denominator. **Thống kê dataset** vẫn đếm phản hồi: net sentiment=100*(n_positive-n_negative)/n_valid_sentiment; Toxic trong denominator và đếm riêng. Semantics này không dùng cho contribution donut demo. Badge AI lấy prediction task; effective lấy effective, không fallback âm thầm. Reset selection/page khi source/scope đổi.

GET `/api/v1/datasets/{id}/network` nhận filters chuẩn như summary; trả queued/running/completed/failed + `network_id,scope_token,filter_signature,network_version,params,scope_item_count,source_item_count,nodes,edges,communities`. API chỉ snapshot các rows, worker mới chạy NLP; UI lazy khi mở/đến viewport. Queue10/cache100/TTL900s, failed không reuse; retry tạo job mới cùng snapshot. Không NLP trong API transaction. Worker.lock bảo vệ single worker, running network được tính lại an toàn sau restart; snapshot đổi trước publication -> failed SCOPE_CHANGED.

Population mặc định có sentiment hợp lệ đúng nguồn nhãn của summary dataset, kể cả partial labels/all-toxic; population này độc lập với độ lớn contribution trong donut demo. `cooccurrence-v2`: cửa sổ5 vị trí segmented tokens gốc trước lọc stopword (distance<=4), trong cùng câu, không xuyên phản hồi. Stopwords v2 giữ phủ định. Node/edge mỗi phản hồi chỉ góp1; edge IDs source::target; community counts union item IDs. Method **connected components**, layout deterministic sunflower v2, stable tie sorting; không Louvain/modularity/seed giả. Tối đa40 nodes/120 edges; không quan hệ -> empty. Tổng hợp đủ snapshot nhiều trang.

GET `/api/v1/networks/{network_id}/evidence?selection_type=node|edge|community&selection_id=...&page=1&page_size=10` server resolve membership từ graph đã lưu, không nhận item IDs làm chứng cứ. Kiểm network source scope/filter/expiry; graph cũ sau sửa text/review/run ->409, UI refresh và thông báo ngắn. Node/cạnh/cộng đồng chọn bằng keyboard; mobile có picker. Token snapshot không thay filter identity.

## LLM và vận hành

Không khởi tạo provider/service, không client API/types/help/config 9router trong luồng hiện hành. Legacy endpoint explanation luôn410 (sau Origin check), kể cả truyền kwargs cấu hình cũ; kwargs chỉ giữ compatibility, không bật lại. Không xóa httpx dùng ở nơi khác hoặc sửa lịch sử nghiên cứu. Báo cáo Gemini cũ có chỉ dẫn superseded.

Chạy API+worker bằng `scripts/start-local.ps1 -RuntimeDirectory <isolated-runtime> -Port <free-port>`; dừng cùng runtime bằng stop-local.ps1. `python -m services.api.main` chỉ import app rồi thoát, không phải server. Xem LOCAL_APP và report cho URL/runtime đã xác minh. Không commit/push/train/thay weights hoặc chạm live DB để kiểm thử.
