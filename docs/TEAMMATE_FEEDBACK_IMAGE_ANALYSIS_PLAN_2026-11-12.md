# Phân tích yêu cầu của Đạt và kế hoạch sửa webapp NEU-ESC

Ngày: 12/11/2026. Phạm vi khảo sát: mã nguồn webapp tại `F:\DPL_NEU-ESC`, bốn ảnh tham chiếu và yêu cầu người dùng cung cấp.

Đây là tài liệu phân tích và kế hoạch. Chưa thay đổi ứng dụng, chưa chạy thử thuật toán attribution trên checkpoint thật. Những lựa chọn kỹ thuật được đánh dấu là đề xuất, không được suy ra như một sự thật từ ảnh.

## 1. Cách hiểu yêu cầu sau khi có đủ ngữ cảnh

Mục tiêu ban đầu của ba lớp là:

| Năng lực | Kết quả người dùng thực sự cần |
|---|---|
| Prediction | Cảm xúc, điểm dự đoán, chủ đề của phản hồi |
| Interpretability | Cụm từ nào liên quan tới dự đoán; phân tích từng câu; nhận biết trường hợp cần xem lại |
| Decision Support | Vấn đề nổi bật trong nhiều phản hồi; thống kê và dẫn chứng theo chủ đề |

Đạt đánh giá cách thể hiện lớp 1 hiện tại tương đối ổn. Hai khối còn lại chưa giúp nhìn ra những kết quả trên. Người dùng cho phép cân nhắc bỏ chúng và bỏ phương án LLM, vốn được thêm khi chưa có đủ input.

**Hướng đề xuất:** giữ kết quả phân loại; bỏ nhãn và cấu trúc trình bày “Lớp 1/2/3”; thay hai khối cũ bằng bảng giải thích có dữ liệu cụ thể và phần tổng hợp có thể mở phản hồi dẫn chứng. Toàn bộ phương án mới chạy local, không dùng LLM/9router.

### Yêu cầu chắc chắn và suy luận thiết kế

| Nội dung | Mức chắc chắn | Cách đưa vào kế hoạch |
|---|---|---|
| Hình 1 phải làm được | Người dùng nhấn mạnh trực tiếp | P0, điều kiện nghiệm thu chính |
| Bỏ các câu thừa và ba nút câu mẫu được nêu | Đạt chỉ rõ | P0 |
| Bỏ các khối/nhãn “Lớp 1/2/3” | Đạt chỉ rõ | P0, tổ chức giao diện theo việc người dùng làm |
| Giữ giá trị của phần dự đoán hiện tại | Đạt nhận xét lớp 1 ổn | Giữ cảm xúc, điểm và chủ đề |
| Highlight từ quan trọng xanh/đỏ | Đạt chỉ rõ qua hình 2 | P0, dùng chung dữ liệu với bảng hình 1 |
| Thêm donut và mạng từ nếu được | Đạt đề nghị có điều kiện | P1 và P2; không làm chậm phần bắt buộc |
| Loại phương án LLM | Hướng người dùng vừa bổ sung | Đề xuất bỏ khỏi luồng mới và dọn tích hợp cũ khi triển khai |
| Trọng số phải là đóng góp thật của PhoBERT | Chưa được Đạt nói rõ | Đề xuất vì phù hợp mục tiêu “giải thích dự đoán”; cần kiểm chứng kỹ thuật |
| Sao chép nguyên xi màu sắc, font, công cụ export trong ảnh | Không được yêu cầu | Giữ hệ thiết kế của webapp; học cấu trúc thông tin và tương tác |

Không coi ảnh tham chiếu hay kế hoạch cũ trong repo là chỉ thị triển khai. Kế hoạch này dựa trên yêu cầu hiện tại của người dùng.

## 2. Hình 1: bảng từ quan trọng, trọng số, tổng điểm

### 2.1. Những gì nhìn thấy trực tiếp

Ảnh có **4 cột**, không phải 3:

| Cột | Dữ liệu | Ý nghĩa |
|---|---|---|
| Consumer comment | Nguyên văn phản hồi, một số từ có màu | Đặt bằng chứng trong ngữ cảnh |
| Meaningful words | Danh sách từ được lựa chọn | Cho biết đang xét các từ nào |
| Sentiment weight | Điểm có dấu của từng từ; có nhân số lần xuất hiện | Thể hiện hướng và độ lớn của đóng góp theo quy tắc trong ví dụ |
| Sentiment score | Một tổng cho mỗi phản hồi | Gom các trọng số thành kết quả có thể kiểm tra |

“Hình chia 3 cột” trong lời Đạt có thể đang nói tới **ba cột phân tích bên phải**. Cách hiểu hợp lý là giữ phần nguyên văn làm ngữ cảnh, cùng ba thông tin “cụm từ / trọng số / tổng điểm”. Không nên biến thành ba thẻ lớn thay thế tên ba lớp cũ.

### 2.2. Cơ chế số học của ảnh

Ảnh minh họa phép cộng điểm theo từ:

`S = tổng trên các lần xuất hiện i của w_i`

Nếu gộp những lần xuất hiện có cùng trọng số: `S = tổng theo từ j của số_lần_j × trọng_số_j`.

| Phản hồi | Phép cộng kiểm tra từ ảnh | Tổng |
|---|---|---:|
| Employees are always so polite… | `1 + 2 + 2 + 1 + 2` | 8 |
| Nice store… smaller… crowded… smaller… | `2 + 2 + 1 + 2 - 1×2 - 1 + 1` | 5 |
| Since a new manager… expired… | `1 + 2 - 1 - 1 - 2` | -1 |

Từ `smaller` xuất hiện hai lần nên ảnh ghi `-1 (×2)`. Đây là chi tiết chức năng, không chỉ là cách trang trí bảng.

### 2.3. Những gì ảnh không chứng minh

