import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, post } from "./api";
import type { Dataset, Item, Job, Prediction, Profile, Task } from "./types";
import { activeJob, labelName } from "./types";
import { Badge, ErrorNotice, Modal } from "./ui";
import type { Notify } from "./App";
export function QuickAnalysis({
  profiles,
  datasets,
  onClose,
  notify,
}: {
  profiles: Profile[];
  datasets: Dataset[];
  onClose: () => void;
  notify: Notify;
}) {
  const client = useQueryClient();
  const [profileId, setProfileId] = useState(profiles[0]?.id ?? "");
  const profile = profiles.find((p) => p.id === profileId)!;
  const [text, setText] = useState("");
  const [submittedText, setSubmittedText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("");
  const [added, setAdded] = useState(false);
  const job = useQuery({
    queryKey: ["quick-job", jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) =>
      !q.state.data || activeJob(q.state.data.status) ? 1000 : false,
  });
  const result = job.data?.result;
  const prediction = result
    ? "prediction" in result
      ? (result as Item).prediction
      : (result as Prediction)
    : null;
  const running = !!jobId && (!job.data || activeJob(job.data.status));
  async function analyze() {
    setBusy(true);
    setError(null);
    setJobId(null);
    setAdded(false);
    try {
      const response = await post<{ job_id: string; run_id: string }>(
        "/quick-analysis",
        { profile: profileId, text },
      );
      setSubmittedText(text);
      setJobId(response.job_id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function add() {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      await post(`/datasets/${target}/items`, {
        items: [{ text: submittedText }],
      });
      await client.invalidateQueries({ queryKey: ["datasets"] });
      await client.invalidateQueries({ queryKey: ["items", target] });
      await client.invalidateQueries({ queryKey: ["summary", target] });
      setAdded(true);
      notify(
        "Đã thêm câu vào bộ phản hồi. Chạy phân tích trong bộ đó để lưu kết quả gắn với phiên bản mới.",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Thử một câu" onClose={onClose} wide>
      <p className="muted">
        Thử dự đoán thật qua cùng worker phân tích. Văn bản được lưu tạm và dọn
        sau 15 phút kể từ khi tác vụ kết thúc.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void analyze();
        }}
      >
        <label>
          Loại nội dung
          <select
            value={profileId}
            disabled={running || busy}
            onChange={(e) => {
              setProfileId(e.target.value);
              setJobId(null);
              setTarget("");
              setError(null);
            }}
          >
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Văn bản cần thử
          <textarea
            data-testid="quick-input"
            maxLength={5000}
            rows={4}
            required
            value={text}
            disabled={running || busy}
            onChange={(e) => {
              setText(e.target.value);
              setJobId(null);
              setAdded(false);
            }}
            placeholder="Nhập một phản hồi tiếng Việt…"
          />
        </label>
        {profile.model.available &&
          profile.model.preprocessing?.equivalence === "approximate" && (
            <div className="notice small">
              <span>
                Văn bản được tách từ trước khi phân tích. Kết quả trên dữ liệu
                bạn nhập có thể khác benchmark nghiên cứu.
              </span>
              <details>
                <summary>Chi tiết kỹ thuật</summary>
                <p className="technical-reason small">
                  Model: {profile.model.model_id} ({profile.model.backbone ?? "PhoBERT"} ·{" "}
                  {profile.model.setup ?? "mtl_ed"}). Tách từ nội bộ bằng
                  underthesea 9.5.0 trước khi mã hóa tối đa 128 token; văn bản
                  gốc được giữ nguyên.
                </p>
              </details>
            </div>
          )}
        {!profile.model.available && (
          <div className="notice warning">
            <strong>Model chưa sẵn sàng</strong>
            <span>Cần cài bộ model hợp lệ cho loại nội dung này.</span>
            <a href="#/help" onClick={onClose}>
              Xem hướng dẫn
            </a>
            {profile.model.reason && (
              <details>
                <summary>Chi tiết kỹ thuật</summary>
                <p className="technical-reason small">{profile.model.reason}</p>
              </details>
            )}
          </div>
        )}
        <div className="dialog-actions">
          <span className="muted small">{text.length}/5.000 ký tự</span>
          <button
            className="primary"
            data-testid="quick-analyze"
            disabled={
              !text.trim() || busy || running || !profile.model.available
            }
          >
            {busy ? "Đang gửi…" : running ? "Đang phân tích…" : "Phân tích câu"}
          </button>
        </div>
      </form>
      {error != null && <ErrorNotice error={error} />}{" "}
      {job.isError && (
        <ErrorNotice error={job.error} retry={() => void job.refetch()} />
      )}{" "}
      {running && (
        <div className="notice" role="status">
          {job.data?.status === "loading_model"
            ? "Đang nạp model…"
            : job.data?.status === "running"
              ? "Đang phân tích…"
              : "Đang chờ worker…"}{" "}
          Mã tác vụ: {jobId?.slice(0, 8)}
          <button
            disabled={job.data?.cancel_requested}
            onClick={async () => {
              try {
                await post(`/jobs/${jobId}/cancel`, {});
                await job.refetch();
              } catch (e) {
                setError(e);
              }
            }}
          >
            Hủy phân tích
          </button>
        </div>
      )}
      {job.data && !activeJob(job.data.status) && !prediction && (
        <div className="notice warning" role="status">
          {job.data.status === "cancelled"
            ? "Đã hủy phân tích."
            : job.data.error || "Tác vụ kết thúc nhưng chưa có kết quả."}
          <button
            disabled={busy || !profile.model.available}
            onClick={async () => {
              try {
                await post(`/jobs/${jobId}/retry`, {});
                await job.refetch();
              } catch (e) {
                setError(e);
              }
            }}
          >
            Chạy lại tác vụ này
          </button>
        </div>
      )}
      {prediction && (
        <section className="quick-result">
          <h3>Kết quả AI</h3>
          <dl className="prediction-labels">
            {(["sentiment", "topic"] as Task[]).map((task) => (
              <div key={task}>
                <dt>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</dt>
                <dd>{labelName(profile, task, prediction[task].label_id)}</dd>
              </div>
            ))}
          </dl>
          {prediction.truncated && (
            <div className="notice warning">
              Model đã cắt ngắn đầu vào. Kết quả chỉ dựa trên phần văn bản model
              đã đọc.
            </div>
          )}
          <details>
            <summary>Điểm mô hình</summary>
            <p className="muted small">
              Điểm softmax chưa hiệu chuẩn, không phải xác suất dự đoán đúng.
              {profile.id === "neu" &&
                " Nhãn Ngôn từ độc hại (Toxic) chỉ dùng hỗ trợ rà soát, không tự động kết luận về người viết."}
            </p>
            {(["sentiment", "topic"] as Task[]).map((task) => (
              <div className="score-group" key={task}>
                <h4>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</h4>
                {profile[task].map((l, i) => (
                  <div className="score-row" key={l.id}>
                    <span>{l.name}</span>
                    <progress value={prediction[task].scores[i] ?? 0} max={1} />
                    <span>
                      {((prediction[task].scores[i] ?? 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </details>
          <p className="small muted">
            {prediction.model_id} · {prediction.model_version}
          </p>
          <div className="quick-add">
            <label>
              Lưu câu vào bộ phản hồi cùng hệ nhãn
              <select
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  setAdded(false);
                }}
              >
                <option value="">Chọn bộ phản hồi</option>
                {datasets
                  .filter((d) => d.profile === profileId)
                  .map((d) => (
                    <option value={d.id} key={d.id}>
                      {d.name}
                    </option>
                  ))}
              </select>
            </label>
            <button
              disabled={!target || busy || added}
              onClick={() => void add()}
            >
              {added ? "Đã thêm câu" : "Thêm câu vào bộ"}
            </button>
            {!datasets.some((d) => d.profile === profileId) && (
              <p className="muted small">
                Tạo bộ phản hồi cùng loại nội dung để lưu câu này.
              </p>
            )}
            {added && <Badge tone="success">Đã lưu văn bản</Badge>}
          </div>
        </section>
      )}
    </Modal>
  );
}
