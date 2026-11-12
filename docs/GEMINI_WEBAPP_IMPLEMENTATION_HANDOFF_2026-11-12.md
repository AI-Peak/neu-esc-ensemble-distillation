# Bàn giao Gemini: triển khai webapp theo góp ý của Đạt

Ngày: 12/11/2026. Repository: `F:\DPL_NEU-ESC`. Shell: PowerShell.

Bản rà soát lần 2: đã làm rõ nguồn nguyên văn, target/màu, partition token, tiêu chí số học và vòng đời job/cache. Những ngưỡng hiệu năng bên dưới là mục tiêu UX để đo khi thực thi, không phải kết quả benchmark đã có.

## 1. Nhiệm vụ và thứ tự ưu tiên

Triển khai vào webapp React + FastAPI hiện có, dựa trên mockup mới nhất tại `design-previews/2026-11-12/`. Đây là yêu cầu thực thi, không phải làm thêm một prototype.

Ưu tiên quyết định theo thứ tự:

1. Yêu cầu mới nhất của người dùng và nội dung góp ý của Đạt trong phần 2.
2. Bản bàn giao này.
3. Mockup mới nhất: bố cục và tương tác; dữ liệu của mockup không phải dữ liệu production.
4. `PRODUCT.md`, `DESIGN.md`, các nguyên tắc dữ liệu/model hiện có.
5. Tài liệu phân tích cũ dùng để tham khảo cơ chế ảnh, không giữ những lựa chọn UI đã được thay thế.

Không tự quay về phương án 9router/LLM, ba khối lớp, hoặc thiết kế mockup đời trước ngày 12/11.

## 2. Yêu cầu gốc phải được nghiệm thu

Đạt yêu cầu:

> Bỏ các câu dư thừa như “Văn bản gốc luôn được giữ nguyên”, “Thử nhanh với một câu mẫu”, “Dịch vụ sinh viên”, “Trải nghiệm học tập”, “Một thông báo”. Bỏ các khối lớp 1, lớp 2, lớp 3. Phần dự đoán hiện tại tương đối ổn; thêm highlight từ quan trọng như ảnh xanh/đỏ. Thay cách trình bày hai lớp còn lại bằng bảng có cột như ảnh. Nếu được thì thêm hai visualization.

Người dùng bổ sung:

- Quan trọng nhất là hình 1 phải làm được.
- Có thể bỏ hai khối lớp 2/3 hiện tại và bỏ phương án LLM.
- Muốn cách trình bày sát ảnh nhất có thể.
- Tên **Tổng đóng góp** được chấp nhận.
- **Giữ các thanh đo nhỏ** cạnh trọng số.
- Chat thực thi sẽ dùng Gemini; được phép dùng subagent nếu giúp tăng chất lượng.

Ý nghĩa sản phẩm ban đầu vẫn là: dự đoán cảm xúc/điểm/chủ đề; hiểu dự đoán qua từ ngữ; tìm vấn đề và thống kê theo topic. Không cần dùng tên “lớp” để trình bày những năng lực đó.

### Ma trận truy vết

| ID | Yêu cầu | Thay đổi cụ thể | Tiêu chí |
|---|---|---|---|
| R01 | Bỏ chữ thừa | Xóa riêng câu phụ “Văn bản gốc luôn được giữ nguyên”, nhóm câu mẫu và copy lặp trong demo | Giữ nguyên nội dung phản hồi và cột Phản hồi của R04 |
| R02 | Bỏ các khối lớp | Bỏ nhãn lớp và cấu trúc diễn giải cũ | Không đổi tên rồi giữ nguyên các đoạn dài |
| R03 | Giữ prediction | Giữ sentiment, điểm, topic và phân bố nhãn truy cập được | Dùng đúng classifier local hiện tại |
| R04 | Hình 1 | Nguyên văn / từ quan trọng / trọng số / tổng | Trọng số có nguồn, tổng kiểm tra được |
| R05 | Hình 2 | Highlight cụm từ liên kết với bảng | Chọn hai chiều, đúng occurrence và ngữ cảnh |
| R06 | Giữ thanh nhỏ | Thanh độ lớn mỗi trọng số | Cùng một quy tắc chuẩn hóa, không giả confidence |
| R07 | Bỏ LLM | Loại tích hợp khỏi production và help/config liên quan | Không phát sinh outbound request diễn giải |
| R08 | Hình 3, bổ sung | Donut + thống kê topic + dẫn chứng | Đếm thật, đủ nhãn, cùng scope |
| R09 | Hình 4, bổ sung | Mạng đồng xuất hiện từ/cụm từ | Node/cạnh có dữ liệu và mở được dẫn chứng |

R01–R07 là P0. R08 là P1. R09 là P2. Làm theo thứ tự này; việc hoàn thành P1/P2 không bù cho P0 chưa đạt. Khi P0 đạt, tiếp tục P1/P2 trong phạm vi và nguồn lực cho phép, không tự dừng chỉ để hỏi lại những việc đã được mô tả.

Báo riêng trạng thái **P0 / P1 / P2**. P2 chưa làm không biến P0 đã đạt thành thất bại, nhưng không được nói “toàn bộ yêu cầu hoàn tất” nếu còn phần chưa thực hiện. Nếu dừng phần bổ sung, ghi lý do/blocker cụ thể và công việc còn lại; không tự bỏ vì đã thấy phần trước “đủ tốt”.

## 3. Tài liệu đầu vào cần đọc

- `docs/TEAMMATE_FEEDBACK_IMAGE_ANALYSIS_PLAN_2026-11-12.md`: phân tích bốn ảnh, nguồn dữ liệu và giới hạn.
- `design-previews/2026-11-12/index.html`, `styles.css`, `mockup.js`: mockup mới nhất.
- `design-previews/2026-11-12/reference-table-desktop.png`: ảnh chuẩn phần trọng tâm, cần mở bằng công cụ xem ảnh.
- `design-previews/2026-11-12/analysis-desktop.png`, `analysis-mobile.png`, `mockup-desktop.png`: bố cục và responsive.
- `design-previews/2026-11-12/README.md`: phân biệt fixtures với chức năng thật.
- `PRODUCT.md`, `DESIGN.md`: nền tảng app.
- `apps/web/src/SentenceDemo.tsx`, `SentenceDemo.css`, `api.ts`, `types.ts`, `demoPrediction.ts`.
- `services/inference/registry.py`, `preprocessing.py`, `architecture.py`; `services/sensitivity.py`, `worker.py`, `storage/db.py`, `api/main.py`.
- `services/analytics.py`, `demo_scope.py`, `profiles.json`.
- Tests tương ứng trong `tests/api`, `tests/inference`, `tests/e2e` và `tests/test_runtime_isolation.py`.