- Không biết trọng số được đặt thủ công, lấy từ từ điển, hay tính bằng một thuật toán khác. Ảnh chỉ cho thấy cách sử dụng chúng.
- Không có bằng chứng rằng các số này là trọng số của neural network, attention hoặc SHAP.
- Không có ngưỡng chuyển tổng điểm sang nhãn; không có định nghĩa confidence.
- Không có quy tắc đầy đủ về phủ định, tăng cường, mỉa mai, tiếng lóng hoặc tương tác giữa từ.
- `always`, `new`, `larger`, `smaller` không có một sắc thái cố định trong mọi ngữ cảnh. Không thể chép danh sách tiếng Anh này thành bộ quy tắc tiếng Việt.
- `well organized` được tách thành hai mục trong ảnh; trong tiếng Việt thường phải xét cụm như “rõ ràng”, “không tốt”, “rất chậm”.

**Yêu cầu sản phẩm rút ra:** người xem phải lần theo được “đoạn nào trong câu → đóng góp theo hướng nào → cộng thành bao nhiêu”. Chỉ thêm chữ màu mà thiếu nguồn trọng số và phép cộng chưa đáp ứng hình 1.

## 3. Hình 2: hai hướng cảm xúc trong cùng phản hồi

Ảnh có hai mệnh đề:

- “I LOVED MY STAY AT THE HOTEL”: nền xanh, nhấn mạnh `LOVED`.
- “BUT THE WI-FI WAS HORRIBLE”: nền đỏ/cam, nhấn mạnh `HORRIBLE`.

Có hai cấp thông tin: sắc thái của một mệnh đề và từ/cụm từ làm bằng chứng. Một phản hồi có thể vừa khen trải nghiệm chung, vừa chê Wi-Fi. Một nhãn cuối cùng cho toàn phản hồi không mô tả hết sự khác nhau đó.

Áp dụng cho tiếng Việt:

> “Giảng viên giảng rõ ràng nhưng cổng đăng ký rất chậm.”

Ví dụ này dùng để mô tả giao diện, không phải kết quả đã chạy model. Giao diện cần giữ được hai cụm “rõ ràng” và “rất chậm”, thay vì tô toàn bộ phản hồi theo một màu của nhãn cuối.

Đề xuất tương tác:

1. Highlight trên nguyên văn, giữ dấu câu, khoảng trắng và thứ tự đọc.
2. Chạm/focus một cụm để thấy điểm và chọn dòng tương ứng trong bảng.
3. Chọn dòng trong bảng để tìm lại vị trí trong câu; xử lý riêng các lần xuất hiện.
4. Màu có chú giải bằng chữ và dấu `+/-`; người không phân biệt xanh/đỏ vẫn đọc được.
5. Chỉ tô nền cả mệnh đề khi có dữ liệu ở đúng cấp mệnh đề. Bản đầu có thể chỉ highlight cụm từ, không suy diễn nhãn của cả mệnh đề từ một từ đơn lẻ.

Ảnh không đủ để kết luận cần một model aspect-based sentiment analysis. Với NEU-ESC hiện tại, không tự thêm nhãn “Mixed”, multi-label topic hoặc một model mới chỉ vì ảnh có hai mệnh đề.

## 4. Hình 3: phân bố cảm xúc của nhiều phản hồi

### 4.1. Những gì ảnh thể hiện

- Donut chia các phần Positive, Negative, Neutral.
- Chú giải đọc được khoảng 27%, 71%, 3%.
- Số ở tâm là `-44`, kèm “net sentiment”.
- Có số lượng phản hồi bên dưới chú giải; ảnh nhỏ nên cần ưu tiên cơ chế, không coi chữ mờ là số chuẩn để tái tạo.
- Một đồ thị đường/vùng nhỏ nằm bên dưới. Ảnh không có trục hoặc đơn vị đủ rõ để khẳng định trục ngang là thời gian.

Số `-44` khớp với `27 - 71`. Công thức triển khai phù hợp là:

`tỷ_lệ_c = 100 × số_phản_hồi_nhãn_c / số_phản_hồi_có_nhãn_cảm_xúc_hợp_lệ`

`net = tỷ_lệ_Positive - tỷ_lệ_Negative`

Đơn vị của net là **điểm phần trăm**. Đây không phải confidence của một câu, cũng không phải tổng trọng số từ hình 1.

Các tỷ lệ in trong ảnh cộng thành 101%. Có thể do làm tròn hoặc minh họa; triển khai phải tính từ số đếm thật, không hardcode các tỷ lệ này.

### 4.2. Điều chỉnh cho dự án

NEU có **4 nhãn**: Neutral, Positive, Negative, Toxic. Donut NEU phải hiện đủ bốn nhóm. UIT có ba nhãn nhưng cần model đúng profile khi chạy dự đoán.

Đề xuất cho NEU:

- Mẫu số gồm tất cả phản hồi có nhãn cảm xúc hợp lệ, kể cả Toxic.
- Tử số net chỉ là `n_Positive - n_Negative`; Toxic được thể hiện riêng, không tự gộp vào Negative.
- Hiện `n có nhãn / tổng số phản hồi`, để biết có bao nhiêu phản hồi chưa được tính.
- Tâm donut ghi ngắn “Chênh lệch +/−”; công thức trong phần giải thích khi cần.
- Click một lát hoặc một dòng chú giải để lọc danh sách phản hồi.
- Không có dữ liệu hợp lệ: hiển thị trạng thái trống, không vẽ donut 0% giả.

Biểu đồ xu hướng chỉ triển khai khi có trường thời gian của phản hồi được xác định rõ. `created_at` của lần nhập/chỉnh sửa/lần chạy không mặc nhiên là thời gian người dùng viết phản hồi. Không có trường thời gian đáng tin cậy thì giữ donut và bỏ đường xu hướng.

## 5. Hình 4: mạng liên hệ giữa từ và cụm chủ đề

### 5.1. Những gì nhìn thấy trực tiếp

