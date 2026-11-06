# Bản hiểu dự án NEU-ESC

Ngày đọc: 2026-11-05; hoàn tất tổng hợp 2026-11-06. Checkout gốc: `c539171`. Phạm vi: toàn bộ file làm việc hiện hữu của repo, không bao gồm lịch sử Git, tài liệu được nhắc tới nhưng không có trên disk, hoặc artifact ở Kaggle/Drive bên ngoài.

Ba subagent GPT-6.1 Sol đọc độc lập ba phần: baseline và code tác giả; improvement và kết quả ED/UIT/bias; dữ liệu, notebook tương quan/oracle và audit paper. Agent chính tổng hợp và chuyển yêu cầu thành kế hoạch sản phẩm. Đây là đọc/audit tĩnh, không chạy lại các thí nghiệm huấn luyện.

## 1. Dự án đang làm gì?

Với một đoạn tiếng Việt, model dự đoán đồng thời:

- **Cảm xúc**: nội dung mang sắc thái nào?
- **Chủ đề**: nội dung đang nói về việc gì?

Group 5, DPL302m tái lập các cấu hình của paper NEU-ESC theo code công khai, dùng hai backbone PhoBERT-base-v2 và ViSoBERT. Nhóm bổ sung ED, tức dùng ensemble giáo viên tạo phân phối nhãn mềm cho một student học theo, rồi kiểm tra thêm trên UIT-VSFC.

Đây là bài toán phân loại văn bản, chưa phải chatbot, tóm tắt sinh văn bản, trích nguyên nhân phàn nàn, phát hiện ý định hay phân tích nhiều khía cạnh trong một câu. Mỗi task hiện trả đúng một nhãn cho mỗi đầu vào. Một câu vừa khen giảng viên vừa chê cơ sở vật chất vẫn bị ép về một chủ đề chính.

## 2. Bản đồ kho mã

| Khu vực | Vai trò | Dùng cho web như thế nào? |
|---|---|---|
| `src_baseline/neu_esc_kaggle.py` | Fetch, tokenize, train, chọn epoch, predict, xuất kết quả baseline | Tham chiếu kiến trúc và preprocessing; không gọi CLI train trong web |
| `src_baseline/run_queue.py` | Xếp các run lên GPU | Chỉ phục vụ training ngoài app |
| `src_baseline/check_runs.py` | Kiểm hoàn tất, loss, protocol, IDs và version | Nguồn điều kiện hợp lệ của artifact nghiên cứu |
| `src_baseline/aggregate.py`, `analyze_gap.py` | Tổng hợp và audit chênh lệch paper | Tab báo cáo ngắn |
| `src_baseline/check_author_smart.py` | Đối chiếu hành vi SMART tác giả | Evidence, không là chức năng người dùng |
| Hai notebook trong `src_baseline/` | Smoke timing và chạy seed trên Kaggle | Hướng dẫn lịch sử, cần sửa drift nếu dùng lại |
| `src_improvement/neu_esc_improvement.py` | Hai dataset, ED, OOF teachers, train/predict | Nền tảng model student cho app |
| `src_improvement/run_queue.py`, `check_runs.py`, `aggregate_improvement.py` | Điều phối, kiểm và tổng hợp improvement | Training/evidence |
| `src_improvement/logit_bias.py` | Fit bias trên validation logits | Thí nghiệm phụ; không bật mặc định trong công cụ |
| `data/` | 9 CSV raw/processed và mô tả nhãn | Hiểu schema, test local, thống kê dữ liệu |
| `reports/` | CSV/MD/JSON số liệu, audit và bản nháp paper | Nguồn báo cáo, không thay thế weights |
| `reports/baseline_reproduce/author_code/` | Bản chụp code tác giả và hash | Audit; không phải package production đang chạy |
| Notebook gốc | Tương quan và oracle TF-IDF/LR | Nghiên cứu thăm dò, không phải model deploy |

Hiện không có frontend, backend API, schema database, requirements/pyproject khóa dependency, checkpoint đã fine-tune, thư mục `runs/`, OOF teachers hoặc logits cấp câu trong checkout này.

## 3. Dữ liệu và nhãn thực tế

### NEU-ESC: thảo luận sinh viên

| Train | Validation | Test | Tổng |
|---:|---:|---:|---:|
| 23.048 | 3.305 | 6.613 | 32.966 |

| Sentiment ID | Tên gốc | Tên gợi ý trên app |
|---:|---|---|
| 0 | Neutral | Trung tính |
| 1 | Positive | Tích cực |
| 2 | Negative | Tiêu cực |
| 3 | Toxic | Ngôn từ độc hại |