Mockup không gọi model: nhãn, điểm, trọng số, node positions và communities được dựng để duyệt thiết kế. Tuyệt đối không copy chúng làm fallback production. Dữ liệu demo tác giả tạo có thể dùng trong tests hoặc bộ dữ liệu nhập minh họa có ghi nguồn, không giả như kết quả model đã chạy.

Tại thời điểm bàn giao, plan và thư mục mockup đang untracked. Chúng là tài sản của công việc trước, không được xóa/reset. Kiểm lại git status trước sửa; trạng thái ở chat mới có thể đã khác.

## 4. Thiết kế phải giữ

### Bảng hình 1

- Bốn cột desktop, tỷ lệ tham chiếu khoảng **50% / 21% / 15% / 14%**.
- Header xanh teal liền mạch, chữ trắng. Tên cột: **Phản hồi / Từ quan trọng / Trọng số cảm xúc / Tổng đóng góp**.
- Dòng phụ tiếng Anh như mockup: Consumer comment, Meaningful words, Sentiment weight. Cột cuối ghi “Tổng các trọng số”, không đổi tên sang confidence.
- Phản hồi nguyên văn ở cột lớn bên trái, giữ dấu câu/khoảng trắng/Unicode. Từ tích cực xanh đậm; từ tiêu cực đỏ nghiêng theo target phù hợp.
- Danh sách cụm từ ở giữa, trọng số căn ngang đúng từng cụm. Giữ các thanh đo nhỏ.
- Một tổng căn giữa trong cột cuối, nền trắng, số trung tính; không biến thành một thẻ KPI riêng.
- Công thức, baseline và phương pháp nằm trong **Cách tính tổng** dạng mở rộng. Không đưa cả đoạn diễn giải thường trực vào bảng.
- Tên “Các từ còn lại” chỉ dùng khi thực sự có các nhóm bị ẩn, kèm tổng thật của chúng.
- Highlight có thể chọn từ câu hoặc từ dòng bảng, trạng thái chọn đồng bộ. Keyboard/touch không phụ thuộc hover.

### Luồng trang

1. Nhập phản hồi và kết quả dự đoán hiện tại.
2. Bảng từ ngữ/đóng góp ngay bên dưới, đủ chiều rộng.
3. Tổng quan bộ phản hồi có bộ chọn dataset và nguồn nhãn thật.
4. Network và danh sách phản hồi dẫn chứng.

Giữ font Be Vietnam Pro, nhận diện teal, điều hướng chính. Mobile đưa nguyên văn lên trên, từ và trọng số thành hai cột, tổng ở dưới. Tablet có nguyên văn phía trên và ba vùng phân tích bên dưới. Không ép bốn cột hẹp trên điện thoại.

Mockup đã bỏ các control lựa chọn dataset/profile vì chỉ có một fixture. App thật vẫn phải giữ các lựa chọn cần thiết để xác định dữ liệu, nhưng bố trí gọn. Không copy sự thiếu control của mockup vào app thật.

Không viết lại toàn bộ app. Các route datasets/research/help, lưu câu vào dataset, import, duyệt nhãn, revision và CSV export phải tiếp tục hoạt động.

**Snapshot nguyên văn chuẩn:** bảng, text hash và mọi offset dùng đúng `item.text` server đã lưu cho prediction nguồn. Code hiện tại trim trước khi POST; không lấy offset trên bản server nhưng render textarea trước trim hoặc đang sửa. Nếu thay đổi việc trim để giữ cả khoảng trắng đầu/cuối, làm nhất quán từ submit đến lưu trữ/render/test. Không normalize raw text trong renderer; dùng `white-space: pre-wrap` và text nodes để giữ xuống dòng/khoảng trắng, không render HTML của người nhập.

Bố cục theo mockup nhưng contrast phải đạt mức đọc được: 4,5:1 cho chữ thường, 3:1 cho chữ lớn. Được điều chỉnh sắc độ teal/xanh/đỏ để đạt contrast, không đổi cấu trúc hoặc nhận diện. Caption/nhãn tối thiểu 14px, nội dung phản hồi tối thiểu 16px; outline/selection không chỉ phụ thuộc màu.

## 5. Trọng số và tổng: chốt trước khi code UI production

Ảnh gốc chỉ cho thấy phép cộng trọng số; không cho biết thuật toán tạo trọng số. Shapley là **đề xuất của kế hoạch**, không phải yêu cầu Đạt đã đặt ra. Mục tiêu là hình 1 hoạt động trung thực, hữu ích và giải thích được nguồn số.

### Hướng chính: attribution trực tiếp từ classifier local

Với Positive/Negative, dùng hàm mục tiêu:

```text
f(x) = 100 × (p_Positive(x) − p_Negative(x))
weight_i = phi_i
total_contribution = sum(phi_i)
target_output = baseline_value + total_contribution
```

