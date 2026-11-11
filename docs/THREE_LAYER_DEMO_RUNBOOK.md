# Runbook Trình diễn Demo Webapp Ba lớp (`Prediction · Interpretability · Decision Support`)

- **Trạng thái tài liệu:** **ĐÃ REHEARSAL MODEL THẬT TRÊN BẢN COPY BẤT BIẾN (M4 — 2026-11-10)** *(Đã chạy xác nhận trọn vẹn luồng H2 đơn luồng offline trên bản copy bất biến của bundle active NEU và bộ 24 câu nguyên vẹn `data/demo/three_layer_feedback_vi.csv`; kiểm chứng song song bằng G3 Playwright real-model E2E).*
- **Bộ dữ liệu minh họa:** [`data/demo/three_layer_feedback_vi.csv`](file:///f:/DPL_NEU-ESC/data/demo/three_layer_feedback_vi.csv) (24 câu, `illustrative=true`, xem thêm [`data/demo/README.md`](file:///f:/DPL_NEU-ESC/data/demo/README.md))
- **Tài liệu quy chuẩn:** [`docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md`](file:///f:/DPL_NEU-ESC/docs/WEBAPP_THREE_LAYER_DEMO_IMPLEMENTATION_PLAN_2026-11-10.md) (mục H1–H3)

---

## 1. Quy tắc Rehearsal & Chọn đường đi xác định (H2)

1. **Không sửa dữ liệu hoặc chỉnh ngưỡng theo kết quả chạy:** Import nguyên 24 câu từ [`three_layer_feedback_vi.csv`](file:///f:/DPL_NEU-ESC/data/demo/three_layer_feedback_vi.csv) với hệ nhãn `NEU (Thảo luận sinh viên)` và chạy suy luận thật một lần trọn vẹn trước buổi trình diễn.
2. **Chọn Chủ đề cần chú ý:** Chọn chủ đề đứng đầu bảng xếp hạng mặc định (`negative_count DESC, eligible_count DESC, topic_id ASC`), sau đó bấm nút xem phản hồi tiêu cực (`sort=source_row ASC`).
3. **Chọn phản hồi có Tín hiệu model:** Mở dòng đầu tiên thỏa bộ lọc trong danh sách đang xem; nếu phạm vi chủ đề đang chọn không có dòng nào bị gắn cờ, bỏ riêng bộ lọc chủ đề rồi chọn dòng đầu tiên trong toàn bộ hàng chờ `"Có tín hiệu, chưa đối chiếu"` (nêu rõ thay đổi phạm vi). Nếu với ngưỡng hiện tại (`review-signals-v1`, chưa hiệu chuẩn) không có dòng nào bị gắn cờ, nói trung thực *"Với ngưỡng hiện tại, chưa có dòng bị đánh dấu"* rồi mở thủ công một câu pha trộn để minh họa.
4. **Chọn đoạn thử nghiệm độ nhạy:** Chọn một cụm từ có ý nghĩa rõ trên nội dung câu (không quét tự động để chọn lần có flip). Dù kết quả có đổi nhãn dẫn đầu hay điểm gần như giữ nguyên, đều đối chiếu bảng cùng nhãn (`before`, `after`, `delta`) và nêu rõ giới hạn thử nghiệm.
5. **Thao tác sửa nhãn thực (Human Review):** So sánh dự đoán model với tham chiếu đề xuất trong [`data/demo/README.md`](file:///f:/DPL_NEU-ESC/data/demo/README.md), chọn dòng bất đồng đầu tiên theo `source_row` mà người trình bày giải thích được (hoặc nếu model trùng toàn bộ, chọn một câu nhiều ý và nêu rõ *"Tôi minh họa việc người phụ trách chọn nhãn theo cách đọc này"*). Thực hiện sửa trạng thái sang `Tự chọn / sửa nhãn` kèm ghi chú thực tế để quan sát thống kê `Đã duyệt nếu có, còn lại AI` cập nhật.

---

## 2. Dữ liệu Rehearsal Thực tế (Đã đo ở T11 trên model thật)

- **Environment / Runtime cô lập:** `Windows-10-10.0.26200-SP0`, Python `3.10.11`, AMD64 (Ryzen 7 PRO 5850U: `8` nhân vật lý / `16` luồng), `30,83 GiB` RAM, CPU FP32 (`torch 2.14.1+cpu`, `num_threads=8`, `transformers 4.44.2`, `safetensors 0.8.0`, `underthesea 9.5.0`), `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`. Chạy hoàn toàn trên thư mục runtime tạm cô lập tại audit root (`...\real-model-runtime\rehearsal`), không chạm `runtime/` production.
- **Model & Policy Identity:**
  - Model: `neu-phobert-mtl-ed-s42` · version `neu-phobert-mtl-ed-s42-e10-617f852a3fff` (schema `neu-v1`, mode `cpu-fp32-eval`).
  - Checksums bundle copy bất biến khớp tuyệt đối: `manifest.json` `5117b413...`, `model.safetensors` `036b62c7...` (từ `demo/model.pt` `754892a7...`), `preprocessing_sha256` `27aa95d7...`, `current.json` `887bb18a...`.
  - Policy: `review-signals-v1` (hash `2d1cd5d7af32168af6c6ae30af6b1c43ba9f7c2f1cd6d73cc221067d1a1fc9a6`, `experimental=true`, ngưỡng thử nghiệm chưa hiệu chuẩn `top1_min=0,60`, `margin_min=0,15` cho cả Cảm xúc và Chủ đề).
- **Thời gian đo & bộ nhớ (Cold load vs Warm inference):**
  - Khởi động API + Worker tới `/api/v1/health` sẵn sàng: `1,195s`.
  - Cold batch `24` dòng (bao gồm worker lazy-load lần đầu PhoBERT + `underthesea` + commit SQLite): `7,584s` (worker RSS `1.206,2 MiB`, peak working set `1.642,9 MiB`, API RSS `4,3 MiB`).
  - Warm single Quick Analysis (`Thư viện mở cửa đến chín giờ tối.`): `0,559s` wall (`51,55 ms` inference).
  - Warm single Sensitivity pair (`D06`): `0,574s` wall (`42,89 ms` inference tính cả cặp).
- **Kết quả dự đoán & Tín hiệu trên 24 dòng (`three_layer_feedback_vi.csv`, giữ nguyên gốc):**
  - So với tham chiếu gợi ý trong [`data/demo/README.md`](file:///f:/DPL_NEU-ESC/data/demo/README.md): khớp `14/24` câu về Cảm xúc và `20/24` câu về Chủ đề (bất đồng đáng chú ý để minh họa trung thực giới hạn model: `D05` câu mỉa mai vẫn cho `Tích cực 0,9118` không bị gắn cờ; `D24` gán `Tiêu cực 0,9796` thay vì `Toxic` — phù hợp nhận xét paper về lớp hiếm `Toxic` 2,5%).
  - Tổng hợp cờ `review-signals-v1`: `5/24` dòng gắn cờ Cảm xúc (`D04, D06, D08, D14, D16`), `5/24` dòng gắn cờ Chủ đề (`D12, D13, D14, D20, D21`), hợp nhất **`9/24`** dòng trong hàng chờ `pending_signal_review`, `0/24` dòng bị cắt ngắn (`<= 18` token).
- **Top Topic Attention & Mẫu số (`effective` trước rà soát):**
  - Mẫu số: `24/24` dòng có đủ cả chủ đề và cảm xúc (`0` thiếu).
  - Hạng 1: **`Dịch vụ` (`topic_id=4`)** với **`4` Tiêu cực / `6` dòng đủ hai nhãn (`66,7%`), `0` Toxic, `small_sample=false`** (các câu Tiêu cực theo `source_row`: `D06, D08, D10, D22`).
  - Các nhóm sau: `Việc làm / tuyển dụng` (`1/3`, `Ít dữ liệu`), `Khác` (`1/1`, `Ít dữ liệu`), `Học tập` (`0/7`), `Câu lạc bộ / sự kiện` (`0/4`, `Ít dữ liệu`), `Tin tức` (`0/2`, `Ít dữ liệu`), `Hỏi đáp / chia sẻ` (`0/1`, `Ít dữ liệu`).
- **Item có Tín hiệu model được chọn (`scope_widened=false`):**
  - Trong bộ lọc `topic=4` (`Dịch vụ`) và `review_signal=pending_signal_review`, có 2 dòng `["D06", "D08"]`; chọn dòng đầu tiên **`D06`**: *"Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc."*
  - Tín hiệu cảm xúc: `flagged` (`LOW_TOP1`) — `Tiêu cực` `top1=0,5947`, `Trung tính` `top2=0,4010`, `margin=0,1937`.
  - Tín hiệu chủ đề: `clear` — `Dịch vụ` `top1=0,6982`, `Học tập` `top2=0,2410`, `margin=0,4572`.
- **Sensitivity Experiment thực tế (`D06`, chọn cụm định sẵn theo nội dung):**
  - Cụm bỏ: `"báo lỗi liên tục"` → biến thể: *"Cổng đăng ký học phần , mình chưa đăng ký được môn bắt buộc."* (`17 -> 14` token, `model_input_equal=false`, warnings `["SENSITIVITY_NOT_CAUSAL"]`).
  - Cảm xúc: đổi nhãn dẫn đầu `Tiêu cực (0,595) → Trung tính (0,988)` (`Tiêu cực -0,584`, `Trung tính +0,587`, `Tích cực 0,003 → 0,001 (-0,002)`, `Toxic 0,002 → 0,000 (-0,002)`).
  - Chủ đề: đổi nhãn dẫn đầu `Dịch vụ (0,698) → Học tập (0,732)` (`Dịch vụ -0,512`, `Học tập +0,492`).
  - *Cách diễn giải khi demo:* Việc bỏ cụm `"báo lỗi liên tục"` làm mất ý phản ánh sự cố kỹ thuật nên kết quả đổi cả hai đầu ra chỉ phản ánh độ nhạy đầu vào trên cùng model, không phải bằng chứng nhân quả hay giải thích từ vựng đơn lẻ.
- **Thao tác Human Review thực tế & Bản chụp Export CSV:**
  - Trong H2 rehearsal, sửa độc lập Cảm xúc trên **`D01`** (*"Giảng viên giải thích bài tập rõ ràng..."*, dòng bất đồng đầu tiên theo `source_row` với README): AI `Trung tính (0)` → người rà soát chọn `Tích cực (1)` kèm ghi chú; tác vụ Chủ đề giữ `unreviewed`, dự đoán AI gốc và giá trị số tín hiệu không đổi, `attention` chế độ `Chỉ dự đoán AI gốc` giữ nguyên hoàn toàn. *(Ghi chú bổ sung: trong bài test E2E model thật G3 `test_three_layer_real_model.py`, khi minh họa sự thay đổi số đếm `Tiêu cực` ở bảng Chủ đề cần chú ý từ `0 -> 1` trên `Học tập`, có thể chuyển sang sửa `D01` thành `Tiêu cực` hoặc chọn bất đồng tiếp theo `D02` sang `Tiêu cực` — khi thực hiện phải nêu rõ ý đồ minh họa).*
  - Bản chụp xuất CSV (`all`, `effective`): `export_id = 47baab40-cdf9-4be3-a747-90c8cbaa2d21`, `24` dòng, `19.705` bytes, SHA-256 `b8a9f68cf0bc1a1b3a4e7beb52c5e0b1571b7fea6aea3d5f9f0729f9d25b6270`.

---

## 3. Kịch bản Trình bày 3–5 phút (H3 — với model đã nạp ấm)

> [!IMPORTANT]
> Các mốc thời gian chỉ là bố cục lời dẫn khi model đã nạp sẵn từ bước rehearsal; nếu chạy batch live trên CPU chậm, chờ tiến độ thực tế và nêu rõ, không thay bằng kết quả giả. Khi mở từ run đã rehearsal trước, nêu rõ cho người xem và có thể chạy thêm một câu/batch khi cần chứng minh live.

| Khoảng thời gian gợi ý | Thao tác trên màn hình | Lời dẫn & điều phải thấy |
|---|---|---|
| `0:00–0:40` | Mở app local, nhập [`three_layer_feedback_vi.csv`](file:///f:/DPL_NEU-ESC/data/demo/three_layer_feedback_vi.csv), chọn hệ nhãn NEU, chạy phân tích | *"Đây là bộ 24 phản hồi minh họa do chúng tôi soạn. Mỗi dòng có một cảm xúc và một chủ đề."* Quan sát tiến độ thực từ worker. |
| `0:40–1:25` | Tab `Tổng quan` → bảng `Chủ đề cần chú ý` → bấm `Xem N phản hồi tiêu cực` của chủ đề đầu bảng | Nêu rõ số Tiêu cực, mẫu số hợp lệ, nguồn `"Đã duyệt nếu có, còn lại AI"`, nhãn `Ít dữ liệu` nếu `n < 5`, và `Toxic` tách riêng. *"Đây là số liệu của bộ phản hồi này theo bộ lọc hiện tại."* |
| `1:25–2:05` | Lọc `Tín hiệu model`, mở chi tiết một dòng, mở `Vì sao được đánh dấu?` | Chỉ ra `top1`, `top2`, `margin`, ngưỡng `review-signals-v1` (công bố *ngưỡng thử nghiệm, chưa hiệu chuẩn*) và cảnh báo cắt ngắn tách riêng nếu có. *"Tín hiệu giúp ưu tiên kiểm tra; điểm softmax không phải xác suất dự đoán đúng."* |
| `2:05–3:05` | Mở `Khám phá dự đoán`, nhập/chọn đúng một occurrence, xem preview `variant_text`, bấm `Chạy thử khi bỏ đoạn` | Đọc điểm trước/sau của **cùng một nhãn** trong bảng so sánh và thông điệp giới hạn cố định (*không phải bằng chứng nhân quả*). Dù nhãn giữ nguyên hay đổi đều giải thích trung thực theo kết quả thật. |
| `3:05–4:05` | Ở mục `Rà soát của bạn`, đổi nhãn một tác vụ (`Tự chọn / sửa nhãn`) kèm ghi chú, bấm `Lưu`, quay lại `Tổng quan` | Chỉ tác vụ được sửa thay đổi sang nhãn người duyệt; dự đoán AI gốc và giá trị số của tín hiệu không đổi; `pending_signal_review` và số liệu `Tổng quan` theo nguồn effective cập nhật. |
| `4:05–4:45` | Bấm `Xuất CSV`, chọn phạm vi (`Theo bộ lọc` hoặc `Toàn bộ`), tạo và tải snapshot | Nêu rõ các cột giữ riêng dự đoán AI, nhãn duyệt, nhãn hiệu lực; thử nghiệm độ nhạy không ghi đè dữ liệu nguồn. *"File xuất là bản chụp bất biến tại thời điểm tạo."* |