| Thành phần | Cách đọc |
|---|---|
| Node có nhãn như graph, text, data, tool | Các từ/khái niệm |
| Cạnh nối | Quan hệ giữa các từ; ảnh không công bố quy tắc tạo cạnh |
| Nhóm màu | “graph communities”, tức các cộng đồng trong mạng |
| Main Topical Groups | Những từ đại diện cho từng cộng đồng |
| Most Influential Elements | Ảnh ghi rõ “highest betweenness”, các phần tử nối những vùng chủ đề |
| Kích thước node khác nhau | Có mã hóa một đại lượng; không có chú giải đủ rõ để khẳng định đại lượng cụ thể |
| Network Structure: Focused, network ecology | Chỉ số/diễn giải của công cụ trong ảnh; chưa có công thức |

Không nên gọi đây là knowledge graph, attention graph của PhoBERT, hoặc biểu đồ sentiment. Màu trong ảnh thể hiện cộng đồng chủ đề, không có nghĩa xanh là tích cực và hồng là tiêu cực.

### 5.2. Cơ chế đề xuất cho webapp

Xây **mạng đồng xuất hiện từ/cụm từ** từ nhiều phản hồi thuộc bộ dữ liệu đang chọn:

1. Tách câu và tách từ tiếng Việt, giữ nguyên các cụm có nghĩa như “học phí”, “đăng ký học phần”, “giảng viên”.
2. Chuẩn hóa cho mục đích đếm, loại từ dừng và token không mang thông tin. Giữ liên kết về văn bản gốc để mở dẫn chứng.
3. Hai từ có cạnh khi xuất hiện trong cùng cửa sổ ở cùng một câu. Điểm khởi đầu để kiểm chứng: cửa sổ 5 từ sau tách từ; không nối xuyên các phản hồi.
4. Trọng số cạnh là số phản hồi khác nhau chứa quan hệ này, để một phản hồi lặp từ nhiều lần không chi phối toàn mạng.
5. Kích thước node theo số phản hồi có nhắc tới từ; độ dày cạnh theo trọng số cạnh.
6. Tìm cộng đồng bằng thuật toán như Louvain với phiên bản và seed cố định; đặt tên bằng 2–3 từ đại diện, không dùng LLM để đặt tên.
7. Nếu có mục “từ nối các nhóm”, tính betweenness riêng. Với cạnh có trọng số liên hệ, phải chuyển sang độ dài phù hợp, ví dụ `distance = 1/weight`, thay vì coi liên hệ mạnh là khoảng cách dài.
8. Chọn node, cạnh hoặc cộng đồng để xem các phản hồi tạo nên phần mạng đó.

Điểm khởi đầu về mật độ hiển thị: 40–60 node, khoảng 100–150 cạnh, ngưỡng đồng xuất hiện tối thiểu 2 phản hồi. Đây là tham số thử nghiệm cần chỉnh bằng dữ liệu thật. Ghi rõ khi chỉ hiển thị phần mạng đã lọc; không gọi centrality trên mạng rút gọn là centrality của toàn bộ tập dữ liệu.

Cụm mạng được suy ra từ từ ngữ, khác với 10 nhãn topic cố định của classifier NEU. Có thể lọc mạng theo topic classifier, nhưng không đổi tên hai khái niệm thành một.

Ảnh không đủ thông tin để tái tạo các chỉ số “Focused”, “ecology” hoặc cả bộ tab LDA/Stats. Chúng không phải điều kiện để đáp ứng đề nghị trực quan hóa.

## 6. Hiện trạng webapp đã kiểm tra qua mã nguồn

| Thành phần | Hiện có | Khoảng trống / hướng xử lý |
|---|---|---|
| `apps/web/src/SentenceDemo.tsx` | Input, ba câu mẫu, kết quả, lớp 2, lớp 3 | Đúng màn hình Đạt đang góp ý; cần tổ chức lại |
| `SentenceDemo.css` | Font Be Vietnam Pro, màu teal, các trạng thái responsive | Tái sử dụng hệ thiết kế, thêm token màu dữ liệu nhất quán |
| `services/inference/registry.py` | PhoBERT local, softmax sentiment/topic, batch inference, kiểm model identity | Chưa trả attribution; đường inference hiện trả điểm toàn đầu vào |
| `services/inference/preprocessing.py` | `underthesea`, PhoBERT tokenizer chậm, tối đa 128 token | Chưa có ánh xạ hoàn chỉnh raw span → từ đã tách → BPE token |
| `services/explanation.py` | 9router/LLM trả đúng hai chuỗi `reading`, `caution` | Không có trọng số từ; đề xuất loại phương án này khỏi app mới |
| `services/sensitivity.py` | Chọn cụm bằng UTF-16, kiểm grapheme, so baseline/variant | Tái sử dụng xử lý offset và nguyên tắc identity; không cộng thẳng các delta đơn lẻ |
| `services/worker.py` | Worker riêng, hàng đợi, ưu tiên và inference cặp | Cần job attribution có giới hạn, hủy được, không chặn prediction |
| `services/analytics.py` | Thống kê Negative/Toxic theo topic | Có nền tảng cho phần quyết định hữu ích |
| `services/storage/db.py` | Summary, mẫu số, nhãn AI/đã duyệt, revisions | Dùng cùng phạm vi cho donut, thống kê, dẫn chứng |
| `services/demo_scope.py` | `scope_token`, kiểm dữ liệu thay đổi giữa summary và drill-down | Phải áp dụng cho các trực quan hóa mới |
| `services/profiles.json` | NEU 4 sentiment/10 topic; UIT 3 sentiment/4 topic | Không hardcode donut ba nhóm hay index nhãn theo một profile |

Các điểm mã nguồn trực tiếp liên quan: câu mẫu ở `SentenceDemo.tsx:26`; dòng giữ nguyên văn bản ở `SentenceDemo.tsx:580`; khối mẫu ở `SentenceDemo.tsx:615`; các nhãn lớp ở khoảng dòng 696, 938, 1133; contract diễn giải ở `types.ts:357`; softmax được tạo trong `registry.py` và chưa có kết quả theo token.

