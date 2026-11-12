# Donut đóng góp cụm từ · 12/11/2026

## Kết quả

**Nghiệm thu cuối:** frontend build PASS;381 backend passed; toàn bộ167 E2E cases có execution cuối PASS,0 skip và không thiếu case so với fresh collection; browser checkpoint thật trên build cuối1passed. E2E cuối dùng4 tập execution, không tuyên bố lượt full ban đầu165passed/2failed đã PASS. Raw logs/XML các lần fail giữ nguyên; [manifest từng case và nguồn XML](../test-results/contribution-donut-20261112/e2e-final-coverage.json) ghi bằng chứng thành công cuối.

Donut tại **Câu vừa phân tích** chuyển từ đếm nhãn của một item sang **tỷ trọng độ lớn đóng góp của toàn bộ cụm từ trong chính văn bản**. Một lần nhập vẫn tạo một prediction/item, kể cả đoạn nhiều câu. Bảng bốn cột, highlight hai chiều, topic ranking, network, evidence và dataset workspace giữ luồng hiện hành. Không commit/push/deploy/train, thay weights/current pointer nguồn hoặc dùng database live để test.

Nguyên nhân cũ: `/quick-analysis` tạo một item cho toàn văn; summary đếm nhãn item đó. Vì vậy Negative →100%,1 phản hồi, net sentiment−100 dù attribution có hai dấu. Biểu đồ mới chỉ lấy **cùng snapshot completed đã validated với bảng**, không đổi ý nghĩa summary hay tách câu để tạo nhiều prediction.

## Công thức và target

`P = sum(max(phi_i,0))`, `N = sum(max(-phi_i,0))`, `M = P+N`; tỷ trọng là `100*P/M` và `100*N/M`. Tổng trong bảng vẫn `D=P-N=sum(phi_i)` điểm phần trăm, không clamp. Dùng mọi group gốc, không cộng lại dòng “Các từ còn lại”, baseline, output, softmax hoặc số lượng group.

Tính tỷ lệ sau khi scale các phi bằng `max(abs(phi))` để tránh tổng độ lớn overflow hoặc tiny values underflow. Hình tròn giữ tỷ lệ thật, không thêm diện tích tối thiểu cho lát nhỏ. Hiển thị1 chữ số thập phân bằng số phần nghìn nguyên và phần bù, tổng100,0%. Phía khác0 nhưng làm tròn0,0% được chú thích dưới0,05% trước làm tròn. Mọi phi=0 →empty state; NaN/Infinity hoặc payload sai →error, không thay bằng0. Validator giữ tolerance1e-6 và bổ sung kiểm tổng finite.

- `polarity_margin = 100*(p_positive-p_negative)`: xanh/đỏ, “Nghiêng tích cực / Nghiêng tiêu cực”.
- `label_score = 100*p_label`: xanh lam/nâu, “Tăng điểm / Giảm điểm [tên nhãn từ profile]”, gồm Trung tính và Ngôn từ độc hại. Không gán cảm xúc tích cực cho tăng Toxic.

Donut là thông tin: SVG role img + mô tả screen reader, legend chữ và%, không button/tabIndex/aria-pressed/cursor pointer hay handler lọc evidence. Topic/network vẫn lọc evidence. Không thêm request hoặc model forward cho phép chuẩn hóa này. Summary query và guard total1 giữ nguyên cho topic/network/evidence; tải/lỗi summary không chặn donut attribution.

## Bằng chứng checkpoint thật offline

Runtime riêng: `test-results/contribution-donut-20261112/preview-runtime`. Bundle nguồn được đọc/copy qua `_verify_and_copy_active_bundle`, kiểm inventory SHA-256 nguồn/copy và current.json byte-identical; kiểm lại14 files gồm manifest sau lượt model. [Bundle](../test-results/contribution-donut-20261112/bundle-info.json), [integrity](../test-results/contribution-donut-20261112/source-integrity.json).

