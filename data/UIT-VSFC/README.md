# UIT-VSFC (dataset thứ hai, kiểm tra tổng quát hoá)

UIT-VSFC — Vietnamese Students' Feedback Corpus (Nguyen et al., KSE 2018). Dùng split train/dev/test
chính thức, không chia lại. Các CSV ở đây có cùng layout với NEU-ESC (`text,sentiment,classification`)
nên runner `src_improvement/neu_esc_improvement.py --dataset vsfc` đọc được mà không cần đổi code huấn luyện.

## Nguồn

File gốc là 9 file `.txt` (câu / nhãn sentiment / nhãn topic cho mỗi split) trên Google Drive của UIT-NLP,
đúng các file mà loader HuggingFace `uitnlp/vietnamese_students_feedback` (revision `7b56c6cb`) tải về:

| Split | sentences | sentiments | topics |
|---|---|---|---|
| train | `1nzak5OkrheRV1ltOGCXkT671bmjODLhP` | `1ye-gOZIBqXdKOoi_YxvpT6FeRNmViPPv` | `14MuDtwMnNOcr4z_8KdpxprjbwaQ7lJ_C` |
| dev → `val` | `1sMJSR3oRfPc3fe1gK-V3W5F24tov_517` | `1GiY1AOp41dLXIIkgES4422AuDwmbUseL` | `1DwLgDEaFWQe8mOd7EpF-xqMEbDLfdT-W` |
| test | `1aNMOeZZbNwSRkjyCWAGtNCMa3YrshR-n` | `1vkQS5gI0is4ACU58-AbWusnemw7KZNfO` | `1_ArMpDguVsbUGl-xSMkTF_p5KpZrmpSB` |

(URL: `https://drive.google.com/uc?id=<id>&export=download`.)

## Nhãn

- `sentiment`: 0 negative, 1 neutral, 2 positive.
- `classification` (topic): 0 lecturer, 1 training_program, 2 facility, 3 others.

| Split | Số câu | Sentiment [neg, neu, pos] | Topic [lec, prog, fac, oth] |
|---|---:|---|---|
| train | 11.426 | 5325 / 458 / 5643 | 8166 / 2201 / 497 / 562 |
| val | 1.583 | 705 / 73 / 805 | 1151 / 267 / 70 / 95 |
| test | 3.166 | 1409 / 167 / 1590 | 2290 / 572 / 145 / 159 |

Tổng 16.175 câu, khớp với bài gốc. Bài gốc ghi dev có 1.538 câu, nhưng con số này là lỗi đánh máy:
file dev có 1.583 dòng, và 11.426 + 1.583 + 3.166 = 16.175. Lớp Neutral chỉ chiếm khoảng 4–5% mỗi split.

## Cách tạo

- `{split}_set.csv`: câu gốc (đã `strip()`), giữ nguyên thứ tự dòng, ghi bằng pandas với `lineterminator="\n"`.
- `{split}_set_processed.csv`: cùng nội dung nhưng `text` được tách từ bằng **underthesea 9.5.0**
  (`word_tokenize(text, format="text")`, nối âm tiết bằng `_`), dùng cho PhoBERT. ViSoBERT đọc bản không tách.
  Tác giả NEU-ESC không công bố công cụ tách từ của họ, và máy nhóm không có Java để chạy VnCoreNLP,
  nên đây là một khác biệt có chủ đích so với tiền xử lý PhoBERT chuẩn.

```python
import pandas as pd
from underthesea import word_tokenize   # 9.5.0
R = "<thư mục chứa 9 file .txt>"
for split, name in (("train", "train"), ("dev", "val"), ("test", "test")):
    read = lambda k: open(f"{R}/{split}_{k}.txt", encoding="utf-8").read().split("\n")
    sents, sen, top = read("sents"), read("sentiments"), read("topics")
    n = len([x for x in sen if x.strip()])
    df = pd.DataFrame({"text": [x.strip() for x in sents[:n]],
                       "sentiment": [int(x) for x in sen[:n]],
                       "classification": [int(x) for x in top[:n]]})
    df.to_csv(f"{name}_set.csv", index=False, lineterminator="\n")
    df["text"] = [word_tokenize(t, format="text") for t in df.text]
    df.to_csv(f"{name}_set_processed.csv", index=False, lineterminator="\n")
```

## SHA-256

Runner kiểm tra các hash này trong `fetch --dataset vsfc` (bảng `DATASETS["vsfc"]`):

```
3d636af567e2ddc2c0aa3f93b7a87755526974a57a070ff15b8fa9512bdbbf50  train_set.csv
a5e07e9d95e0b2fa08c033a49d80ca22b2a40e7a122539e92b3674636e0eb801  val_set.csv
b3e7a59945d7ca49f135bb857ab01c4ffb5c7c0d73db825ae5a05fed9cc7beb5  test_set.csv
9b96dca185a8a54e2073a84762054f0e619e514292adee3b447a687c7af1db5c  train_set_processed.csv
e9431f5d3cb577270062816950fd07e611f80f8d6ed53c34205b4c55664730b3  val_set_processed.csv
7439de60438951aa9db58ee379d315840c386d070ee259502116c65b1c5c7163  test_set_processed.csv
```

Trên Windows, git có thể đổi line ending khi checkout và làm lệch hash; khi đó hãy tắt `core.autocrlf`
cho thư mục này hoặc tạo lại CSV bằng đoạn code trên.