Đây là khảo sát mã nguồn. Không dùng báo cáo kiểm thử cũ để khẳng định giao diện/thuật toán mới đã chạy thành công.

## 7. Quyết định quan trọng: lấy trọng số hình 1 từ đâu?

### 7.1. Ba lựa chọn không dùng LLM

| Cách làm | Có thể làm gì | Giới hạn | Đề xuất |
|---|---|---|---|
| Từ điển + quy tắc | Điểm nguyên kiểu +1, +2, -1, -2; cộng đúng như ảnh; chạy nhanh | Giải thích điểm của từ điển, không chứng minh vì sao PhoBERT dự đoán | Chỉ dùng nếu mục tiêu được chốt là minh họa lexical scoring |
| Bỏ/che từng cụm rồi chạy lại | Đo độ nhạy của model; tận dụng nền tảng hiện có | Các delta có tương tác, không có tính cộng thành điểm gốc | Dùng trong thao tác khám phá; không dùng tổng delta làm tổng attribution |
| Phân bổ Shapley theo nhóm từ | Đóng góp có dấu, có quan hệ cộng với điểm nền và điểm model được chọn | Nhiều lượt suy luận; cần quy ước baseline và ánh xạ token chính xác | Hướng chính đề xuất cho yêu cầu interpretability |

**Chọn hướng thứ ba để kiểm chứng trước.** Không hứa có ngay số nguyên giống ảnh. Giá trị của hình 1 là cấu trúc bằng chứng và phép cộng; với model thật, trọng số có thể là số thập phân theo điểm phần trăm.

Nếu kiểm chứng không đạt, báo rõ ràng giới hạn CPU/ánh xạ. Không âm thầm chuyển sang từ điển và vẫn gắn nhãn “đóng góp của PhoBERT”.

### 7.2. Điểm cần giải thích và phép cộng

Để có hướng tích cực/tiêu cực như ảnh, định nghĩa điểm cân bằng của **một đầu vào**:

`f(x) = 100 × [p_Positive(x) - p_Negative(x)]`

Trong đó `p` là softmax của model đang dùng. Đây là chênh lệch điểm nhãn model, không phải tỷ lệ phản hồi trong dataset và không phải xác suất dự đoán đúng.

Gọi `b` là đầu vào tham chiếu sau khi che các nhóm từ được xét:

`B = f(b)`

`D = tổng_i phi_i`

`f(x) = B + D`

`phi_i` là đóng góp Shapley xấp xỉ của cụm i. Bảng hiển thị các `phi_i` và **Tổng đóng góp D**; một dòng công thức ngắn nêu điểm nền và điểm sau khi cộng. Không đặt `B = 0` chỉ để bảng trông giống ảnh.

Nếu cần giải thích đúng nhãn đang dự đoán, dùng hàm `g_c(x) = 100 × p_c(x)`. Cùng các lần chạy coalition có thể thu điểm cho cả bốn nhãn sentiment và topic; không cần chạy thêm một model riêng cho từng nhãn.

### 7.3. Cách tính đề xuất

1. Đóng băng model identity, text revision, preprocessing và đầu vào token của dự đoán cần giải thích.
2. Lập các nhóm từ/cụm từ có ý nghĩa, bao phủ các token nội dung thuộc phạm vi phân tích. Cụm phủ định/tăng cường ưu tiên đi cùng từ liên quan nếu ánh xạ xác minh được.
3. Che token của nhóm bằng `<mask>` ở cấp token ID; giữ nguyên token đặc biệt, chiều dài và attention mask theo quy ước đã kiểm chứng. Không xóa đầu câu rồi vô tình kéo phần vượt 128 token vào cửa sổ model.
4. Xét nhiều thứ tự đưa các nhóm vào. Ở mỗi thứ tự, đo mức đổi điểm khi thêm một nhóm vào những nhóm đã có trước đó.
5. Lấy trung bình đóng góp qua các thứ tự. Mỗi thứ tự hoàn chỉnh có tổng delta bằng `f(x)-f(b)`, nên trung bình cũng giữ quan hệ cộng, trong sai số số học.
6. Tính bằng giá trị đầy đủ; làm tròn ở frontend. Nếu chỉ hiện những cụm lớn nhất, có dòng “Các cụm còn lại” để tổng vẫn khớp.

Đây là lời giải thích phụ thuộc cách nhóm từ và baseline che từ. Nó đo hành vi của classifier dưới phép thay đổi đầu vào đã định nghĩa; không phải chứng minh nhân quả về ngôn ngữ hay quá trình suy nghĩ của model.

### 7.4. Phủ định, từ lặp và nhãn đặc biệt

- “không tốt”, “không tệ”, “rất chậm”, “không những… mà còn…” cần các trường hợp kiểm tra riêng. Không gán màu chỉ bằng cách tìm một từ “tốt” hoặc “tệ”.
- Trong phương pháp model, cùng một từ lặp hai lần có thể có hai đóng góp khác nhau. Hiện riêng hoặc gộp bằng tổng thật, ví dụ `chậm (2 lần): -a + -b`. Chỉ hiện `w × 2` nếu thực sự dùng cùng w theo phương pháp lexical đã khai báo.
- Đóng góp dương/âm trên `f` nghĩa là nghiêng điểm model về Positive/Negative. Không khẳng định đó là nhãn sentiment độc lập của chính từ đó.
- Neutral/Toxic cần chế độ giải thích nhãn tương ứng (`g_Neutral`, `g_Toxic`), vì cân bằng Positive/Negative không giải thích đầy đủ hai nhãn này.
- Khi giải thích một nhãn cụ thể, dấu `+/-` nghĩa là tăng/giảm điểm nhãn đó. Không tô xanh và gọi “tích cực” cho một cụm đang tăng điểm Toxic. Chú giải và màu phải theo target được chọn.
- Giữ nhãn dự đoán gốc và confidence/điểm model. Attribution không ghi đè kết quả phân loại.