- Model: `neu-phobert-mtl-ed-s42`, version `neu-phobert-mtl-ed-s42-e10-617f852a3fff`, schema neu-v1, CPU FP32 eval, K8.
- Checkpoint SHA-256: `036b62c7b24fbe10ba30562090908fe8c81d0ebe339a84ad9fb02a569b2e20b1`.
- Manifest SHA-256: `5117b413d141d4e6b80a2805b9b5ff27b353d404d3a42bc95c29055e4f527b1d`.
- [JSON đầy đủ](../test-results/contribution-donut-20261112/real-model/real-contribution-evidence.json): văn bản, prediction, source identity/hash, mọi groups, aggregates, P/N/D, tỷ lệ và request inventory; page_errors=[];7 POST prediction và7 POST attribution cho7 lần submit, không tăng khi render/resize/mở-thu bảng.

| Văn bản | Nhãn thật / target | Groups | P | N | D | Donut tăng / giảm |
|---|---|---:|---:|---:|---:|---|
| Đoạn siêu thị trong yêu cầu | Tiêu cực / polarity_margin |17|52,661228|153,810808|−101,149580|25,5% /74,5%|
| Dịch vụ tốt nhưng thời gian chờ quá lâu. | Tiêu cực / polarity_margin |7|47,466926|75,340287|−27,873361|38,7% /61,3%|
| Thư viện sáng sủa nhưng wifi mất kết nối mỗi buổi chiều. | Trung tính / label_score0 |10|41,656627|67,576607|−25,919980|38,1% /61,9%|
| Câu Toxic tác giả viết, nguyên văn trong JSON | Ngôn từ độc hại / label_score3 |11|112,048582|12,559855|99,488727|89,9% /10,1%|

Mỗi completed được đối chiếu phần trăm legend **và độ dài SVG arc** với toàn bộ groups, D với aggregate; mở/thu bảng không đổi donut. Câu dài55 lần “Thư viện có tài liệu mới.” thực sự unsupported do truncation, giữ prediction và không có chart cũ. Loading được giữ POST rồi chuyển tiếp response thật; lỗi410 được tạo bằng hết hạn **riêng source quick của test** trong database runtime riêng khi GET đang pending; polling dừng, prediction giữ lại.

### Toàn bộ17 groups của đoạn siêu thị

P cộng g_2,g_4,g_8,g_9,g_15,g_16; N lấy độ lớn11 group âm còn lại. Không chọn riêng6 group trong bảng thu gọn.

| Group | Cụm từ nguyên văn | phi (điểm phần trăm, làm tròn ở đây) |
|---|---|---:|
|g_0|Kể từ khi|−7,594983|
|g_1|một người quản lý mới|−8,832362|
|g_2|tiếp quản, siêu thị|3,654184|
|g_3|từng được coi|−3,651632|
|g_4|là tốt nhất|15,705858|
|g_5|quanh đây này|−4,883140|
|g_6|đã sa sút thảm hại|−63,196169|
|g_7|. Họ hầu như|−9,312193|
|g_8|không có gì cả|0,521919|
|g_9|, rau củ|14,187794|
|g_10|quả thì luôn|−1,079382|
|g_11|hết hạn/|−3,019592|
|g_12|hỏng, và|−5,108477|
|g_13|cửa hàng không được duy trì|−46,624641|
|g_14|/chăm chút cẩn thận|−0,508237|
|g_15|. Được cái là|2,965261|
|g_16|nhân viên dễ thương|15,626212|

Full precision: P52,66122846514918; N153,81080834777094; M206,47203681292012; D−101,14957988262177. Tỷ lệ25,505259345537617% /74,49474065446238%. Baseline12,55522295832634 +D =output−88,59435692429543, residual0. Bảng hiển thị−101,1 điểm phần trăm, donut25,5% /74,5%; không đổi số/dấu để ép câu chuyện. Dấu của “không có gì cả” hay “rau củ” là kết quả model trong ngữ cảnh, không phải từ điển cảm xúc.

## Files sửa trong lượt này