- Các p là điểm softmax chưa hiệu chuẩn; không gọi là xác suất đúng.
- Đơn vị: điểm phần trăm. Dấu của phi thể hiện ảnh hưởng lên hàm mục tiêu, không phải một nhãn độc lập của từ.
- Tổng ở cột cuối chính là sum(phi), không lấy target_output khi baseline khác 0.
- Cùng một từ xuất hiện hai lần phải có ID/span riêng; có thể có hai điểm khác nhau. Không tự ghi `w × 2` khi điểm khác nhau.
- Thanh nhỏ: `abs(phi_i) / max_j(abs(phi_j))` trên cùng một bảng; toàn số 0 thì thanh 0. Đây không phải tỷ lệ đóng góp trên tổng và không phải confidence.
- Tổng và residual tính bằng giá trị đầy đủ; làm tròn khi hiển thị. Nếu số hiển thị lệch tổng do làm tròn, nói rõ trong phần cách tính; không sửa trọng số để khớp bằng mắt.
- “Các từ còn lại” là tổng những attribution thực sự đã tính, không phải số bù tùy ý để đạt một tổng đẹp.
- Resolve Positive/Negative theo `key` của profile, không hardcode label index vì NEU/UIT khác thứ tự. Metadata phải lưu target cụ thể, không chỉ nhãn tiếng Việt hiển thị.
- `f(x)` nằm trong `[-100, 100]`, nhưng đóng góp và tổng chênh lệch với baseline có thể nằm trong `[-200, 200]`. Không clamp trọng số/tổng về `[-100, 100]`, không chia lại để ép thành 100%.
- Chọn tối đa 6 nhóm có `abs(phi)` lớn nhất để hiện ban đầu, sau đó xếp theo vị trí trong câu; nếu còn nhóm ẩn thì thêm “Các từ còn lại” và nút xem đủ. Đây là quy tắc hiển thị, không được loại token khỏi phép tính. Mẫu số thanh đo lấy max trên các nhóm gốc đã tính, không tính dòng tổng nhóm ẩn; dòng “Các từ còn lại” chỉ hiện số để tránh bị hiểu là một từ.

Target mặc định: prediction Positive/Negative dùng `polarity_margin`; prediction Neutral/Toxic dùng `label_score` của đúng nhãn dự đoán, tức `100 × p_label(x)`. Hiện một dòng ngắn “Đang xem: cân bằng tích cực/tiêu cực” hoặc “Đang xem: đóng góp cho nhãn [tên]”.

Với `polarity_margin`, dùng xanh/đỏ như mockup và chú giải nghiêng tích cực/tiêu cực. Với `label_score`, đổi chú giải thành **tăng/giảm điểm [nhãn]**, dùng xanh lam/nâu với dấu `+/-` để không lẫn với màu sentiment; đầu cột trọng số ghi rõ “cho nhãn [tên]”. Không tô tăng Toxic thành xanh rồi gọi “tích cực”. Tên cột cuối vẫn là Tổng đóng góp. Không bắt buộc có control đổi target ở P0; nếu có, request/cache/legend đều phải đổi cùng nhau.

### Thuật toán khởi điểm

Permutation Shapley theo nhóm từ: trung bình marginal contribution của các nhóm theo nhiều hoán vị đầy đủ. Mỗi đường đi đi từ baseline đến toàn input, nên tổng đóng góp bằng chênh lệch hai đầu trong sai số số học.

- Chạy cùng checkpoint, mode CPU FP32 eval, preprocessing và tokenizer với prediction nguồn.
- Che BPE token của nhóm bằng mask token hợp lệ; không xóa đầu chuỗi rồi kéo phần ngoài 128 token vào vùng đọc.
- Giữ special tokens và padding/attention mask đúng quy ước. Baseline và tokens luôn hiện diện phải được ghi trong method metadata.
- Grouping có phiên bản, bao phủ đúng tập token được thay đổi. Giữ phủ định/cường độ trong cụm khi ánh xạ đủ chắc chắn.
- Các nhóm tạo thành partition: không chồng lấp, không bỏ sót token thuộc tập được giải thích; mọi token giữ cố định phải có policy rõ. Dấu câu/stopword không được âm thầm loại khỏi cả baseline lẫn tổng. Khi không có nhóm hợp lệ, trả `unsupported`, không trả completed với tổng 0 giả.
- Truncation có thể cắt giữa các BPE của một từ. Không highlight cả từ/cụm nếu model chỉ thấy prefix mà không ánh xạ được chính xác prefix về raw. Bản P0 được phép báo attribution chưa hỗ trợ trường hợp này; phải giữ prediction và cảnh báo. Các câu thường, không cắt ngắn, không được lấy unsupported làm đường tránh triển khai.
- Không tự giả định tokenizer chậm hỗ trợ offset mapping. Xây mapping raw → segmented text → BPE bằng thuật toán kiểm chứng được.
- Nếu dùng tokenization theo từ để dựng mapping, phải assert chuỗi IDs ghép lại khớp tokenization nguyên câu; sai thì không trả attribution.
- Với normalization, giữ ánh xạ về raw; không lấy offset normalized gắn lên raw. Dùng UTF-16 bên UI và kiểm grapheme như `services/sensitivity.py`.
- Không thêm gradient vào đường prediction hoặc thay architecture/checkpoint chỉ để dễ giải thích.

Additivity kiểm phép tính, không chứng minh độ đúng ngữ nghĩa của lời giải thích. Đầu vào che nhiều token khác phân phối phản hồi tự nhiên; kết quả phụ thuộc baseline và grouping. Ghi giới hạn ngắn trong Cách tính tổng và report, không viết “model suy nghĩ như vậy” hoặc tuyên bố nhân quả chỉ vì residual nhỏ.

## 6. M0: kiểm chứng nhỏ, hữu hạn trước triển khai

Chạy spike local có thể giữ thành module/test nếu đạt. Không triển khai một framework nghiên cứu attribution lớn.

Kiểm tra 12–20 câu do tác giả viết, đa dạng: khen, chê, vừa khen vừa chê, trung tính, Toxic, phủ định, tăng cường, từ lặp, emoji, NFC/NFD, nhiều dấu câu, đoạn dài/cắt ngắn. Không dùng test split benchmark để chọn cách giải thích cho đẹp.

| Kiểm chứng | Bằng chứng cần lưu |
|---|---|
| Model nguồn | Model/version/schema/hash và preprocessing identity |
| Mapping | Spans chính xác, raw slices khớp, token IDs đúng, boundary không cắt grapheme |
| Prediction parity | Điểm full-input khớp prediction nguồn với tolerance đo được và ghi lại |
| Additivity | baseline + sum(phi) = output; residual hữu hạn, đạt ngưỡng ở mục nghiệm thu số học bên dưới |
| Stability | So dấu/ranking trên ít nhất hai tập permutation độc lập cho vài câu; đánh dấu phần thiếu ổn định |
| Chi phí | Số group, permutation, coalition unique, thời gian cold/warm, peak memory |
| Hàng đợi | Prediction mới không phải chờ toàn bộ một attribution dài |