### 7.5. Bước kiểm chứng bắt buộc trước khi chốt triển khai P0

| Việc kiểm chứng | Điều kiện đạt |
|---|---|
| Raw text → underthesea → BPE → span | Khôi phục đúng vị trí trên raw text; kiểm Unicode tổ hợp, emoji, dấu câu, từ lặp |
| Tái tạo điểm đầu vào đầy đủ | Điểm chạy phục vụ attribution khớp dự đoán nguồn trong tolerance số học đã đo |
| Quy ước che từ | Baseline và coalition hợp lệ; model/tokenizer/preprocessing không bị thay giữa chừng |
| Quan hệ cộng | `B + sum(phi) ≈ f(x)` trước làm tròn; lưu residual |
| Chi phí CPU | Đo thời gian, số coalition, peak memory trên model thật; prediction vẫn đáp ứng được |
| Độ ổn định | So sánh các tập hoán vị trên nhóm câu cố định; xác định cụm có dấu/ranking thiếu ổn định |

Ngân sách khởi điểm để benchmark, chưa phải SLA: tối đa khoảng 24 nhóm, 8 hoán vị hoàn chỉnh, deduplicate coalition, batch theo năng lực worker. Với 24 nhóm và 8 hoán vị, cận đơn giản là `8 × (24-1) + 2 = 186` coalition khác nhau trước khi deduplicate thêm. Đây có thể đắt trên CPU; phải đo trước khi bật tự động cho mọi đầu vào.

Nếu quá chậm, ưu tiên cache, batch, nhóm cụm hợp lý và giới hạn phạm vi. Mọi thay đổi cách nhóm phải được phản ánh trong kết quả. Không giảm tính trung thực bằng cách sinh trọng số cho đẹp.

Với đầu vào bị cắt ngắn: chỉ highlight phần token model đã đọc khi ánh xạ xác minh được. Nếu chưa ánh xạ đáng tin cậy, hiển thị kết quả prediction và thông báo attribution chưa khả dụng cho đầu vào này, thay vì tô cả phần model chưa thấy.

## 8. Giao diện đề xuất

### 8.1. Bố cục

```text
NEU-ESC                           Bộ dữ liệu | Nghiên cứu

Nhập phản hồi                         Kết quả phân tích
[textarea]                            Cảm xúc · điểm model
[Phân tích] [Xóa]                     Chủ đề · điểm model
                                      Phân bố nhãn hiện có

Phân tích từ ngữ
┌────────────────────┬────────────────┬──────────────┬──────────────┐
│ Phản hồi           │ Từ / cụm từ    │ Đóng góp     │ Tổng đóng góp│
│ nguyên văn có      │ cụm A          │ +a           │              │
│ highlight liên kết │ cụm B          │ -b           │ D            │
│ với từng dòng      │ phần còn lại   │ c            │              │
└────────────────────┴────────────────┴──────────────┴──────────────┘
Điểm nền B + tổng đóng góp D = điểm đang giải thích
[Cách tính]  [Thử bỏ một cụm từ]

Tổng quan bộ phản hồi       [Chọn bộ dữ liệu] [Nguồn nhãn]
[Phân bố cảm xúc]           [Các chủ đề cần xem và số phản hồi]
[Mạng từ/cụm từ khi đã có dữ liệu]
[Danh sách phản hồi theo phần vừa chọn]
```

Desktop đủ rộng: bố cục bốn cột đúng hình 1, nguyên văn chiếm khoảng 40–45% chiều rộng. Tablet: nguyên văn ở phía trên, ba cột phân tích ở dưới. Mobile: nguyên văn → danh sách cụm/điểm → tổng và công thức; không ép chữ vào bốn cột hẹp.

Hình 1 và 2 dùng **một bộ dữ liệu attribution**, để không xảy ra highlight một cụm nhưng bảng chấm một cụm khác. Bảng không bị nhét vào cột nhỏ của kết quả dự đoán.

### 8.2. Nội dung bỏ và giữ

| Nội dung hiện tại | Xử lý đề xuất |
|---|---|
| “Văn bản gốc luôn được giữ nguyên” | Bỏ khỏi giao diện |
| “Thử nhanh với một câu mẫu” | Bỏ |
| Ba nút “Dịch vụ sinh viên”, “Trải nghiệm học tập”, “Một thông báo” | Bỏ; sửa empty-state không còn nhắc chọn câu mẫu |
| “Lớp 1 · Prediction”, “Lớp 2 · Interpretability”, “Lớp 3 · Decision Support” | Bỏ toàn bộ nhãn mang tính kiến trúc |
| Văn bản giải thích lặp, khối AI reading/caution | Thay bằng bảng có dữ liệu và mô tả phương pháp khi mở chi tiết |
| Hai dòng thông báo gửi tới dịch vụ diễn giải | Bỏ khi tích hợp LLM được loại bỏ |
| Cảm xúc, điểm model, chủ đề, phân bố nhãn | Giữ chức năng hiện có |
| Cảnh báo model thiếu, input bị cắt, lỗi tác vụ | Giữ đúng lúc phát sinh, viết ngắn gọn |
| Cờ khó phân loại | Hiện khi có cờ và nói cụ thể tác vụ nào; bỏ khối thông báo thành công dài khi không có cờ |
| Sensitivity thủ công | Giữ dưới thao tác “Thử bỏ một cụm từ”, tránh chiếm một khối lớn |
| Thống kê chủ đề và dẫn chứng | Tái tổ chức trong tổng quan dataset, dùng số thật |

Giữ font Be Vietnam Pro, nhận diện teal và bố cục thao tác quen thuộc. Màu xanh/đỏ dùng cho dữ liệu; Neutral xám, Toxic một màu hổ phách riêng. Không đổi toàn bộ theme vì ảnh tham chiếu dùng màu khác.

### 8.3. Phân tích từng câu

Một phản hồi có thể gồm nhiều câu. Nếu hiển thị nhãn cho từng câu, phải tách câu có offset và chạy classifier cho từng câu; không lấy nhãn cả đoạn gắn cho tất cả các câu con.