- Mới: `apps/web/src/ContributionDistribution.tsx`, `contributionShares.ts`: chart thông tin, phép chuẩn hóa, làm tròn và trạng thái.
- `SentenceDemo.tsx`: thay caller donut, bỏ mapping counts chỉ phục vụ donut, giữ summary/guard và topic/network/evidence; `SentenceDemo.css`: legend thông tin và responsive.
- `attributionValidation.ts`: từ chối tổng không finite; không nới source/parity/aggregate validation. `useAttribution.ts` và request epoch/terminal guard không sửa.
- Mới: `tests/e2e/test_contribution_donut.py`, `tests/inference/test_contribution_donut_real_model.py`.
- Cập nhật assertions có chủ đích ở attribution regressions, feedback redesign, demo scope, workspace và live browser test; thay assertions net/count của demo bằng tỷ trọng, giữ assertions dataset/review/export/network/sensitivity.
- `WEBAPP_ATTRIBUTION_CONTRACT.md`, `PRODUCT.md`, `DESIGN.md`, `LOCAL_APP.md` và báo cáo này.

`SentimentDistribution.tsx` cũ không sửa; kiểm caller xác nhận trước thay đổi chỉ demo dùng nó. Thống kê dataset/API summary vẫn đếm phản hồi đúng semantics. Không sửa backend/model/db implementation để vẽ chart.

## Kiểm thử thực sự chạy

| Lượt | Kết quả | Artifact |
|---|---|---|
| Frontend strict TypeScript + Vite production build |PASS,95 modules|[build.log](../test-results/contribution-donut-20261112/build.log)|
| Backend full ngoài E2E |381 passed,5 real_model deselected,22 warnings,335,74s|[backend.xml](../test-results/contribution-donut-20261112/backend.xml), [log](../test-results/contribution-donut-20261112/backend.log)|
| Regression donut mới |21 passed,47,34s,không skip|[formula.xml](../test-results/contribution-donut-20261112/formula.xml), [log](../test-results/contribution-donut-20261112/formula.log)|
| Browser API+worker checkpoint thật, build cuối sau giãn legend768 |1 passed,78,46s,không skip|[real-model.xml](../test-results/contribution-donut-20261112/real-model.xml), [log](../test-results/contribution-donut-20261112/real-model.log)|
| Reordered schema riêng (Toxic ID/index1, Positive3) |2 passed,19 deselected,11,76s|[reordered-schema.xml](../test-results/contribution-donut-20261112/reordered-schema.xml)|
| Network R09 sau chỉnh thời gian chờ |1 passed,43,26s|[network-final.xml](../test-results/contribution-donut-20261112/network-final.xml), [log](../test-results/contribution-donut-20261112/network-final.log)|
| Full E2E lượt đầu, hoàn tất |165 passed,2 failed,không skip,2069,43s|[e2e.xml](../test-results/contribution-donut-20261112/e2e.xml), [log](../test-results/contribution-donut-20261112/e2e.log)|
| Nhóm kiểm lại sau CSS cuối |30 passed,1 failed (timeout bảng attribution15s),303,82s|[final-regression.xml](../test-results/contribution-donut-20261112/final-regression.xml), [log](../test-results/contribution-donut-20261112/final-regression.log)|
| Full E2E coverage cuối,9 files qua4 tập execution |167 cases cuối PASS,0 fail/skip;fresh collect167 khớp chính xác,không missing/extra|[manifest](../test-results/contribution-donut-20261112/e2e-final-coverage.json), [kiểm coverage](../test-results/contribution-donut-20261112/coverage-check.log)|
| E2E cuối nhóm1 (attribution +donut +scope) |74 passed,833,34s,không skip|[XML1](../test-results/contribution-donut-20261112/e2e-final-1.xml)|
| E2E cuối nhóm3 (workspace/review/export/sensitivity) |46 passed,882,48s,không skip|[XML3](../test-results/contribution-donut-20261112/e2e-final-3.xml)|
| E2E cuối SentenceDemo |42 cases thuộc module SentenceDemo đều passed trong lượt47 cases; redesign được chạy lại riêng bên dưới|[XML2 nguyên bản](../test-results/contribution-donut-20261112/e2e-final-2.xml), [log](../test-results/contribution-donut-20261112/e2e-final-2.log)|
| E2E cuối toàn file redesign |5 passed,49,56s,không skip|[XML redesign](../test-results/contribution-donut-20261112/e2e-final-redesign.xml), [log](../test-results/contribution-donut-20261112/e2e-final-redesign.log)|