**Ngưỡng nghiệm thu số học:** so full-input probability vector với prediction nguồn bằng `max_abs_diff <= 1e-5` cho cả hai head, đồng thời label/schema/identity khớp. Target polarity theo đơn vị điểm phần trăm có sai lệch tối đa suy ra `0.002`; label score tối đa `0.001`. Tính cộng dồn phi bằng float64 trên coalition outputs đã cache; additivity residual nội bộ của cùng lần tính phải `<= 1e-6` điểm phần trăm. Không đánh đồng sai số parity hai lần inference với residual nội bộ. Nếu chưa đạt, điều tra thứ tự batch, dtype, eval, tokenization, identity trước; không nới ngưỡng chỉ để test xanh.

Độ ổn định là mục riêng: báo sự thay đổi dấu/ranking của nhóm mạnh giữa ít nhất hai tập hoán vị, không gọi độ lệch chuẩn Monte Carlo là “độ tin cậy của dự đoán”. Nếu ngân sách mẫu quá nhỏ để kết luận, đánh dấu giải thích xấp xỉ/thiếu ổn định và không làm đậm kết luận về một từ; không tự sửa dấu theo trực giác.

Ngân sách khởi điểm: 8 hoán vị, khoảng 24 nhóm tối đa cho chế độ tương tác; batch khoảng 8 hoặc thấp hơn nếu cần. Đây là cấu hình để đo, không SLA. Với G nhóm và K hoán vị, cận `K×(G−1)+2` coalition trước deduplicate.

**Ngân sách vận hành khởi điểm:** đo ít nhất 20 lượt warm trên các câu khác nhau trong tập tác giả viết, báo median/p95/max và cold-start riêng. Mục tiêu auto-run: warm p95 không quá 15 giây cho input trong phạm vi hỗ trợ. Nếu vượt sau tối ưu hữu hạn, chuyển attribution sang nút “Phân tích từ ngữ” có tiến độ, giữ prediction hiện ngay và báo lựa chọn này trong report. Deadline compute mặc định 60 giây và không vượt source expiry; concurrency attribution 1 trong worker, hàng đợi tối đa 10 work items với phản hồi bận/retry, cache thành công tối đa 100 mục và TTL tối đa 900 giây hoặc vòng đời nguồn nếu ngắn hơn. Đây là cấu hình server có thể điều chỉnh bằng bằng chứng M0, không phải lời hứa tốc độ.

Kiểm scheduling bằng thứ tự thực thi: khi đang tính attribution và có quick prediction mới, sau microbatch attribution hiện hành phải có cơ hội chạy quick prediction trước microbatch attribution tiếp theo. Chốt batch size để một batch không chiếm quá ngân sách tương tác đo được. Dùng cơ chế microbatch hiện có trong `Worker.run_once`; không tạo scheduler framework mới.

Nếu nhiều nhóm hơn giới hạn, không âm thầm bỏ token. Có thể gộp nhóm liền kề theo quy tắc có phiên bản và hiển thị đúng granularity, hoặc báo giới hạn cho input đó. Chỉ trả kết quả từ các hoán vị hoàn chỉnh; một job bị hủy không được có bảng tổng hoàn chỉnh giả.

**Điểm quyết định M0:**

1. Mapping và phép cộng đúng, latency phù hợp: triển khai attribution async.
2. Tính đúng đạt nhưng latency cao: tối ưu batch/cache/grouping và cơ chế tính theo yêu cầu; ghi rõ lựa chọn UX. Không đoán con số latency chưa đo.
3. Mapping/tính đúng chưa đạt: tiếp tục sửa trong phạm vi hữu hạn; nếu thành blocker thật, báo cụ thể. Không coi chỉ đổi UI là hoàn tất R04.
4. Từ điển local là phương án thay thế cần trình bày rõ với người dùng nếu phải đổi semantics. Nó có thể giống phép cộng số nguyên của ảnh, nhưng phải gọi là điểm theo từ điển, không là đóng góp PhoBERT. Không tự đổi âm thầm.

Cấm cộng các delta che từng từ độc lập rồi gọi đó là Shapley hoặc tổng đóng góp model. Không dùng attention như bằng chứng đóng góp sentiment có dấu.

## 7. Contract đề xuất và lifecycle

Root agent viết contract trước khi giao frontend/backend làm song song. Có thể đổi tên endpoint nội bộ nếu giải thích rõ; giữ semantics dưới đây.

```text
POST /api/v1/quick-analysis/{source_job_id}/attribution
  header: Idempotency-Key: <UUID riêng cho generation + target + lần thử>
  body: { source_prediction_id, target }
  response: 202 { attribution_id, status } khi tạo/đang chờ;
            200 { attribution_id, status: completed } khi tái dùng kết quả hợp lệ

GET /api/v1/attributions/{attribution_id}
POST /api/v1/attributions/{attribution_id}/cancel
```

Không nhận text/model/score do client tự gửi để làm nguồn tính. Server đọc prediction, raw text và revision từ nguồn hợp lệ. Target nằm trong allowlist theo profile. Ngân sách, seed và baseline là cấu hình server có phiên bản.

`target` có đúng một trong hai dạng: `{ kind: "polarity_margin" }` hoặc `{ kind: "label_score", label_id: <id thuộc sentiment profile> }`. Không chấp nhận NaN/Infinity/boolean làm ID hoặc số trọng số. JSON schema strict với field lạ bị từ chối. GET trạng thái không gửi lại text từ client.

Payload kết quả cần:

```text
status: queued | running | completed | cancelled | failed | unsupported
source: source_job_id, source_prediction_id, item_id, revision_id,
        run_id, text_hash, profile_id, schema_id, model_id, model_version,
        execution_identity
method: id, version, grouping_version, baseline_policy, target,
        unit, seed, requested_permutations, completed_permutations,
        evaluated_coalitions
coverage: truncated, input_token_count, mapping_status, analyzed_spans,
          fixed_token_policy, explained_token_indices
groups[]: id, text, start_utf16, end_utf16, token_indices,
          contribution, optional stability metadata
aggregate: baseline_value, total_contribution, target_output,
           additivity_residual, optional hidden_groups_contribution
progress: completed_batches, total_batches_if_known
error: code, short user-facing message
```