P0 tập trung một phản hồi và attribution ở đúng phạm vi dự đoán. Sau khi P0 đạt, thêm chế độ mở từng câu khi đầu vào có nhiều câu: hiển thị nhãn riêng, cho chọn câu cần attribution để giới hạn chi phí. Nhãn toàn phản hồi vẫn giữ riêng; không tự đổi thành trung bình các nhãn câu.

## 9. Hỗ trợ quyết định cần dẫn tới thao tác gì?

Donut và network chỉ có giá trị khi giúp trả lời được:

1. Bộ dữ liệu này có bao nhiêu phản hồi tích cực, tiêu cực, trung tính, Toxic?
2. Chủ đề nào có nhiều phản hồi tiêu cực nhất, với mẫu số bao nhiêu?
3. Trong nhóm đó, những cụm như “đăng ký học phần”, “lỗi”, “chậm” thường được nhắc cùng nhau ra sao?
4. Đọc những phản hồi nào để kiểm tra vấn đề?

Thống kê topic hiện có đủ nền tảng cho bước 2. Mỗi hàng nên có topic, `n tiêu cực / n đủ cả hai nhãn`, tỷ lệ, số Toxic riêng và nút mở dẫn chứng. Giữ quy tắc xếp hạng đã có `negative_count_desc`; không gọi “tỷ lệ cao nhất” nếu thực tế đang xếp theo số lượng.

Mạng từ bổ sung bước 3. Nhãn cụm có thể là “đăng ký học phần · lỗi · chậm”, kèm số phản hồi; không cần LLM viết một đoạn kết luận. Nhóm ít dữ liệu có dấu hiệu phù hợp; không đặt thành kết luận mạnh về toàn bộ sinh viên.

Tất cả phần tổng hợp dùng cùng `dataset_id`, profile, `label_source`, run/revision scope và bộ lọc. Khi mở dẫn chứng, kiểm `scope_token`; dữ liệu đổi thì tải lại thay vì hiện danh sách không còn khớp số trên biểu đồ.

Không tự đưa câu đang gõ vào donut của dataset. Câu chỉ tham gia thống kê sau khi người dùng lưu vào bộ dữ liệu theo luồng hiện có.

## 10. Thiết kế dữ liệu và tích hợp đề xuất

### 10.1. Attribution

Một job local riêng, khởi chạy sau khi prediction nguồn đã hoàn tất. Kết quả prediction hiển thị ngay; bảng attribution có trạng thái đang tính, lỗi, hủy và thử lại độc lập.

API dự kiến:

- `POST /api/v1/quick-analysis/{job_id}/attribution`: tạo job gắn với `source_prediction_id` và các lựa chọn phương pháp đã giới hạn phía server.
- `GET /api/v1/attributions/{id}`: đọc trạng thái và kết quả.
- Có cơ chế hủy job; có thể tích hợp hàng đợi hiện tại, nhưng không giả danh job sensitivity cặp vì bản chất công việc khác nhau.

Các trường kết quả cần có:

| Nhóm | Trường |
|---|---|
| Identity | job/item/revision/prediction, profile/schema, model/version, text hash |
| Method | method version, grouping version, baseline definition, target, unit, seed, số hoán vị hoàn tất |
| Coverage | phạm vi input token đã đọc, truncated, trạng thái ánh xạ |
| Spans | id, raw text, start/end UTF-16, token indices, đóng góp theo target, thông tin độ ổn định khi đã có |
| Totals | base value, sum contributions, output value, additivity residual |
| Lifecycle | queued/running/completed/cancelled/failed/unsupported, thời gian và lỗi có thể xử lý |

Server kiểm span khớp nguyên văn, không cắt grapheme, không chồng nhóm tính điểm và không thiếu phần đóng góp. Render bằng React text node/mark; không ghép HTML từ văn bản người dùng.

Cache phải gắn với text revision, model identity, preprocessing, phương pháp, baseline, grouping, target và ngân sách tính. Clear/sửa câu/đổi profile làm kết quả cũ mất hiệu lực trên UI. Kết quả tới muộn không được gắn sang câu mới.

Không đưa PyTorch/underthesea nặng vào API process nếu phá ranh giới runtime hiện tại. Inference và công việc NLP nặng chạy trong worker/model runtime; hàng đợi ưu tiên prediction, hủy được giữa batch và kiểm lại nguồn trước khi công bố kết quả.

### 10.2. Dataset visualizations

- Donut sử dụng `/datasets/{id}/summary` và mẫu số sentiment hiện có; phần toán tỷ lệ có thể làm tại frontend từ số đếm chuẩn.
- Network cần pipeline tổng hợp riêng. Đọc snapshot cùng phạm vi với summary, xử lý ngoài giao dịch SQLite đang mở; chỉ trả kết quả còn khớp snapshot.
- Không lấy một trang `/items` rồi coi đó là toàn bộ dataset. Tổng hợp server-side hoặc duyệt đầy đủ snapshot có giới hạn đã công bố.
- Dữ liệu network cần nodes, edges, communities, document counts, tham số tiền xử lý/cạnh, số phản hồi nguồn, giới hạn lọc và scope token.
- Drill-down node/cạnh/cộng đồng nên dựa trên membership theo snapshot. Không chỉ dùng tìm chuỗi `q` vì cách chuẩn hóa/cụm từ có thể cho tập kết quả khác.
- Với tập lớn: job nền và cache theo scope. Frontend tải graph khi mở phần này; không tăng chi phí trang nhập câu mặc định.

## 11. Loại tích hợp LLM khỏi phương án mới

Khi triển khai thay đổi này:

1. Bỏ tự gọi `getExplanation`, state và UI `reading/caution`, retry upstream, thông báo 9router trong `SentenceDemo.tsx`.
2. Dọn contract/client helper tương ứng trong `types.ts`, `api.ts`.
3. Bỏ khởi tạo `ExplanationService` và endpoint explanation khỏi đường production sau khi rà các caller; thay bằng API attribution local.
4. Dọn module/provider/config/script/help không còn dùng. `App.tsx` hiện có hướng dẫn gateway; cần cập nhật cùng tài liệu PRODUCT, DESIGN và vận hành.
5. Cập nhật tests theo hành vi mới: không gửi request ngoài, không yêu cầu API key, không hiện lỗi “chưa cấu hình dịch vụ diễn giải”. Không xóa các kiểm thử source identity, stale result, hủy job đang cần cho pipeline local mới.

Không cần huấn luyện lại student để bỏ LLM. Attribution cũng dùng checkpoint hiện tại; chỉ thêm cách đo và hiển thị kết quả của nó.

## 12. Kế hoạch triển khai theo phụ thuộc

| Mốc | Công việc | Đầu ra / điều kiện xong |
|---|---|---|
| P0-A: chốt semantics và spike | Xác định target score, baseline, ánh xạ raw/BPE; benchmark attribution thật | Báo cáo tính đúng, chi phí, giới hạn; không có số giả |
| P0-B: dọn giao diện và tích hợp cũ | Bỏ câu mẫu, nhãn lớp, khối LLM; giữ prediction và cảnh báo hữu ích | Màn hình gọn, prediction hoạt động độc lập |
| P0-C: engine attribution | Job/worker, grouping, coalition inference, tổng, cache, hủy, identity | API trả spans và phép cộng kiểm tra được |
| P0-D: hình 1 + hình 2 | Bảng 4 cột thích ứng; highlight liên kết bảng; trạng thái loading/error | Hoàn thành phần ưu tiên nhất |
| P0-E: nghiệm thu | Kiểm model thật, phủ định, lặp từ, Unicode, nhãn đặc biệt, responsive | Chốt P0 trước khi đầu tư network |
| P1-A: donut | Tận dụng summary; đủ nhãn NEU/UIT; click lọc dẫn chứng | Hình 3 có dữ liệu thật và mẫu số rõ |
| P1-B: chủ đề/vấn đề | Làm gọn topic attention, số lượng/tỷ lệ/Toxic, danh sách dẫn chứng | Khôi phục giá trị Decision Support |
| P1-C: nhiều câu | Tách câu đúng raw offsets, prediction mỗi câu, attribution theo câu được chọn | Đáp ứng “phân tích từng câu” khi đầu vào là đoạn |
| P2: network | Tiền xử lý, co-occurrence, cộng đồng, centrality, UI tương tác | Hình 4 liên kết tới phản hồi thật |
| Sau P2 nếu có dữ liệu | Trend theo thời gian thật, thêm xuất biểu đồ khi cần | Không giả thời gian hoặc dữ liệu |

Đường phụ thuộc chính: `P0-A → P0-C → P0-D → P0-E`. Dọn UI có thể được chuẩn bị độc lập, nhưng không coi việc dọn chữ là hoàn tất hình 1. Donut và network không phải điều kiện để bắt đầu sử dụng P0.

Không ước lượng ngày hoàn thành attribution trước spike model thật. Phần ít bất định là dọn UI và donut; phần nhiều bất định nhất là mapping PhoBERT và chi phí attribution CPU, sau đó là chất lượng nhóm từ của network.

## 13. Bản đồ file dự kiến

| File/module | Trách nhiệm |
|---|---|
| `apps/web/src/SentenceDemo.tsx` | Điều phối prediction, attribution, dataset summary; loại khối cũ |
| `apps/web/src/SentenceDemo.css` | Bố cục và màu dữ liệu, responsive, focus |
| Component mới `HighlightedFeedback.tsx` | Render nguyên văn và spans có thể chọn |
| Component mới `AttributionTable.tsx` | Cụm từ, trọng số, tổng và điểm nền |
| Component mới `SentimentDistribution.tsx` | Donut và chú giải dùng counts, nhãn từ profile |
| Component mới `TermNetwork.tsx` | Network, chọn node/nhóm, dữ liệu dẫn chứng |
| `apps/web/src/types.ts`, `api.ts` | Contract mới và bỏ contract LLM không còn dùng |
| `services/inference/registry.py` | API nội bộ cho coalition inference cùng model identity |
| `services/inference/preprocessing.py` | Hỗ trợ ánh xạ đã kiểm chứng, không đổi prediction âm thầm |
| Module mới `services/attribution.py` | Phân bổ đóng góp, kiểm tổng, phiên bản phương pháp |
| `services/worker.py`, `services/storage/db.py` | Lifecycle job, cache/storage và migration nếu cần |
| `services/api/main.py` | Endpoint attribution/network, validation nguồn |
| Module mới `services/text_network.py` | Tổng hợp từ và mạng; không phụ thuộc LLM |
| `services/analytics.py`, `services/demo_scope.py` | Dùng lại mẫu số, nhãn và snapshot; chỉ mở rộng khi cần |
| `services/explanation.py`, help/config/doc liên quan | Dọn theo việc loại LLM |

Tên component/module mới là đề xuất, chưa phải file đã được tạo. Bản đầu donut có thể dùng SVG; graph chỉ thêm dependency cần thiết sau khi chốt quy mô. Không cần một thư viện dashboard lớn để đáp ứng bốn ảnh.

## 14. Các trạng thái phải có