| Topic ID | Tên gốc | Tên gợi ý trên app |
|---:|---|---|
| 0 | Spam | Rác / quảng cáo |
| 1 | News | Tin tức |
| 2 | Academic | Học tập |
| 3 | Other | Khác |
| 4 | Service | Dịch vụ |
| 5 | Jobs & Recruitment | Việc làm / tuyển dụng |
| 6 | Personal Affairs | Chuyện cá nhân |
| 7 | Social Affairs | Vấn đề xã hội |
| 8 | Help & Share | Hỏi đáp / chia sẻ |
| 9 | Club & Events | Câu lạc bộ / sự kiện |

Tổng nhãn cảm xúc theo CSV: `[22773, 4148, 5200, 845]`. README/paper ghi Negative 5.250 nhưng CSV thực là 5.200; dashboard phải tính theo dữ liệu thật. Neutral khoảng 69%, nên Accuracy không phản ánh đầy đủ chất lượng lớp hiếm.

### UIT-VSFC: đánh giá đào tạo

| Train | Validation | Test | Tổng |
|---:|---:|---:|---:|
| 11.426 | 1.583 | 3.166 | 16.175 |

Sentiment: `0 negative`, `1 neutral`, `2 positive`.

Topic: `0 lecturer`, `1 training_program`, `2 facility`, `3 others`.

Tên trên app lần lượt: Giảng viên, Chương trình đào tạo, Cơ sở vật chất, Khác. Không có lớp Toxic. Cùng ID không đồng nghĩa cùng nhãn với NEU. UIT được train/evaluate riêng; kết quả của nó không chứng minh checkpoint NEU tự tổng quát hóa zero-shot.

### Schema và giới hạn chung

- Tất cả CSV có đúng ba cột `text,sentiment,classification`, UTF-8 không BOM; audit không thấy missing/blank.
- Không có timestamp, người viết, giảng viên cụ thể, mã môn, lớp hay khoa. Không thể tạo biểu đồ xu hướng thời gian hay xếp hạng giảng viên từ ba cột này.
- NEU có 3 raw CSV; processed dùng trong training không hiện diện. UIT có 3 raw và 3 processed, giữ thứ tự và nhãn.
- Không phát hiện trùng văn bản chính xác giữa split. UIT train có một extra duplicate text; điều này không là kiểm định đầy đủ mọi loại leakage.
- Regex sơ bộ không phát hiện một số dạng email/URL/số điện thoại trong dữ liệu; chưa phải audit PII hoàn chỉnh.

Nguồn nhãn: `data/NEU/README.md:26`, `data/UIT-VSFC/README.md:20`. Nguồn lệch count: `reports/baseline_reproduce/data_source/paper_data_comparison.json:17`.

## 4. Model hoạt động như thế nào?

### Baseline

Hai backbone khóa revision: `vinai/phobert-base-v2`, `uitnlp/visobert`.

ST là hai model riêng nếu cần cả sentiment và topic. MTL dùng chung encoder; vector token đầu đi qua Linear → SiLU → LayerNorm rồi tách thành hai đầu phân loại. NEU có kích thước đầu ra 4/10, UIT 3/4.

Tokenization dùng `use_fast=False`, tối đa 128 token và padding theo batch. ViSoBERT đọc raw text. PhoBERT đọc processed text đã tách từ. UIT dùng underthesea 9.5.0; preprocessing NEU tác giả chưa được tái tạo đầy đủ.

MTL học bằng CE có trọng số 0,5 cho mỗi task. MLM và SMART là kỹ thuật huấn luyện bổ sung; không phải tính năng bật/tắt có thể làm model đã train thay đổi tức thời lúc suy luận.

SMART ở repo cố ý theo code tác giả: noise vào token ID rồi ép `.long()`, làm mất gradient noise. Không được diễn giải đây là implementation SMART chuẩn perturb embedding. Repo có nhánh thử embedding riêng để phân tích.

### Ensemble Distillation

Giáo viên OOF: 2 backbone × 3 seed × 5 fold = 30 model cho một dataset. Mỗi dòng train nhận 6 dự đoán từ các model không học fold chứa dòng đó. Teacher distribution là trung bình xác suất softmax, không phải trung bình logits.

Student là model MTL, học CE nhãn thật cộng KL từ teacher, gamma mặc định 1. Khi chạy app chỉ cần student đã fine-tune; không cần tải 30 teacher.

