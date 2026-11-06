import { useRef, useState } from "react";
import { api } from "./api";
import type { Dataset, Preview, Profile, Task } from "./types";
import { ErrorNotice, Loading } from "./ui";
type ReferenceDraft = {
  enabled: boolean;
  source: string;
  sentiment_column: string;
  topic_column: string;
  sentiment_map: Record<string, string>;
  topic_map: Record<string, string>;
};
export function ImportDataset({
  profiles,
  onCreated,
  onCancel,
}: {
  profiles: Profile[];
  onCreated: (d: Dataset) => void;
  onCancel: () => void;
}) {
  const [profileId, setProfileId] = useState(profiles[0]?.id ?? "");
  const profile = profiles.find((p) => p.id === profileId)!;
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"csv" | "paste">("csv");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [delimiter, setDelimiter] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [column, setColumn] = useState("");
  const [skip, setSkip] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [ref, setRef] = useState<ReferenceDraft>({
    enabled: false,
    source: "",
    sentiment_column: "",
    topic_column: "",
    sentiment_map: {},
    topic_map: {},
  });
  const idempotency = useRef({ body: "", key: "" });
  const lines = text.split(/\r?\n/).filter((t) => t.trim());
  const invalid = lines.filter((t) => t.length > 5000);
  const duplicate = lines.length - new Set(lines).size;
  const ignoredBlank = text
    ? text.split(/\r?\n/).filter((t) => !t.trim()).length
    : 0;
  const selectedIssues = (() => {
    if (!preview) return [];
    const seen = new Set<string>();
    return [
      ...preview.issues.filter(
        (i) => !["INVALID_TEXT", "DUPLICATE"].includes(i.code),
      ),
      ...preview.rows.flatMap((row, index) => {
        const value = row[column] ?? "";
        const issues = [];
        if (!value.trim())
          issues.push({
            row: index + 1,
            code: "INVALID_TEXT",
            message: "Cột văn bản đã chọn đang trống.",
          });
        else if (value.length > 5000)
          issues.push({
            row: index + 1,
            code: "INVALID_TEXT",
            message: "Cột văn bản đã chọn dài quá 5.000 ký tự.",
          });
        if (seen.has(value))
          issues.push({
            row: index + 1,
            code: "DUPLICATE",
            message: "Nội dung trùng trong cột đã chọn; vẫn được giữ khi nhập.",
          });
        seen.add(value);
        return issues;
      }),
    ];
  })();
  async function upload(nextFile: File | null, nextDelimiter = delimiter) {
    setFile(nextFile);
    setPreview(null);
    setError(null);
    setRef((r) => ({ ...r, enabled: false, sentiment_map: {}, topic_map: {} }));
    if (!nextFile) return;
    setBusy(true);
    try {
      const data = new FormData();
      data.append("file", nextFile);
      if (nextDelimiter) data.append("delimiter", nextDelimiter);
      const p = await api<Preview>("/imports/preview", {
        method: "POST",
        body: data,
      });
      setPreview(p);
      setColumn(p.columns.includes("text") ? "text" : (p.columns[0] ?? ""));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const refValid =
    !ref.enabled ||
    (ref.source.trim() &&
      (ref.sentiment_column || ref.topic_column) &&
      (["sentiment", "topic"] as Task[]).every((task) => {
        const c = ref[`${task}_column`];
        return (
          !c ||
          [
            ...new Set(
              preview?.rows.map((r) => r[c]).filter((v) => v !== undefined) ??
                [],
            ),
          ].every(
            (v) =>
              ref[`${task}_map`][v] !== undefined &&
              ref[`${task}_map`][v] !== "",
          )
        );
      }));
  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const reference = ref.enabled
        ? {
            source: ref.source.trim(),
            ...Object.fromEntries(
              (["sentiment", "topic"] as Task[])
                .filter((t) => ref[`${t}_column`])
                .flatMap((t) => [
                  [`${t}_column`, ref[`${t}_column`]],
                  [
                    `${t}_map`,
                    Object.fromEntries(
                      Object.entries(ref[`${t}_map`])
                        .filter(([, v]) => v !== "")
                        .map(([k, v]) => [k, Number(v)]),
                    ),
                  ],
                ]),
            ),
          }
        : undefined;
      const payload = {
        name: name.trim(),
        profile: profileId,
        skip_invalid: skip,
        ...(mode === "csv"
          ? { preview_id: preview?.preview_id, text_column: column, reference }
          : { items: lines.map((t) => ({ text: t })) }),
      };
      const body = JSON.stringify(payload);
      if (idempotency.current.body !== body)
        idempotency.current = { body, key: crypto.randomUUID() };
      const d = await api<Dataset>("/datasets", {
        method: "POST",
        headers: { "Idempotency-Key": idempotency.current.key },
        body,
      });
      onCreated(d);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <a href="#/" className="back-link">
            ← Bộ phản hồi
          </a>
          <h1>Tạo bộ phản hồi</h1>
          <p>Chọn hệ nhãn, nhập văn bản và kiểm tra trước khi lưu.</p>
        </div>
      </div>
      <form
        className="import-form"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <section className="section">
          <h2>Thông tin bộ phản hồi</h2>
          <div className="form-grid">
            <label>
              Tên bộ phản hồi
              <input
                autoFocus
                data-testid="dataset-name"
                required
                maxLength={160}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ví dụ: Góp ý sinh viên tháng 11"
              />
            </label>
            <label>
              Loại nội dung
              <select
                value={profileId}
                onChange={(e) => {
                  setProfileId(e.target.value);
                  setRef((r) => ({
                    ...r,
                    enabled: false,
                    sentiment_map: {},
                    topic_map: {},
                  }));
                }}
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted">
            {profile.description} Loại nội dung được giữ cố định sau khi tạo.
          </p>
          <details>
            <summary>Xem các nhãn của loại nội dung này</summary>
            <p>
              <strong>Cảm xúc:</strong>{" "}
              {profile.sentiment.map((l) => l.name).join(" · ")}
            </p>
            <p>
              <strong>Chủ đề:</strong>{" "}
              {profile.topic.map((l) => l.name).join(" · ")}
            </p>
          </details>
        </section>
        <section className="section">
          <h2>Nhập phản hồi</h2>
          <div className="tabs" role="tablist" aria-label="Cách nhập dữ liệu">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "csv"}
              onClick={() => setMode("csv")}
            >
              Tệp CSV
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "paste"}
              onClick={() => setMode("paste")}
            >
              Dán văn bản
            </button>
          </div>
          {mode === "csv" ? (
            <>
              <div className="upload-box">
                <label>
                  Tệp CSV UTF-8
                  <input
                    type="file"
                    accept=".csv,text/csv,text/plain"
                    data-testid="file-upload"
                    disabled={busy}
                    onChange={(e) => void upload(e.target.files?.[0] ?? null)}
                  />
                </label>
                <p>Tối đa 5 MB · 500 phản hồi · 5.000 ký tự mỗi phản hồi</p>
              </div>
              <div className="form-grid">
                <label>
                  Dấu phân cách
                  <select
                    value={delimiter}
                    disabled={busy}
                    onChange={(e) => {
                      setDelimiter(e.target.value);
                      if (file) void upload(file, e.target.value);
                    }}
                  >
                    <option value="">Tự nhận diện</option>
                    <option value=",">Dấu phẩy (,)</option>
                    <option value=";">Dấu chấm phẩy (;)</option>
                    <option value={"\t"}>Tab</option>
                    <option value="|">Dấu gạch đứng (|)</option>
                  </select>
                </label>
                {preview && (
                  <label>
                    Cột văn bản
                    <select
                      data-testid="text-column"
                      value={column}
                      onChange={(e) => {
                        setColumn(e.target.value);
                        setRef((r) => ({
                          ...r,
                          enabled: false,
                          sentiment_column: "",
                          topic_column: "",
                          sentiment_map: {},
                          topic_map: {},
                        }));
                      }}
                    >
                      {preview.columns.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              {busy && !preview && <Loading text="Đang đọc và kiểm tra CSV…" />}
              {preview && (
                <>
                  <div className="preview-heading">
                    <h3>Xem trước dữ liệu</h3>
                    <span>
                      {preview.total_rows} dòng · Dấu phân cách:{" "}
                      {preview.delimiter === "\t" ? "Tab" : preview.delimiter}
                    </span>
                  </div>
                  <div className="table-scroll preview-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Dòng</th>
                          {preview.columns.map((c) => (
                            <th
                              key={c}
                              className={c === column ? "selected-column" : ""}
                            >
                              {c}
                              {c === column ? " · Văn bản" : ""}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.rows.slice(0, 8).map((r, i) => (
                          <tr key={i}>
                            <td>{i + 1}</td>
                            {preview.columns.map((c) => (
                              <td
                                className={
                                  c === column ? "selected-column" : ""
                                }
                                key={c}
                              >
                                {r[c] || <span className="muted">Trống</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted small">
                    Hiện tối đa 8 dòng xem trước. Kiểm tra cột văn bản và dấu
                    tiếng Việt trước khi nhập. Phiên xem trước hết hạn lúc{" "}
                    {new Date(preview.expires_at).toLocaleTimeString("vi-VN")}.
                  </p>
                  {selectedIssues.length > 0 && (
                    <div className="notice warning">
                      <strong>
                        {selectedIssues.length} vấn đề cần kiểm tra
                      </strong>
                      <ul>
                        {selectedIssues.slice(0, 12).map((issue, i) => (
                          <li key={i}>
                            Dòng {issue.row}: {issue.message} ({issue.code})
                          </li>
                        ))}
                      </ul>
                      <p>Dòng trùng là cảnh báo và vẫn được giữ lại.</p>
                    </div>
                  )}
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={skip}
                      onChange={(e) => setSkip(e.target.checked)}
                    />
                    Bỏ qua các dòng lỗi (trống, quá dài hoặc sai số cột) khi
                    nhập
                  </label>
                  <details className="reference-settings">
                    <summary>Nhãn tham chiếu từ CSV (tùy chọn)</summary>
                    <p>
                      Chỉ bật khi biết rõ nguồn nhãn. Cùng một mã số có thể mang
                      ý nghĩa khác ở hệ nhãn khác.
                    </p>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={ref.enabled}
                        onChange={(e) =>
                          setRef({ ...ref, enabled: e.target.checked })
                        }
                      />
                      Tôi xác nhận nguồn và sẽ ánh xạ nhãn tham chiếu
                    </label>
                    {ref.enabled && (
                      <>
                        <label>
                          Nguồn nhãn tham chiếu
                          <input
                            required
                            value={ref.source}
                            onChange={(e) =>
                              setRef({ ...ref, source: e.target.value })
                            }
                            placeholder="Ví dụ: người gán nhãn, tên tập dữ liệu"
                          />
                        </label>
                        {(["sentiment", "topic"] as Task[]).map((task) => (
                          <div key={task} className="reference-task">
                            <label>
                              Cột {task === "sentiment" ? "cảm xúc" : "chủ đề"}{" "}
                              tham chiếu
                              <select
                                value={ref[`${task}_column`]}
                                onChange={(e) =>
                                  setRef({
                                    ...ref,
                                    [`${task}_column`]: e.target.value,
                                    [`${task}_map`]: {},
                                  })
                                }
                              >
                                <option value="">Không dùng</option>
                                {preview.columns
                                  .filter((c) => c !== column)
                                  .map((c) => (
                                    <option key={c}>{c}</option>
                                  ))}
                              </select>
                            </label>
                            {ref[`${task}_column`] &&
                              [
                                ...new Set(
                                  preview.rows
                                    .map((r) => r[ref[`${task}_column`]])
                                    .filter((v) => v !== undefined),
                                ),
                              ].map((v) => (
                                <label className="mapping-row" key={v}>
                                  <span>“{v || "(trống)"}” →</span>
                                  <select
                                    required
                                    aria-label={`Ánh xạ ${task} ${v}`}
                                    value={ref[`${task}_map`][v] ?? ""}
                                    onChange={(e) =>
                                      setRef({
                                        ...ref,
                                        [`${task}_map`]: {
                                          ...ref[`${task}_map`],
                                          [v]: e.target.value,
                                        },
                                      })
                                    }
                                  >
                                    <option value="">Chọn nhãn</option>
                                    {profile[task].map((l) => (
                                      <option key={l.id} value={l.id}>
                                        {l.name}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                              ))}
                          </div>
                        ))}
                        <p className="muted small">
                          Nếu CSV còn giá trị chưa được ánh xạ ngoài phần xem
                          trước, hệ thống sẽ báo lỗi để bạn sửa file. Các cột
                          khác được giữ làm metadata.
                        </p>
                      </>
                    )}
                  </details>
                </>
              )}
            </>
          ) : (
            <>
              <label>
                Văn bản phản hồi
                <textarea
                  data-testid="paste-input"
                  rows={9}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Mỗi dòng là một phản hồi…"
                />
              </label>
              <div className="preview-heading">
                <span>
                  {lines.length} phản hồi không trống · {ignoredBlank} dòng
                  trống được bỏ qua
                </span>
                <span className="muted">
                  {duplicate
                    ? `${duplicate} dòng trùng được giữ lại`
                    : "Mỗi dòng không trống là một phản hồi"}
                </span>
              </div>
              {invalid.length > 0 && (
                <div className="notice warning">
                  {invalid.length} dòng dài quá 5.000 ký tự.
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={skip}
                      onChange={(e) => setSkip(e.target.checked)}
                    />
                    Bỏ qua dòng quá dài khi nhập
                  </label>
                </div>
              )}
              {lines.length > 500 && (
                <div className="notice error" role="alert">
                  Bộ phản hồi vượt giới hạn 500 dòng. Hãy chia thành các bộ nhỏ
                  hơn.
                </div>
              )}
              <p className="muted small">
                Để giữ nhiều dòng trong cùng một phản hồi, hãy dùng CSV có ô
                được đặt trong dấu ngoặc kép.
              </p>
            </>
          )}
          {error != null && <ErrorNotice error={error} />}
        </section>
        <div className="form-footer">
          <p>
            Chỉ lưu dữ liệu ở bước này. Phân tích AI được bắt đầu trong bộ phản
            hồi.
          </p>
          <div className="inline-actions">
            <button type="button" onClick={onCancel} disabled={busy}>
              Hủy
            </button>
            <button
              className="primary"
              data-testid="import-confirm"
              disabled={
                busy ||
                !name.trim() ||
                !profileId ||
                (mode === "csv"
                  ? !preview ||
                    !column ||
                    !refValid ||
                    (selectedIssues.some((i) => i.code !== "DUPLICATE") &&
                      !skip)
                  : !lines.length ||
                    lines.length > 500 ||
                    (invalid.length > 0 && !skip))
              }
            >
              {busy ? "Đang nhập…" : "Nhập dữ liệu"}
            </button>
          </div>
        </div>
      </form>
    </>
  );
}