| Tình huống | UI và hành vi mong muốn |
|---|---|
| Chưa nhập | Một hướng dẫn ngắn ở ô kết quả; không dựng nhiều khối trống |
| Đang prediction | Trạng thái tác vụ hiện tại, có hủy |
| Có prediction, attribution đang chạy | Kết quả nhãn đọc được ngay; bảng có tiến độ thật theo batch/hoán vị nếu đo được |
| Attribution lỗi/chưa hỗ trợ | Giữ prediction; không tô giả; thử lại hoặc cho biết giới hạn cụ thể |
| Sửa câu/clear/đổi profile | Vô hiệu hóa dữ liệu liên quan, loại callback cũ |
| Từ lặp/phủ định/emoji | Vị trí và điểm ứng với đúng lần xuất hiện |
| Toàn đóng góp gần 0 | Hiện số đo; không tự tuyên bố câu trung tính nếu classifier dự đoán khác |
| Toxic/Neutral | Mục giải thích nhãn thích hợp; không ép về thang nhị phân |
| Text >128 token | Cảnh báo và phạm vi đúng; phần chưa được model đọc không nhận attribution |
| Chưa chọn dataset | Một lời nhắc nhỏ; không dùng dữ liệu của câu đơn để giả donut/network |
| Dataset chưa có nhãn | Hiện số chưa phân tích; không chia cho 0 |
| Dữ liệu/nhãn đổi giữa hai request | Refresh scope; không hiện số và dẫn chứng mâu thuẫn |
| Mạng quá ít liên hệ | Trạng thái ít dữ liệu hoặc danh sách từ; không sinh cạnh trang trí |

## 15. Tiêu chí nghiệm thu

### 15.1. P0 bắt buộc

- Không còn các câu/nút mẫu đã được yêu cầu bỏ và nhãn “Lớp 1/2/3” trong màn hình demo.
- Cảm xúc, điểm model, topic và các trạng thái prediction tiếp tục dùng kết quả thật.
- Không có yêu cầu tới LLM/9router; app mới không cần cấu hình dịch vụ diễn giải.
- Có nguyên văn, cụm từ, trọng số có dấu và tổng; mỗi dòng truy ra được vị trí nguồn.
- Highlight và bảng sử dụng cùng attribution, cùng prediction/revision/model identity.
- Điểm nền + tổng đóng góp khớp điểm target trước làm tròn; nhóm ẩn được cộng vào “phần còn lại”.
- Giá trị thập phân, âm, bằng 0, lặp từ khác ngữ cảnh được hiển thị đúng.
- Không dùng các delta độc lập hoặc attention để giả thành attribution cộng được.
- Unicode NFC/NFD, emoji, dấu câu, HTML-like text không làm hỏng spans hoặc render.
- Có bài kiểm tra phủ định, tăng cường, phản hồi vừa khen vừa chê, Neutral/Toxic và input cắt ngắn.
- Prediction không đợi attribution, các job được hủy/dọn đúng, không gắn kết quả cũ sang câu mới.
- Bảng dùng được ở desktop 1440px, tablet 768px, mobile 390px; keyboard/touch thay được hover.

### 15.2. P1 và P2

- Donut được đối chiếu với counts API và đủ mọi nhãn của profile; mẫu số loại phản hồi thiếu nhãn.
- Net của dataset là chênh lệch tỷ lệ đếm, tách khỏi điểm polarity của một câu.
- Topic ranking có số đếm, mẫu số, nguồn nhãn và dẫn chứng đúng scope.
- Không có trend thời gian khi không có timestamp nguồn phù hợp.
- Network có quy tắc tạo cạnh, màu cộng đồng, số đếm và membership kiểm tra được.
- Chọn node/cạnh/cụm mở đúng phản hồi, kể cả khi dataset có nhiều trang.
- Màu network không bị giải thích thành màu sentiment; cụm network không giả thành topic model.
- Không tự tạo tên vấn đề hoặc kết luận bằng LLM.

### 15.3. Kiểm thử cần thực hiện khi triển khai

1. Unit: span mapping, target calculation, Shapley telescoping, baseline, grouping, số học và trạng thái unsupported.
2. API/worker: nguồn hết hạn/đổi revision/model, cache identity, hủy/timeout, không có outbound explanation request.
3. API analytics: mẫu số, bốn nhãn, thay đổi nguồn nhãn, dữ liệu nhiều trang, scope conflict.
4. E2E: bỏ sample buttons; nhập thật, highlight ↔ table; lỗi attribution không làm mất prediction; click chart → dẫn chứng; responsive.
5. Model thật: đối chiếu điểm nguồn, residual, latency/memory, ảnh hưởng lên prediction queue; không dùng test double để kết luận tốc độ hay chất lượng giải thích.

Tests hiện tại có kiểm tra sự hiện diện của ba sample buttons và auto-call LLM, nên cần sửa theo yêu cầu mới; không coi chúng là lý do giữ UI cũ. Duy trì các bài kiểm tra identity, Unicode, snapshot và lưu/xuất/rà soát dữ liệu không phụ thuộc bố cục cũ.

Lượt lập kế hoạch này chưa chạy build/test vì chưa sửa mã ứng dụng. Khi triển khai, chạy build TypeScript/Vite, tests đúng phần thay đổi, regression phụ thuộc và kiểm tra model thật như trên.

## 16. Điểm cần chốt bằng kiểm chứng, không đoán từ ảnh

| Điểm còn bất định | Cách giải quyết |
|---|---|
| Trọng số trong ảnh xuất phát từ thuật toán nào | Không suy đoán nguồn; chọn và công bố phương pháp của webapp |
| Độ nhanh/ổn định của Shapley trên máy hiện tại | Spike P0-A, đo model thật trước khi chốt trải nghiệm tự chạy |
| Mapping qua underthesea và PhoBERT tokenizer chậm | Xây mapping có invariant và dữ liệu kiểm thử; không dựa vào `offset_mapping` không có sẵn |
| Nhóm cụm từ tiếng Việt có đủ tự nhiên | Kiểm trên bộ câu đa dạng; phân biệt grouping hiển thị và đơn vị được chấm |
| Timestamp cho đường xu hướng | Kiểm schema dataset cụ thể; chưa có thì không triển khai trend |
| Chất lượng mạng trên bộ dữ liệu trình bày | Kiểm tra số liên hệ và dẫn chứng thật; chỉnh tham số có phiên bản |

Định hướng bàn giao: **giữ prediction; bỏ LLM và các khối lớp hiện tại; ưu tiên bảng đóng góp + highlight; sau đó bổ sung thống kê có dẫn chứng và mạng từ có dữ liệu thật.**