21 cases mới bao gồm25/75,D−80; chỉ dương/âm/cân bằng/toàn0;9 groups và aggregate không cộng hai lần; thập phân/subnormal5e−324/tiny1e−300/độ lớn1e308 tránh overflow; NaN/±Infinity bị chặn; polarity/Neutral/Toxic/UIT double và đổi thứ tự profile; không tương tác lọc hoặc request mới. Attribution regressions bổ sung chart assertions cho A→B muộn, clear/profile/unmount/cancel, terminal404/410/409/422 và cancel-completed + poll cũ500/404/failed.

Full E2E lượt đầu phát hiện R09 timeout15s khi network đang queued sau attribution. Tái hiện riêng1failed; database runtime fixture xác nhận attribution completed sau17,29s rồi network completed, không có error. Test này kiểm membership/keyboard/evidence chứ không phải SLA cold-start15s; tăng chờ graph thành60s, giữ mọi assertion nguồn/snapshot/node/cạnh/cộng đồng/tương tác. Chạy lại riêng **1passed,43,26s** (toàn test gồm khởi động và2 lần phân tích), không sửa scheduling/backend hoặc skip test để làm xanh.

Failure còn lại của full suite là U14 còn assertion donut chứa “1 /1” theo counts cũ. Đã thay có chủ đích bằng header contribution +đối chiếu SVG/legend với mọi groups thật trả về +không có net sentiment; assertion1/1 của topic giữ nguyên. Ca này và R09 đều pass trong nhóm kiểm lại sau CSS. Nhóm đó gặp R04 chờ bảng15s khi attribution còn chạy; đổi chờ60s theo deadline, không bỏ kiểm bảng/highlight/meter/tổng/method/LLM trap. Full suite cuối chạy lại toàn bộ9 files qua3 pytest processes/runtime tách biệt.

R04 trong fixture thực tế completed sau15,79s, vượt timeout cũ khoảng0,79s. Nhóm demo chạy đồng thời với2 nhóm khác tiếp tục gặp2 timeout (45passed/2failed,820,26s): U07 prediction B sau clear đợi8s trong lúc attribution A còn khởi tạo NLP; U13 sensitivity đợi15s cũng chia sẻ worker với attribution. Những test này đã pass trong lượt tuần tự đầu và kiểm reset/viewport, không phải latency SLA. Đổi riêng thời gian chờ đó thành60s, giữ mọi assertion; chạy lại toàn bộ47 cases nhóm demo riêng. Log/XML đồng thời được giữ với hậu tố `-concurrent`.

Lượt47 cases tiếp theo:46passed/1failed,712,63s. **Cả42 SentenceDemo pass**; R08 timeout ở helper chờ prediction B15s ngay sau A, cùng vấn đề worker cold NLP. Đổi helper chờ60s, giữ kiểm đúng nguồn prediction, tỷ lệ groups, evidence và topic; chạy lại **cả file redesign5passed/49,56s**. Kết quả cuối lấy74+42+46+5=167 executions thực sự pass. Script `check_e2e_coverage.py` collect lại toàn bộ suite và đối chiếu từng nodeid với các XML nguyên bản; manifest không xóa hoặc viết lại failure cũ thành PASS.

Sau visual QA, thêm column-gap24px giữa hai legend ở768 để tỷ lệ không sát swatch phía kia; mobile vẫn một cột. Build và checkpoint browser cuối kiểm geometry gap>=16px, không overflow ở1440/768/390/320 và chụp lại ảnh. Đó là thay đổi CSS cuối, không đổi phép tính/lifecycle.

Lịch sử chưa đạt được giữ rõ: lượt targeted đầu và lượt formula chẩn đoán bị dừng vì fixture truyền NaN/Infinity qua JSON protocol của Playwright làm driver lỗi; chưa có kết quả suite hoàn tất, không tính PASS. Fixture cuối gửi body string (NaN sai JSON; ±1e999 là JSON hợp lệ parse thành Infinity), kiểm đúng parse error/validator mà không làm hỏng driver. Model browser lượt đầu1failed do ModelUnavailable trước prediction, chưa xác định chi tiết exception cold-start; load/predict offline trực tiếp và job mới sau đó thành công. Lượt tiếp1failed vì assertion dùng innerText có newline để so textContent; đã sửa cách so sánh, không bỏ assertion mở/thu bảng. Logs/XML các lượt fail được giữ trong cùng thư mục. Backend được collect trước khi thêm test real mới, vì vậy5 deselected của lượt đó không phải tổng real_model hiện tại.