Frontend có thể chọn vài nhóm nổi bật để hiển thị nhưng backend giữ đầy đủ kết quả để kiểm tổng. Hiện nhóm theo thứ tự xuất hiện để dễ đối chiếu; nếu có nhiều nhóm, mở thêm và tổng phần còn lại rõ ràng.

Cache key gồm text/revision/source prediction, execution identity, preprocessing/grouping/method/baseline/target và ngân sách. Không cache lỗi. Có giới hạn dung lượng và TTL, không vượt vòng đời nguồn quick-analysis. Retry cùng Idempotency-Key không tạo thêm job nặng.

**Idempotency/cancel đơn giản cho P0:** retry cùng thao tác giữ nguyên Idempotency-Key và nhận cùng handle; cùng key nhưng khác body/source trả 409. Generation mới, target mới hoặc thử lại sau terminal failure/cancel dùng key mới. Các key độc lập có handle/job độc lập; P0 không coalesce compute đang chạy giữa các handle, chỉ chia sẻ cache kết quả đã hoàn tất. Vì vậy tab A clear input chỉ cancel handle của A. Nếu sau này coalesce in-flight, bắt buộc thêm subscription/detach và test hai tab trước khi bật. Không cần xây subscription framework cho P0.

Abort HTTP/polling không thay thế cancel server. POST tạo job trả muộn vẫn phải nhận ID rồi cancel nếu generation không còn hợp lệ. Cancel idempotent, không sửa job/run prediction nguồn; công việc completed không bị sửa kết quả bởi một lệnh cancel đến muộn. Retry giữ semantics nguồn và tạo attempt mới, không kế thừa kết quả của permutation dở dang.

**Kiểm nguồn bắt buộc:** dùng `validate_quick_source` trong giao dịch ngắn trước lookup/serve cache, sau inference và trước commit/publication. GET completed cũng kiểm lại expiry/revision/identity; key cache đúng chưa đủ nếu nguồn đã xóa/sửa. Deadline hiệu lực là min(deadline job, source expiry); đọc cache không gia hạn nguồn. Quick source hiện hết hạn 900 giây sau kết thúc; cleanup/delete phải fence mọi attribution liên quan và dọn cache/idempotency để worker muộn không tái tạo kết quả đã mất nguồn.

Xử lý lỗi phân biệt: nguồn không có/đã hết hạn, prediction chưa sẵn sàng, identity đổi, mapping không hỗ trợ, quá dài, model unavailable, lỗi inference, hủy. Không đưa traceback/raw text hoặc đường dẫn nhạy cảm ra thông báo.

Contract HTTP: 404 nguồn/handle không còn tồn tại; 410 khi biết nguồn đã hết hạn; 409 source/model/revision conflict hoặc prediction chưa ready; 422 target/input/idempotency header không hợp lệ; 429 queue đầy; GET work item tồn tại trả 200 cùng trạng thái failed/unsupported/cancelled và mã lỗi để UI hiển thị. Không tự retry vô hạn lỗi 409/410/422. Chốt timeout/retry/backoff và tiến độ trong contract; progress không có mẫu số xác định thì dùng trạng thái đang chạy, không giả %.

Giữ kiểm Origin cùng origin hợp lệ cho POST nặng/cancel như luồng explanation hiện tại, với policy localhost được kiểm đúng hostname/port; không xóa bảo vệ này khi xóa endpoint LLM. Không mở CORS rộng. Phản hồi/quy tắc rate limit không chứa secrets hoặc raw text.

### Storage/worker: giới hạn tích hợp quan trọng

`jobs.run_id` hiện là UNIQUE và các hàm `Worker.claim/finish` cập nhật trạng thái run; không nhét attribution vào job prediction nguồn rồi làm sai lifecycle. Mặc định tạo bảng work item attribution riêng, cùng worker process điều phối; source prediction/run chỉ được tham chiếu đọc. Không tạo fake dataset/run để đựng coalition. Chỉ chọn cách tích hợp khác nếu root chứng minh đơn giản hơn và giữ đầy đủ invariants, ghi quyết định trong contract trước khi giao việc.

Bảng mới cần attempt/lease fencing, cancel flag, source identity, idempotency key, progress và checkpoint đã commit. Lưu coalition output theo bitmask nhóm + method identity; một batch/attempt commit lặp không được cộng phi hoặc progress hai lần. Microbatch yield có checkpoint bền vững, release lease đúng; resume kiểm identity và chỉ tiếp tục checkpoint hợp lệ. Không lưu tensor/model nặng trong SQLite. Hai worker process vẫn phải tuân thủ `worker.lock` hiện tại.

Ưu tiên thay đổi nhỏ, không viết lại scheduler toàn hệ thống. Migration mới phải transactional/idempotent; không sửa MIGRATION_1/2 đã áp dụng. Nếu thêm schema version, cập nhật kiểm thử/health/docs/backup tương ứng; một số tests hiện assert version 2.

Chỉ một encoder resident theo thiết kế hiện tại. API không load torch/model nặng; attribution chạy ở worker. Không khóa SQLite suốt inference. Worker phải kiểm hủy/lease/source giữa batch.

**Priority không tự tạo preemption:** attribution phải yield giữa batch/đơn vị công việc để worker có thể nhận prediction ưu tiên hơn. Nếu giữ một lock xuyên 186 lượt chạy thì đổi priority không giải quyết latency. Thiết kế bounded step/checkpoint/resume, hoặc ghi rõ limitation và sửa trước nghiệm thu concurrency.

## 8. Frontend P0 và loại LLM

File chính: `SentenceDemo.tsx`, `SentenceDemo.css`; có thể tách `HighlightedFeedback.tsx`, `AttributionTable.tsx`, hook `useAttribution.ts` theo nhu cầu.