Best epoch chọn bằng trung bình validation macro-F1 hai task. Không chọn seed/checkpoint theo test. Một checkpoint chạy app và thống kê benchmark nhiều seed là hai loại bằng chứng khác nhau.

Nguồn: `src_improvement/neu_esc_improvement.py:277`, `src_improvement/neu_esc_improvement.py:636`, `src_improvement/neu_esc_improvement.py:749`.

## 5. Vì sao chưa thể nhập câu mới ngay?

Hai runner chỉ giữ `best_state` trong RAM. Sau train, chúng ghi `config.json`, `epochs.jsonl`, `metrics.json`, `predictions.csv`, `logits.npz` và các output OOF tùy tác vụ, nhưng không ghi weights fine-tune ra disk. Ngay cả các output từng run đó cũng không có trong checkout hiện tại, chỉ còn báo cáo tổng hợp.

- `src_baseline/neu_esc_kaggle.py:596`: giữ best state trong RAM.
- `src_improvement/neu_esc_improvement.py:25`: ghi rõ không lưu checkpoint.
- `src_improvement/neu_esc_improvement.py:683`: best state và load lại để evaluate.

Tải pretrained backbone từ Hugging Face không khôi phục student đã học của nhóm. Bảng accuracy và logits của những câu cũ cũng không dự đoán được một câu mới.

Trước live inference phải tìm lại artifact có thật ở nơi nhóm lưu; nếu không có, thêm export rồi train lại. Có thể dùng OOF teacher probabilities đã lưu để tiết kiệm nếu thu hồi được và kiểm tra đủ provenance. Nếu không có teacher artifact, ED cần dựng lại OOF, không chỉ train một student trực tiếp từ raw CSV.

## 6. Kết quả đã được kiểm chứng ở mức báo cáo

Đơn vị tất cả ô bên dưới là %, mean ± sample std trên test, chọn epoch bằng validation.

| Dataset / model | Số seed | Sentiment accuracy | Sentiment macro-F1 | Topic accuracy | Topic macro-F1 |
|---|---:|---:|---:|---:|---:|
| NEU PhoBERT ED | 15 | 83,51 ± 0,24 | 77,91 ± 0,28 | 79,65 ± 0,27 | 63,57 ± 0,40 |
| NEU ViSoBERT ED | 15 | 83,25 ± 0,18 | 77,22 ± 0,28 | 79,73 ± 0,17 | 63,05 ± 0,26 |
| UIT PhoBERT ED | 10 | 93,88 ± 0,12 | 82,02 ± 0,51 | 89,71 ± 0,11 | 80,70 ± 0,58 |
| UIT ViSoBERT ED | 10 | 93,08 ± 0,10 | 80,34 ± 0,49 | 89,32 ± 0,16 | 80,42 ± 0,34 |

NEU seed 42–56; UIT seed 42–51. Nguồn: `reports/improvement/summary.md`, `reports/improvement/README.md`, `reports/uit_vsfc/summary.md`, `reports/uit_vsfc/README.md`.

Các kết luận dùng được:

- ED cải thiện các metric tổng thể trên NEU theo các bảng so sánh trong repo.
- Lợi ích ở UIT rõ hơn cho topic. Không nói ED thắng mọi metric: PhoBERT ED sentiment macro-F1 thấp hơn MLM 0,57 điểm phần trăm, p=0,022; sentiment accuracy gần tương đương.
- ED không mạnh nhất về Toxic. Không biến lớp Toxic thành công cụ tự động kết luận/kỷ luật người viết.
- Trọng số/giáo viên nằm trong giai đoạn huấn luyện; chi phí ít model hơn lúc suy luận chưa tương đương một phép đo latency.
- p in `0.000` là làm tròn; UI phải thể hiện `<0.001`, không `p=0`.
- Các bảng dùng Welch test hoặc paired test theo mục đích; chưa hiệu chỉnh đa so sánh. Không thêm tuyên bố chắc chắn vượt ngoài báo cáo.

## 7. Logit bias và thí nghiệm oracle

`logit_bias.py` chọn bias trên validation macro-F1 rồi áp dụng `argmax(z+b)`. Rare target là Toxic NEU và Neutral UIT, mã nhãn khác nhau. Bias là riêng cho từng run; không lấy bias trung bình của bảng áp lên checkpoint bất kỳ. Bias chưa là probability calibration. Đề xuất để ngoài luồng công cụ v1.

Notebook oracle có 19 cell, dùng TF-IDF 5.000 features + Logistic Regression, seed 42; thêm ground-truth nhãn task kia làm input. Sentiment macro-F1 tăng 65,45 → 65,72; topic 54,09 → 54,34. Đây là thí nghiệm thông tin đặc quyền cho model tuyến tính cụ thể, không là upper bound toán học của Transformer và không thể deploy khi không biết nhãn thật.