## Ảnh đã mở xem

Ảnh prefix `real-` dưới đây dùng checkpoint thật offline, không là mockup/test double. Viewports1440/390/320/768 kiểm body/pane không overflow, SVG và legend khớp tỷ lệ; table/highlight giữ tương tác hai chiều.

- Siêu thị overview: [desktop1440](../test-results/contribution-donut-20261112/real-model/real-supermarket-overview-1440.png), [mobile390](../test-results/contribution-donut-20261112/real-model/real-supermarket-overview-390.png), [320](../test-results/contribution-donut-20261112/real-model/real-supermarket-overview-320.png), [768](../test-results/contribution-donut-20261112/real-model/real-supermarket-overview-768.png).
- Bảng siêu thị: [1440](../test-results/contribution-donut-20261112/real-model/real-supermarket-table-1440.png), [390](../test-results/contribution-donut-20261112/real-model/real-supermarket-table-390.png). Toàn trang: [desktop](../test-results/contribution-donut-20261112/real-model/real-supermarket-page-desktop.png), [mobile](../test-results/contribution-donut-20261112/real-model/real-supermarket-page-mobile.png).
- Target label-score: [Neutral desktop](../test-results/contribution-donut-20261112/real-model/real-library-overview-1440.png), [Toxic mobile](../test-results/contribution-donut-20261112/real-model/real-toxic-overview-390.png).
- [Loading](../test-results/contribution-donut-20261112/real-model/real-loading.png), [unsupported thật](../test-results/contribution-donut-20261112/real-model/real-unsupported.png), [source410 thật](../test-results/contribution-donut-20261112/real-model/real-source-410.png): không chart cũ, không100% từ prediction.

Ảnh trong `test-results/contribution-donut-20261112/test-double/` và ảnh full E2E redesign dùng software predictor/API fixtures, chỉ chứng minh UI/lifecycle và luồng workspace. UIT được kiểm bằng double, production tiếp tục unavailable.

## Chạy và dừng app đã kiểm

[http://127.0.0.1:18865/#/demo](http://127.0.0.1:18865/#/demo), runtime test riêng kể trên, schema4 và worker alive. Đây là process tạo trong lượt này; không restart/kill preview18765 hoặc process người dùng khác. Quick sources có TTL15 phút; nhập/phân tích lại để xem kết quả mới, ảnh/JSON lưu bền trong test-results.

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.\scripts\start-local.ps1 -Port 18865 -RuntimeDirectory 'F:\DPL_NEU-ESC\test-results\contribution-donut-20261112\preview-runtime'
.\scripts\stop-local.ps1 -RuntimeDirectory 'F:\DPL_NEU-ESC\test-results\contribution-donut-20261112\preview-runtime'
```

Lệnh tái kiểm từ root repo (frontend build trước E2E):

```powershell
npm --prefix apps/web run build
.\.venv\Scripts\python.exe -m pytest --ignore=tests/e2e -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/e2e -q --tb=short
$env:FEEDBACK_FIX_APP_URL='http://127.0.0.1:18865'
$env:FEEDBACK_FIX_RUNTIME='F:\DPL_NEU-ESC\test-results\contribution-donut-20261112\preview-runtime'
$env:FEEDBACK_FIX_EVIDENCE='F:\DPL_NEU-ESC\test-results\contribution-donut-20261112\real-model'
.\.venv\Scripts\python.exe -m pytest -m real_model tests/inference/test_contribution_donut_real_model.py -q -s
```

## Giới hạn

K8 là permutation Shapley **ước lượng**; các masked coalitions khác phân phối tự nhiên. Tỷ trọng không phải tỷ lệ từ tích cực/tiêu cực, xác suất cảm xúc hay bằng chứng nhân quả. Không ép input phải có hai màu và không assert một cụm từ luôn cùng dấu. UIT chưa có checkpoint production. Các timing chỉ là lượt kiểm local, không phải SLA.