1. Giữ form, profile selector, nút phân tích/hủy, prediction validation và lưu vào dataset.
2. Xóa nhóm mẫu, câu copy thừa, nhãn lớp và khối `reading/caution`.
3. Prediction xuất hiện ngay khi có; attribution là trạng thái riêng, tự chạy cho input được hỗ trợ sau khi M0 đạt ngân sách phù hợp.
4. Giữ generation ownership cho toàn bộ callback async, kể cả POST trả muộn, cancel/retry/add-to-dataset. Không thay cơ chế hiện tại bằng một check jobId đơn giản.
5. Clear/edit/profile change phải invalidate kết quả cũ, cancel khi biết job ID; callback muộn không được gắn sang input mới.
6. Giữ warning input 128 token, missing model, schema mismatch, score invalid. Không tô phần model chưa đọc.
7. Không có attribution thì prediction vẫn đọc được; không show tổng 0 như kết quả hợp lệ.
8. Cờ khó phân loại chỉ xuất hiện khi có tín hiệu; không tạo khối “không có cờ” dài.
9. Sensitivity thủ công có thể giữ trong một phần mở rộng nhỏ; không chiếm vị trí chính của bảng mới.
10. NEU/UIT lấy nhãn từ profile; UIT thiếu checkpoint vẫn unavailable, không fallback NEU.

Client kiểm contract kết quả trước render: source IDs/hash/model/target khớp generation hiện hành, các số finite, spans nằm đúng raw snapshot và không chồng lấp, aggregate khớp tổng trong tolerance. Dữ liệu không hợp lệ → attribution error, prediction vẫn giữ; không ép payload sai thành giá trị 0. Target label_score không dùng chú giải polarity.

Loại LLM production: client `getExplanation`, types, effects/state, endpoint/service initialization, provider module nếu không còn caller, help/settings/scripts/docs liên quan. Kiểm dependency `httpx` trước khi xóa vì còn có thể dùng ở phần khác/tests. Không đọc/in biến môi trường secret. Không sửa lịch sử báo cáo cũ như thể LLM chưa từng tồn tại; chỉ cập nhật hướng dẫn vận hành hiện hành và ghi superseded khi cần.

## 9. P1: donut và hỗ trợ quyết định

- Dùng Summary API có sẵn; số đếm và mẫu số thật, không lấy softmax một câu vẽ thành tỷ lệ dataset.
- NEU đủ Neutral/Positive/Negative/Toxic; UIT theo schema của nó.
- `net = 100 × (n_positive − n_negative) / n_valid_sentiment`. Toxic ở mẫu số, không cộng vào Negative.
- Hiển thị số có nhãn / tổng khi chưa xử lý hết. Không có nhãn thì empty state.
- Topic ranking dùng `negative_count_desc` hiện có; hiện `n_negative/n_eligible`, Toxic riêng và low-sample indicator hợp lý.
- Click lát donut/topic mở danh sách phản hồi theo lựa chọn. Có hành động xóa bộ lọc, phân trang.
- Cùng dataset/profile/label_source/run/revision scope với summary. Kiểm scope token khi mở dẫn chứng; refresh nếu dữ liệu đổi.
- Câu nhập quick-analysis không tự trở thành thành viên dataset tổng hợp.
- Không thêm trend nếu không có timestamp nguồn hợp lệ. Ngày import hoặc run không mặc nhiên là ngày phản hồi.

Token snapshot hiện tại chủ yếu xác định phiên bản dataset/run/nguồn nhãn, không thay thế filter identity. Query key/cache phải chứa các bộ lọc đã chuẩn hóa. Phân biệt **bộ lọc nền** của summary với **bộ lọc dẫn chứng** do click lát/topic; click không làm mẫu số biểu đồ tự đổi về 100%. Khi đổi bộ lọc nền hoặc nguồn nhãn, reset lựa chọn dẫn chứng/phân trang và lấy summary mới. Trường hợp scope đổi, không ghép counts cũ với items mới.

Phân tích từng câu trong đoạn có thể làm sau P0: tách câu có raw offsets, classifier chạy riêng mỗi câu; attribution theo câu được chọn để giới hạn chi phí. Không gắn nhãn cả đoạn lên mọi câu, không tự thêm nhãn Mixed. Không dùng mục này để trì hoãn hình 1.

## 10. P2: mạng từ có dữ liệu thật

Mục tiêu tối thiểu: node theo từ/cụm; cạnh đồng xuất hiện; nhóm màu có quy tắc; click mở phản hồi dẫn chứng. Không tái tạo tất cả chức năng LDA/centrality/ecology của công cụ trong ảnh.

- Tách từ tiếng Việt local, giữ cụm có nghĩa; stopword list có phiên bản, không loại phủ định máy móc.
- Quy tắc production đề xuất: cùng cửa sổ 5 từ trong một câu, không nối xuyên phản hồi; mỗi phản hồi chỉ cộng một lần cho một cạnh. Mockup hiện dùng đồng xuất hiện trong cùng phản hồi: nếu production dùng cửa sổ, đổi nhãn chú giải cho đúng.
- Node size theo số phản hồi có nhắc từ; edge weight theo số phản hồi hỗ trợ quan hệ.
- Nhóm màu: community detection deterministic như Louvain với seed/version cố định; hoặc phương án đơn giản được ghi rõ. Không copy communities hardcoded từ mockup.
- Tên nhóm lấy 2–3 từ đại diện, không LLM. Community khác nhãn topic classifier.
- Hạn chế khoảng 40–60 nodes, 100–150 edges khởi điểm; lọc có thông tin, không làm rối trang. Không có quan hệ đủ mạnh thì empty/ít dữ liệu.
- Tổng hợp trên dataset đầy đủ trong snapshot, không chỉ trang đầu `/items`.
- Node/edge/community có membership dẫn chứng và scope token; không thay bằng tìm chuỗi gần đúng mà trả bộ đếm khác.
- Xử lý NLP nặng trong worker, không chặn API; job/cache cho dataset lớn, tải khi mở phần network.
- Mobile giữ bộ chọn từ hoặc danh sách thay thế để không phải chạm node nhỏ. Có keyboard path.
- Betweenness, export GEXF, trend, nhiều layout graph là mở rộng, không bắt buộc cho lần này.