Cramér's V khoảng 0,1773, NMI 0,0339. Có tương quan thống kê không chứng minh MTL phải tốt hơn, cũng không chứng minh các cặp nhãn chưa quan sát là bất khả thi.

Claim Personal Affairs +2,07 trong kết luận notebook không có code/output breakdown topic tương ứng; không đưa vào báo cáo app.

## 8. Các bẫy dữ liệu và tài liệu cần nhớ

| Vấn đề | Ảnh hưởng đến triển khai |
|---|---|
| NEU CSV git dùng CRLF, pinned hash dùng LF | Fetch artifact đúng nguồn để train; không sửa bừa hash hoặc coi checkout raw là đã qua kiểm checksum |
| NEU processed có 223/26/68 dòng khác raw ngoài dấu tách từ | Không khẳng định thay segmenter là parity tuyệt đối với training tác giả |
| Quyền tái phân phối NEU chưa nhất quán giữa metadata và ledger | Local dùng dữ liệu sẵn; public không tự đẩy toàn văn dataset lên web |
| README gốc nói UIT chưa commit nhưng `git ls-files` có UIT | Trạng thái Git thực tế ưu tiên hơn lời mô tả cũ |
| `smoke_timing.ipynb` EPOCHS thiếu MLM trong khi queue mặc định có MLM | Sửa trước khi tái dùng notebook tính thời gian |
| `run_seeds.ipynb` còn chọn 4 setup cũ | Không coi notebook này tự chạy đủ 12 setup mỗi seed |
| Notebook oracle dùng `Dataset/NEU` | Sửa path khi chạy lại; output hiện có là evidence lịch sử |
| Một số link `docs/FINDINGS.md`, `docs/papers/...`, `reports/source/...` không tồn tại | Không đưa link chết vào app |
| Runner version khác nhau và bản NEU ED gốc không nằm trong git | Lưu provenance artifact mới; không hứa bitwise parity với mọi run lịch sử |
| Figure 3 paper có diagonal accuracy 54,73% / 31,36%, không khớp Table 6 | Không dùng các ảnh/CSV đó làm confusion matrix của model nhóm |
| Weighted-F1 tác giả có biến thể đảo y_true/y_pred | App dùng metric chuẩn, không trộn hai cột |

Nguồn Figure 3: `reports/baseline_reproduce/paper/figure3_audit.md`. Quyền dữ liệu và nguồn: `reports/baseline_reproduce/data_source/source_ledger.json`, `data/.gitignore`.

Các CSV aggregate chứa task rows, không phải mỗi dòng là một model/run. Baseline per_run có 300 task rows/180 run; improvement có 360 task rows/210 run khi gộp cả baseline; UIT có 200 task rows/100 run; bias có 1.400 task×variant rows. Không cộng chồng baseline với improvement hoặc lấy số dòng làm KPI số model. Audit `gap_runs` có cohort/path trùng nên không suy tổng run duy nhất chỉ từ số chuỗi path.

## 9. Quyết định sản phẩm đã nhận từ người dùng

1. Công cụ làm việc là trọng tâm; không cần xây website thuyết trình vì đã có slide.
2. Có thể có một tab báo cáo ngắn, mức ưu tiên thấp.
3. Chạy trên máy cá nhân trước, có đường lên web sau.
4. Người dùng giao việc lựa chọn JS/Python theo sự phù hợp.

Đề xuất chuyển các sự thật này thành workspace cho nhiều phản hồi, có vòng rà soát và xuất kết quả. Chi tiết trong `WEB_APP_DEMO_PLAN.md`.

## 10. Coverage và việc chưa thực hiện

Đã đọc toàn bộ source Python và README ở baseline/improvement; toàn bộ cell của ba notebook; bản chụp code tác giả; tất cả Markdown/JSON/CSV trong reports; chín CSV dữ liệu được kiểm kê toàn bộ dòng bằng chương trình; hai ảnh paper được xem trực tiếp; root Git/config và trạng thái tracked files được kiểm tra. File nhị phân notebook plot được hiểu qua code/output liên quan, không coi mỗi ảnh nhúng là một lần tái tính thống kê độc lập.

Chưa train lại, chưa tải backbone/weights, chưa benchmark inference, chưa xác minh artifact ngoài repo, chưa triển khai app. Những phần đó là công việc trong kế hoạch tiếp theo, không phải kết quả đã hoàn thành.