Contract P2 cần chốt trước khi code: tạo job từ dataset + normalized base filters + source label policy; GET kết quả gồm `scope_token`, `filter_signature`, `network_version`, params, nodes/edges/communities và counts. Endpoint dẫn chứng dùng network ID + selection type/ID + pagination; kiểm source scope và không tin client gửi membership. Community count là union item IDs, không cộng node counts trùng nhau. Tính cửa sổ trên token trước khi bỏ stopwords để tránh nối những từ vốn ở quá xa; đơn vị/cách ghép cụm phải nhất quán và có phiên bản. Mặc định mạng xét các phản hồi thuộc cùng population có nhãn sentiment hợp lệ của donut; ghi rõ `n dùng cho mạng / n trong scope`, không âm thầm đưa rows chưa có nhãn vào rồi đối chiếu với mẫu số khác.

## 11. Phân công subagent nếu môi trường Gemini hỗ trợ

Người dùng cho phép subagent khi tăng chất lượng. Không bắt buộc spawn để đạt số lượng; không giả vờ đã có reviewer nếu không có công cụ. Nếu môi trường chỉ hỗ trợ một agent, làm cùng các mốc tuần tự và tự review có ghi giới hạn.

Root Gemini chịu trách nhiệm scope, contract, tích hợp, kiểm model thật và nghiệm thu. Giữ tối đa 2–3 subagent cùng lúc để tránh tranh file/RAM. Không bắt buộc một model con cụ thể; dùng lựa chọn sẵn có phù hợp, không tự chuyển tác vụ sang chat người dùng khác.

### Đợt 1: khảo sát và M0

- Root: đọc dự án, chốt contract, thực hiện/điều phối spike model thật.
- Reviewer đọc-only: so yêu cầu Đạt với mockup, kiểm semantics điểm và nguồn dữ liệu.
- Có thể giao UI worker chuẩn bị component trên contract đã chốt, chỉ dùng fixture trong tests/preview. Chưa tuyên bố production xong.

### Đợt 2: triển khai P0

| Vai trò | Ownership | Không tự sửa |
|---|---|---|
| Root | `services/api/main.py`, `services/worker.py`, `services/storage/db.py`, migration, contracts chung `types.ts/api.ts`, tích hợp | Không ghi đè phần worker khác đang làm |
| Attribution worker | Module attribution mới, mapping/coalition trong `services/inference`, unit/model tests liên quan | API/storage/frontend ngoài phạm vi |
| UI worker | `SentenceDemo.tsx/.css`, component/hook riêng, E2E UI được phân công | Inference/storage và contract chung chưa trao quyền |
| Reviewer luân phiên sau khi slot trống | Đọc diff, chạy test nhẹ, kiểm phép cộng/stale/identity/ảnh | Không tự sửa file của owner; trả findings có vị trí |

Root là người duy nhất chạy model benchmark nặng và build/dist tại một thời điểm. Worker inference có thể viết test nhưng gửi root lệnh chạy khi tài nguyên đang bận. Shared tests như `tests/support.py`, E2E fixtures và test server do root quản hoặc chuyển ownership rõ ràng.

### Đợt 3: P1/P2 và review

- Sau P0 đạt, tái sử dụng worker cho analytics/network ở file mới và UI trực quan hóa.
- Root vẫn giữ shared API/storage/types. Worker đề xuất patch interface để root áp dụng.
- Một reviewer độc lập kiểm lại R01–R09, regression và bằng chứng model thật; root sửa findings và chạy lại tests liên quan.

Mẫu lệnh giao việc:

> Bạn phụ trách [file/module], mục tiêu [đầu ra], theo contract [file]. Bạn không làm việc một mình; không revert thay đổi của người khác, không sửa file ngoài ownership khi chưa phối hợp. Fixtures chỉ ở tests/preview. Hoàn tất bằng danh sách file sửa, kiểm thử đã chạy/chưa chạy, lỗi/giới hạn và yêu cầu tích hợp. Không tự push, không chạm live runtime hoặc model weights.

## 12. Các mốc triển khai và nghiệm thu

| Mốc | Đầu ra | Gate |
|---|---|---|
| M0 | Báo cáo feasibility thật + contract | Mapping/parity/additivity đúng, chi phí đã đo |
| M1 | Attribution engine, lifecycle, migration | API/worker tests; không làm sai run nguồn |
| M2 | UI theo mockup, bỏ LLM/copy/layers | Highlight ↔ bảng, score thật, async/stale đúng |
| M3 | P0 acceptance trên model thật | R01–R07 có bằng chứng; screenshots desktop/mobile |
| M4 | Donut + topic + evidence | R08, count và scope khớp |
| M5 | Network | R09, edges/membership thật, responsive |
| M6 | Review/fix, build/regression, bàn giao | Không còn lỗi nghiêm trọng; báo phần nào còn giới hạn |

Không cần hỏi lại giữa các mốc đã được cho phép. Nếu phát hiện cần thay đổi semantics trọng số hoặc thiếu checkpoint/model runtime, báo cụ thể và tiếp tục phần độc lập; không giả kết quả hoặc tuyên bố hoàn tất.

## 13. Kiểm thử có ý nghĩa

### Engine

- Unit game nhỏ có tương tác: Shapley cộng đúng, delta che đơn lẻ không bị nhầm thành tổng.
- G=1, toàn đóng góp zero, cả hai dấu, nhiều occurrence, nhóm ẩn cộng đúng.
- NFC/NFD, emoji/surrogate, dấu câu, phủ định, tách từ có underscore, truncated input.
- Leading/trailing whitespace, CRLF, snapshot sau trim hiện hành, người dùng sửa textarea sau submit; token cuối bị cắt giữa từ, token cố định và nhóm chồng lấp; G=0 không giả completed.
- Full input IDs/scores giống prediction nguồn. Không ép từ “thân thiện” luôn có điểm dương trong tests model thật.
- Không finite/không khớp schema/model → lỗi rõ; không sửa hoặc fabricate output.

### Lifecycle

- POST trùng, nhiều tab/handle độc lập, cache đúng identity, source expiry, edit/review/run/model change.
- Cache hit sau source edit/delete/expiry, mutation xảy ra giữa precheck và publish, cùng key khác body, hai handle khác nhau của cùng nguồn và cancel chỉ một handle; lease resume không đếm trùng coalition.
- Clear/đổi profile khi request tạo job chưa trả: nhận ID muộn phải cancel/vô hiệu hóa.
- Attribution lỗi không làm mất prediction; hủy không công bố tổng giả.
- Worker lease/restart/recovery; request nhanh không bị chặn toàn thời gian attribution.
- Migration từ DB cũ, backup/restore, không lẫn attribution vào dataset/count/export.

### UI và dữ liệu

- Không còn câu/nút/lớp bị yêu cầu bỏ; 10 topic vẫn xem được.
- Không có outbound explanation call hoặc yêu cầu API key.
- Bảng giữ đúng header/bốn cột/màu/italic/thanh nhỏ/tổng/method disclosure.
- Bàn phím, touch, contrast, reduced motion, 390/768/1440 px; 320 và 1920 nếu có.
- Donut đủ bốn nhãn, missing labels, all-toxic, empty dataset, effective-vs-ai.
- Click chart/topic/network trả đúng tổng và item IDs, qua nhiều trang; stale scope có refresh.
- Network không bịa cạnh/community; dữ liệu quá ít hiển thị trung thực.
- Review label change làm đổi effective dataset summary, nhưng attribution vẫn giải thích prediction AI nguồn, không lấy nhãn người duyệt làm target ngầm. Test filter identity và summary/drill-down tách biệt; community membership dùng union, không chỉ trang đầu.

### Build và tests dự kiến

Từ repo root; kiểm runtime/dependency trước. Không cài lại môi trường nếu đã đủ.

```powershell
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest tests/test_sensitivity_selection.py tests/test_runtime_isolation.py tests/api/test_demo_scope.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Thêm và chạy tests mới đúng phần sửa trước full suite. Cập nhật tests cũ đang bắt sample buttons, lớp, provider LLM, database version; không xóa bảo vệ nguồn dữ liệu chỉ để tests xanh.

`pytest.ini` mặc định loại marker `real_model`. Phải chạy opt-in riêng với test file mới hoặc test cũ đã cập nhật:

```powershell
$env:FEEDBACK_REAL_BUNDLE_TEMPLATE = 'F:\DPL_NEU-ESC\runtime\models'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
# Chọn executable đã kiểm chứng có torch/transformers/underthesea và pytest.
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_attribution_real_model.py -q
```

Tên test mới trên là đích dự kiến, chưa tồn tại tại thời điểm bàn giao. Nếu model dependencies ở `.venv-modelcheck`, dùng interpreter tương ứng sau khi kiểm tra. Không gọi test bị skip là pass model thật. Không tải model từ mạng, không train lại.

Runtime thử nghiệm dùng thư mục riêng trong temp hoặc `test-results` có ID phiên chạy; không dùng live `runtime/workspace.sqlite3`. Test model copy bundle qua helper đã có, kiểm hash, không sửa `current.json`/weights nguồn. Log không lộ credentials hoặc raw data ngoài phạm vi cần thiết. Không dừng process không do phiên triển khai sở hữu.

## 14. Bằng chứng và sản phẩm bàn giao

Tạo các tài liệu sau khi thực thi, không tạo kết quả kiểm thử giả từ trước:

- `docs/ATTRIBUTION_FEASIBILITY_2026-11-12.md`: cấu hình, parity/mapping/additivity, thời gian/memory, lựa chọn method và giới hạn.
- `docs/WEBAPP_ATTRIBUTION_CONTRACT.md`: contract đã triển khai, semantics score, version, cache/lifecycle.
- `docs/GEMINI_WEBAPP_IMPLEMENTATION_REPORT_2026-11-12.md`: R01–R09 PASS/PARTIAL/BLOCKED, files, tests, model thật hay double, screenshots, URL chạy, known limits.
- Screenshot UI thật desktop/mobile, state mixed/neutral/toxic/error/loading và dataset graph khi đã làm.
- Cập nhật `PRODUCT.md`, `DESIGN.md`, `docs/LOCAL_APP.md` và tài liệu contract/vận hành có liên quan; không đổi báo cáo nghiên cứu/benchmark.

Final response cho người dùng cần nói rõ phần bắt buộc hình 1–2 đạt chưa, số liệu lấy từ đâu, P1/P2 trạng thái gì, tests thật đã chạy, mở app ở đâu. Không chỉ liệt kê số file sửa hoặc “all tests passed” mà thiếu bằng chứng model thật.

Đối chiếu ảnh UI thật với `reference-table-desktop.png` và `analysis-mobile.png`; kiểm hierarchy/bốn cột/header/màu/thanh đo/tổng/cách tính. Không đánh giá bằng pixel equality vì nội dung và trọng số thật khác fixtures. Lưu ít nhất một luồng đầu cuối thật: nhập câu chưa có trong mockup → prediction → attribution completed → chọn highlight/dòng → mở cách tính và kiểm tổng. Có ít nhất một phản hồi vừa khen vừa chê, nhưng không ép model sinh hai dấu cho đúng câu chuyện. Nếu model đưa trọng số khó hiểu, báo như limitation thay vì sửa số. Report mỗi dòng R01–R09 phải có bằng chứng tương ứng, không chỉ nhãn PASS.

## 15. Những việc không thuộc phạm vi

Không retrain, thay checkpoint, thay dataset schema nhãn, thêm LLM dưới tên khác, thêm chatbot, ABSA, nhãn Mixed, chủ đề giả mới, rewrite framework, thiết kế landing page mới, full graph platform, trend không có timestamp, tự động kết luận hành động quản lý từ một câu. Không commit/push/deploy nếu chưa được yêu cầu.

**Tiêu chuẩn cuối cùng:** một người nhìn vào câu sẽ thấy rõ từ/cụm nào được xét, trọng số tương ứng, và tổng cộng ra sao, theo bố cục gần ảnh Đạt gửi; phần dự đoán vẫn đúng nguồn, các phần tổng hợp chỉ hiện dữ liệu thật.
