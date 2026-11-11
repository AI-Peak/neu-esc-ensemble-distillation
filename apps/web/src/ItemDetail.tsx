import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, post } from "./api";
import type {
  Item,
  Profile,
  Review,
  ReviewPolicy,
  ReviewRelation,
  Task,
  TaskReviewSignal,
} from "./types";
import { date, labelName } from "./types";
import type { Notify } from "./App";
import { Badge, ErrorNotice, Loading, useDialogFocus } from "./ui";
import { SensitivityPanel } from "./SensitivityPanel";
type Props = {
  itemId: string;
  profile: Profile;
  runId: string;
  onClose: () => void;
  onNext: () => void;
  notify: Notify;
};
type ReviewDraft = {
  status: Review["status"];
  label_id: string;
  note: string;
  source_prediction_id: string | null;
  base_revision: number;
  base_revision_id: string;
  base_input_revision: number;
  base_text: string;
  dirty: boolean;
};
const taskName = (task: Task) =>
  task === "sentiment" ? "cảm xúc" : "chủ đề";
const signalReasonText = (reason: string) => {
  if (reason === "LOW_TOP1") return "Điểm cao nhất dưới ngưỡng";
  if (reason === "SMALL_MARGIN") return "Khoảng cách hai nhãn đầu nhỏ";
  if (reason === "NO_PREDICTION") return "Chưa có dự đoán AI";
  if (reason === "INVALID_SCORES") {
    return "Điểm mô hình không hợp lệ hoặc không đầy đủ";
  }
  return reason;
};
const reviewRelationText = (relation: ReviewRelation | undefined) => {
  if (relation === "current_prediction") {
    return "Đã đối chiếu tín hiệu của dự đoán này";
  }
  if (relation === "manual") {
    return "Nhãn tự chọn (không gắn một lần chạy cụ thể)";
  }
  if (relation === "other_prediction") {
    return "Đã duyệt ở dự đoán khác";
  }
  return "Chưa rà soát tác vụ này";
};
const formatThreshold = (value: number | undefined) => {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.abs(value * 100 - Math.round(value * 100)) < 1e-9
    ? value.toFixed(2)
    : String(value);
};
const formatScore = (value: number | null | undefined) =>
  value != null && Number.isFinite(value) ? value.toFixed(3) : "—";
const draftFromReview = (
  review: Review | null,
  item: Item,
): ReviewDraft => ({
  status: review?.status ?? "unreviewed",
  label_id: review?.label_id == null ? "" : String(review.label_id),
  note: review?.note ?? "",
  source_prediction_id: review?.source_prediction_id ?? null,
  base_revision: review?.revision ?? 0,
  base_revision_id: item.revision_id,
  base_input_revision: item.revision,
  base_text: item.text,
  dirty: false,
});
export function ItemDetail(props: Props) {
  const { itemId, runId, onClose } = props;
  const ref = useDialogFocus();
  const item = useQuery({
    queryKey: ["item", itemId, runId],
    queryFn: () =>
      api<Item>(
        `/items/${itemId}${runId ? `?run_id=${encodeURIComponent(runId)}` : ""}`,
      ),
  });
  return (
    <dialog
      ref={ref}
      className="detail-panel"
      aria-labelledby="detail-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <div>
          <span className="muted small">Chi tiết phản hồi</span>
          <h2 id="detail-title">
            {item.data ? `Dòng ${item.data.source_row}` : "Đang tải phản hồi"}
          </h2>
        </div>
        <button
          className="icon-button"
          aria-label="Đóng chi tiết"
          onClick={onClose}
        >
          ×
        </button>
      </header>
      {item.isPending ? (
        <Loading />
      ) : !item.data ? (
        <ErrorNotice error={item.error} retry={() => void item.refetch()} />
      ) : (
        <DetailContent
          key={`${item.data.id}::${runId}`}
          {...props}
          item={item.data}
          syncError={item.isError ? item.error : null}
          onRetrySync={() => {
            void item.refetch();
          }}
        />
      )}
    </dialog>
  );
}
function DetailContent({
  item,
  profile,
  runId,
  onNext,
  notify,
  syncError,
  onRetrySync,
}: {
  item: Item;
  profile: Profile;
  runId: string;
  onNext: () => void;
  notify: Notify;
  syncError: unknown;
  onRetrySync: () => void;
}) {
  const client = useQueryClient();
  const tasks: Task[] = ["sentiment", "topic"];
  const [drafts, setDrafts] = useState<Record<Task, ReviewDraft>>({
    sentiment: draftFromReview(item.reviews.sentiment, item),
    topic: draftFromReview(item.reviews.topic, item),
  });
  const [reviewConflicts, setReviewConflicts] = useState<Record<Task, boolean>>({
    sentiment: false,
    topic: false,
  });
  const [staleSourceRevisions, setStaleSourceRevisions] = useState<
    Record<string, true>
  >({});
  const prevRevisionIdRef = useRef(item.revision_id);
  // A background refetch may refresh untouched tasks, but never rebase a dirty draft.
  // When the source revision changes, reset untouched tasks cleanly while preserving dirty drafts
  // on their original base input revision/text until the user explicitly compares and resolves.
  useEffect(() => {
    const revisionChanged = prevRevisionIdRef.current !== item.revision_id;
    prevRevisionIdRef.current = item.revision_id;
    setDrafts((current) => {
      let next = current;
      for (const task of ["sentiment", "topic"] as const) {
        if (current[task].base_revision_id !== item.revision_id) {
          if (!current[task].dirty) {
            next = {
              ...next,
              [task]: draftFromReview(item.reviews[task], item),
            };
          }
        } else if (
          !current[task].dirty &&
          (item.reviews[task]?.revision ?? 0) !== current[task].base_revision
        ) {
          next = {
            ...next,
            [task]: draftFromReview(item.reviews[task], item),
          };
        }
      }
      return next;
    });
    if (revisionChanged) {
      setEditing(false);
      setText(item.text);
      setUndo(null);
      setReviewConflicts({ sentiment: false, topic: false });
    }
  }, [item.revision_id, item.text, item.reviews]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(item.text);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [revisionOpen, setRevisionOpen] = useState(false);
  const [undo, setUndo] = useState<{
    task: Task;
    previous: Review | null;
  } | null>(null);
  const history = useQuery({
    queryKey: ["reviews", item.id],
    queryFn: () => api<Review[]>(`/items/${item.id}/reviews`),
    enabled: historyOpen,
  });
  const revisions = useQuery({
    queryKey: ["revisions", item.id],
    queryFn: () =>
      api<
        {
          revision_id: string;
          revision: number;
          text: string;
          metadata: Record<string, unknown>;
          created_at: string;
        }[]
      >(`/items/${item.id}/revisions`),
    enabled: revisionOpen,
  });
  const policy = useQuery({
    queryKey: [
      "review-policy",
      profile.id,
      item.review_signals?.policy_hash ?? "current",
    ],
    queryFn: () =>
      api<ReviewPolicy>(
        `/review-policy?profile=${encodeURIComponent(profile.id)}`,
      ),
    staleTime: Infinity,
  });
  function change(task: Task, patch: Partial<ReviewDraft>) {
    setDrafts((d) => ({
      ...d,
      [task]: {
        ...d[task],
        ...patch,
        dirty: true,
      },
    }));
  }
  const hasInputRevisionConflict = (task: Task) => {
    const draft = drafts[task];
    if (!draft.dirty) return false;
    return (
      draft.base_revision_id !== item.revision_id ||
      Boolean(staleSourceRevisions[draft.base_revision_id])
    );
  };
  const hasNewInputSnapshot = (task: Task) =>
    drafts[task].base_revision_id !== item.revision_id;
  const hasReviewConflict = (task: Task) => {
    const draft = drafts[task];
    if (!draft.dirty || hasInputRevisionConflict(task)) return false;
    return (
      reviewConflicts[task] ||
      (item.reviews[task]?.revision ?? 0) !== draft.base_revision
    );
  };
  const hasNewReviewSnapshot = (task: Task) =>
    (item.reviews[task]?.revision ?? 0) !== drafts[task].base_revision;
  const hasConflict = (task: Task) =>
    hasInputRevisionConflict(task) || hasReviewConflict(task);
  function resolveConflict(task: Task, keepDraft: boolean) {
    const inputConflict = hasInputRevisionConflict(task);
    if (inputConflict && !hasNewInputSnapshot(task)) return;
    if (!inputConflict && hasReviewConflict(task) && !hasNewReviewSnapshot(task)) {
      return;
    }
    const remainingConflict = tasks.some(
      (t) => t !== task && hasConflict(t),
    );
    setDrafts((d) => ({
      ...d,
      [task]: keepDraft
        ? {
            ...d[task],
            status:
              inputConflict && d[task].status === "confirmed"
                ? "corrected"
                : d[task].status,
            label_id:
              inputConflict && d[task].status === "unreviewed"
                ? ""
                : d[task].label_id,
            source_prediction_id: inputConflict
              ? null
              : d[task].source_prediction_id,
            base_revision: item.reviews[task]?.revision ?? 0,
            base_revision_id: item.revision_id,
            base_input_revision: item.revision,
            base_text: item.text,
            dirty: true,
          }
        : draftFromReview(item.reviews[task], item),
    }));
    setReviewConflicts((c) => ({ ...c, [task]: false }));
    if (!remainingConflict) {
      setError(null);
    }
  }
  function confirmDisplayed(task: Task) {
    if (item.stale || hasConflict(task)) return;
    const labelId = item.prediction?.[task]?.label_id;
    if (labelId == null) return;
    change(task, {
      status: "confirmed",
      label_id: String(labelId),
      source_prediction_id: item.prediction?.id ?? null,
    });
  }
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["item", item.id] }),
      client.invalidateQueries({ queryKey: ["items", item.dataset_id] }),
      client.invalidateQueries({ queryKey: ["summary", item.dataset_id] }),
      client.invalidateQueries({ queryKey: ["reviews", item.id] }),
      client.invalidateQueries({ queryKey: ["datasets"] }),
    ]);
  }
  async function saveReview(task: Task) {
    const draft = drafts[task];
    if (item.stale || hasConflict(task)) return;
    const sentRevisionId = draft.base_revision_id;
    let saved: Review;
    try {
      saved = await api<Review>(`/items/${item.id}/review`, {
        method: "PUT",
        body: JSON.stringify({
          task,
          status: draft.status,
          label_id: draft.status === "unreviewed" ? null : Number(draft.label_id),
          source_prediction_id: draft.source_prediction_id,
          note: draft.note,
          expected_revision: draft.base_input_revision,
          expected_review_revision: draft.base_revision,
          ...(runId ? { run_id: runId } : {}),
        }),
      });
    } catch (e) {
      if (e instanceof ApiError && e.code === "REVIEW_CONFLICT") {
        setReviewConflicts((c) => ({ ...c, [task]: true }));
      } else if (e instanceof ApiError && e.code === "REVISION_CONFLICT") {
        setStaleSourceRevisions((s) => ({ ...s, [sentRevisionId]: true }));
      }
      throw e;
    }
    setUndo({ task, previous: item.reviews[task] });
    setDrafts((d) => ({
      ...d,
      [task]: draftFromReview(saved, {
        ...item,
        revision_id: saved.revision_id ?? sentRevisionId,
        revision: draft.base_input_revision,
        text: draft.base_text,
      }),
    }));
    return saved;
  }
  const valid = (task: Task) =>
    drafts[task].status === "unreviewed" || drafts[task].label_id !== "";
  async function save(task?: Task, next = false) {
    if (item.stale) return;
    const toSave = task ? [task] : tasks.filter((t) => drafts[t].dirty);
    if (toSave.some(hasConflict)) return;
    if (!task && tasks.some((t) => !valid(t) || hasConflict(t))) return;
    if (toSave.some((t) => !valid(t))) return;
    setBusy(true);
    setError(null);
    try {
      if (!toSave.length) {
        if (next) {
          onNext();
          return;
        }
        return;
      }
      for (const t of toSave) await saveReview(t);
      await refresh();
      notify(
        task
          ? `Đã lưu rà soát ${task === "sentiment" ? "cảm xúc" : "chủ đề"}.`
          : "Đã lưu các nhãn đã thay đổi.",
      );
      if (next) onNext();
    } catch (e) {
      setError(e);
      await refresh();
    } finally {
      setBusy(false);
    }
  }
  async function undoReview() {
    if (!undo) return;
    setBusy(true);
    setError(null);
    try {
      let restored: Review;
      if (undo.previous)
        restored = await post<Review>(`/items/${item.id}/reviews/restore`, {
          task: undo.task,
          review_revision: undo.previous.revision,
          revision_id: item.revision_id,
          expected_revision: item.revision,
          expected_review_revision: item.reviews[undo.task]?.revision ?? 0,
        });
      else
        restored = await api<Review>(`/items/${item.id}/review`, {
          method: "PUT",
          body: JSON.stringify({
            task: undo.task,
            status: "unreviewed",
            label_id: null,
            note: "",
            expected_revision: item.revision,
            expected_review_revision: item.reviews[undo.task]?.revision ?? 0,
          }),
        });
      setUndo(null);
      await refresh();
      setDrafts((d) => ({
        ...d,
        [undo.task]: draftFromReview(restored, {
          ...item,
          revision_id: restored.revision_id ?? item.revision_id,
        }),
      }));
      setReviewConflicts((c) => ({ ...c, [undo.task]: false }));
      notify("Đã hoàn tác bằng một phiên bản rà soát mới.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function restore(review: Review) {
    if (!review.task) return;
    setBusy(true);
    setError(null);
    try {
      const restored = await post<Review>(`/items/${item.id}/reviews/restore`, {
        task: review.task,
        review_revision: review.revision,
        revision_id: review.revision_id,
        expected_revision: item.revision,
        expected_review_revision: item.reviews[review.task]?.revision ?? 0,
      });
      setDrafts((d) => ({
        ...d,
        [review.task!]: draftFromReview(restored, {
          ...item,
          revision_id: restored.revision_id ?? item.revision_id,
        }),
      }));
      setReviewConflicts((c) => ({ ...c, [review.task!]: false }));
      await refresh();
      notify("Đã khôi phục nhãn bằng phiên bản mới.");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function saveText() {
    setBusy(true);
    setError(null);
    try {
      await api<Item>(`/items/${item.id}/text`, {
        method: "PATCH",
        body: JSON.stringify({ text, expected_revision: item.revision }),
      });
      setEditing(false);
      await refresh();
      await client.invalidateQueries({ queryKey: ["revisions", item.id] });
      notify(
        runId
          ? "Đã lưu văn bản mới. Chọn “Văn bản hiện tại” trong bộ phản hồi để xem và rà soát bản mới."
          : "Đã lưu phiên bản văn bản mới. Cần phân tích hoặc rà soát lại phiên bản này.",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="detail-content">
      <section>
        <div className="section-heading">
          <h3>Văn bản gốc</h3>
          <span className="muted small">Phiên bản {item.revision}</span>
        </div>
        {item.stale && (
          <div className="notice warning">
            Văn bản đã thay đổi sau lần phân tích này. Dự đoán bên dưới thuộc
            phiên bản cũ. Đóng bảng và chọn “Văn bản hiện tại” để rà soát bản
            mới.
          </div>
        )}
        {editing ? (
          <>
            <label className="sr-only" htmlFor="edit-text">
              Sửa văn bản phản hồi
            </label>
            <textarea
              id="edit-text"
              rows={7}
              maxLength={5000}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="notice small">
              Lưu sẽ tạo phiên bản mới. Nhãn dự đoán và nhãn đã duyệt của bản cũ
              được giữ trong lịch sử, không tự áp dụng sang bản mới.
            </div>
            <div className="inline-actions">
              <button
                onClick={() => {
                  setEditing(false);
                  setText(item.text);
                }}
                disabled={busy}
              >
                Hủy sửa
              </button>
              <button
                className="primary"
                onClick={() => void saveText()}
                disabled={busy || !text.trim() || text === item.text}
              >
                Lưu phiên bản văn bản
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="original-text">{item.text}</p>
            <button
              className="quiet"
              disabled={item.stale}
              onClick={() => setEditing(true)}
            >
              Sửa văn bản
            </button>
          </>
        )}
        {item.error && (
          <div className="notice error" role="alert">
            Lỗi xử lý: {item.error}
          </div>
        )}
        {item.prediction?.truncated && (
          <div className="notice warning">
            Model đã cắt ngắn đầu vào (
            {item.prediction.token_count_before_truncation} token trước cắt).
            Kết quả không phản ánh đầy đủ toàn văn.
          </div>
        )}
        {item.prediction?.warnings?.map((w, i) => (
          <p className="notice warning small" key={i}>
            {w}
          </p>
        ))}
      </section>
      <section className="prediction-section">
        <h3>Dự đoán AI gốc</h3>
        {item.prediction ? (
          <>
            <dl className="prediction-labels">
              {tasks.map((task) => (
                <div key={task}>
                  <dt>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</dt>
                  <dd>
                    {labelName(
                      profile,
                      task,
                      item.prediction?.[task]?.label_id,
                    )}
                  </dd>
                </div>
              ))}
            </dl>
            <details>
              <summary>Điểm mô hình</summary>
              <p className="muted small">
                Điểm softmax chưa được hiệu chuẩn; không phải xác suất dự đoán
                đúng.
                {profile.id === "neu" &&
                  " Nhãn Ngôn từ độc hại (Toxic) chỉ hỗ trợ người rà soát, không tự động kết luận về người viết."}
              </p>
              {tasks.map((task) => (
                <div className="score-group" key={task}>
                  <h4>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</h4>
                  {profile[task].map((l, index) => {
                    const rawScore = item.prediction?.[task]?.scores?.[index];
                    const hasValidScore =
                      typeof rawScore === "number" &&
                      Number.isFinite(rawScore) &&
                      rawScore >= 0 &&
                      rawScore <= 1;
                    return (
                      <div className="score-row" key={l.id}>
                        <span>{l.name}</span>
                        <progress
                          value={hasValidScore ? rawScore : 0}
                          max={1}
                          aria-label={`Điểm ${l.name}`}
                        />
                        <span>
                          {hasValidScore
                            ? `${(rawScore * 100).toFixed(1)}%`
                            : "—"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </details>
            <p className="muted small model-info">
              {item.prediction.model_id} · {item.prediction.model_version} ·{" "}
              {typeof item.prediction.duration_ms === "number" &&
              Number.isFinite(item.prediction.duration_ms)
                ? `${item.prediction.duration_ms.toFixed(0)} ms`
                : "—"}
            </p>
          </>
        ) : (
          <p className="muted">
            Chưa có dự đoán cho phiên bản này. Bạn có thể gán nhãn thủ công ở
            dưới.
          </p>
        )}
        <SignalSection
          item={item}
          profile={profile}
          tasks={tasks}
          policy={policy.data}
          policyPending={policy.isPending}
          policyError={policy.isError ? policy.error : null}
          onRetryPolicy={() => void policy.refetch()}
        />
      </section>
      <SensitivityPanel
        item={item}
        profile={profile}
        runId={runId}
        editingSourceText={editing}
        onReloadItem={() =>
          void client.invalidateQueries({ queryKey: ["item", item.id] })
        }
      />
      <section className="review-section">
        <h3>Rà soát của bạn</h3>
        <p className="muted small">
          Cảm xúc và chủ đề được lưu độc lập. Lưu nhãn không thay đổi dự đoán AI
          gốc.
        </p>
        {tasks.map((task) => (
          <fieldset
            key={task}
            data-testid={`review-${task}`}
            disabled={busy || item.stale}
            className="review-task"
          >
            <legend>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</legend>
            <label>
              Trạng thái {task === "sentiment" ? "cảm xúc" : "chủ đề"}
              <select
                aria-label={`Trạng thái ${task === "sentiment" ? "cảm xúc" : "chủ đề"}`}
                value={drafts[task].status}
                onChange={(e) => {
                  if (hasConflict(task)) return;
                  if (e.target.value === "confirmed") confirmDisplayed(task);
                  else change(task, {
                    status: e.target.value as Review["status"],
                    source_prediction_id: null,
                  });
                }}
              >
                <option value="unreviewed">Chưa rà soát</option>
                <option
                  value="confirmed"
                  disabled={
                    item.prediction?.[task]?.label_id == null || hasConflict(task)
                  }
                >
                  Xác nhận nhãn AI đúng
                </option>
                <option value="corrected">Tự chọn / sửa nhãn</option>
              </select>
            </label>
            {drafts[task].status === "confirmed" && (
              <>
                <p className="small">
                  Nhãn xác nhận:{" "}
                  <strong data-testid={`confirmed-label-${task}`}>
                    {labelName(profile, task, Number(drafts[task].label_id))}
                  </strong>
                </p>
                <p className="muted small review-source" data-testid={`confirmed-source-${task}`}>
                  Prediction nguồn: {drafts[task].source_prediction_id ?? "không có ID"}
                  {drafts[task].source_prediction_id && item.prediction?.id &&
                    drafts[task].source_prediction_id !== item.prediction.id &&
                    " · Khác dự đoán đang xem. Sửa ghi chú giữ nhãn và nguồn này."}
                </p>
              </>
            )}
            {item.prediction?.[task]?.label_id != null && (
              <button
                type="button"
                className="quiet"
                disabled={hasConflict(task)}
                aria-label={`Xác nhận dự đoán đang xem: ${taskName(task)}`}
                onClick={() => confirmDisplayed(task)}
              >
                Xác nhận dự đoán đang xem:{" "}
                {labelName(profile, task, item.prediction?.[task]?.label_id)}
              </button>
            )}
            {drafts[task].status === "corrected" && (
              <label>
                Nhãn {task === "sentiment" ? "cảm xúc" : "chủ đề"} đã sửa
                <select
                  aria-label={`Nhãn ${task === "sentiment" ? "cảm xúc" : "chủ đề"} đã sửa`}
                  value={drafts[task].label_id}
                  onChange={(e) => change(task, { label_id: e.target.value })}
                >
                  <option value="">Chọn nhãn</option>
                  {profile[task].map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              Ghi chú {task === "sentiment" ? "cảm xúc" : "chủ đề"}
              <textarea
                rows={2}
                value={drafts[task].note}
                onChange={(e) => change(task, { note: e.target.value })}
              />
            </label>
            {hasConflict(task) && (
              <div className="notice warning review-conflict" role="alert" data-testid={`review-conflict-${task}`}>
                {hasInputRevisionConflict(task) ? (
                  <>
                    <strong>
                      Văn bản nguồn đã thay đổi — nháp {taskName(task)} thuộc phiên bản{" "}
                      {drafts[task].base_input_revision}.
                    </strong>
                    <p>
                      Bản nháp của bạn được soạn ở{" "}
                      <strong>phiên bản văn bản {drafts[task].base_input_revision}</strong>{" "}
                      (bản duyệt {drafts[task].base_revision}) và vẫn được giữ ở trên để đối chiếu.
                      {hasNewInputSnapshot(task)
                        ? ` Văn bản hiện tại đang ở phiên bản ${item.revision}.`
                        : " Hiện chưa tải được phiên bản văn bản mới nhất từ server."}
                    </p>
                    {hasNewInputSnapshot(task) ? (
                      <>
                        <div className="review-conflict-compare">
                          <div>
                            <span className="small">
                              Văn bản lúc soạn nháp (phiên bản {drafts[task].base_input_revision}):
                            </span>
                            <p className="review-conflict-text">{drafts[task].base_text}</p>
                          </div>
                          <div>
                            <span className="small">
                              Văn bản hiện tại (phiên bản {item.revision}):
                            </span>
                            <p className="review-conflict-text">{item.text}</p>
                          </div>
                        </div>
                        <p>
                          <strong>
                            Nhãn trên phiên bản {item.revision} (bản duyệt {item.reviews[task]?.revision ?? 0}):
                          </strong>{" "}
                          {item.reviews[task]
                            ? `${labelName(profile, task, item.reviews[task]!.label_id)} · ${
                                item.reviews[task]!.status === "confirmed"
                                  ? "Đã xác nhận"
                                  : item.reviews[task]!.status === "corrected"
                                    ? "Đã sửa"
                                    : "Chưa rà soát"
                              }`
                            : "Chưa rà soát"}
                        </p>
                        {item.reviews[task]?.note && (
                          <p className="server-note">
                            Ghi chú server: {item.reviews[task]!.note}
                          </p>
                        )}
                      </>
                    ) : (
                      <div className="inline-actions">
                        <p className="small">
                          Tải lại phiên bản văn bản mới nhất trước khi đối chiếu hoặc lưu nháp.
                        </p>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            onRetrySync();
                            void refresh();
                          }}
                        >
                          Thử tải bản hiện tại
                        </button>
                      </div>
                    )}
                    {drafts[task].status === "confirmed" && (
                      <p className="small">
                        Nháp đang gắn xác nhận dự đoán của văn bản phiên bản{" "}
                        {drafts[task].base_input_revision}
                        {drafts[task].source_prediction_id
                          ? ` (${drafts[task].source_prediction_id})`
                          : ""}
                        . Nếu chọn áp sang văn bản hiện tại, trạng thái sẽ chuyển thành “Tự chọn / sửa nhãn” và không gắn xác nhận dự đoán của văn bản cũ.
                      </p>
                    )}
                    <div className="inline-actions">
                      <button
                        type="button"
                        disabled={!hasNewInputSnapshot(task)}
                        aria-label={`Dùng bản hiện tại, bỏ nháp: ${taskName(task)}`}
                        onClick={() => resolveConflict(task, false)}
                      >
                        Dùng bản hiện tại, bỏ nháp
                      </button>
                      <button
                        type="button"
                        disabled={!hasNewInputSnapshot(task)}
                        aria-label={`Áp nháp lên văn bản hiện tại: ${taskName(task)}`}
                        onClick={() => resolveConflict(task, true)}
                      >
                        Áp nháp lên văn bản hiện tại
                      </button>
                    </div>
                    <p className="small">
                      Áp nháp chỉ cập nhật phiên bản nền sau khi bạn đối chiếu. Bấm Lưu để ghi các thay đổi của bạn.
                    </p>
                  </>
                ) : (
                  <>
                    <strong>Rà soát {taskName(task)} đã thay đổi ở nơi khác.</strong>
                    <p>
                      Bản nháp của bạn dựa trên bản duyệt {drafts[task].base_revision} và vẫn được giữ ở trên.
                      Đối chiếu bản server trước khi tiếp tục lưu.
                    </p>
                    {!hasNewReviewSnapshot(task) ? (
                      <p>Đang tải bản server mới. Nếu chưa tải được, bấm thử lại bên dưới.</p>
                    ) : (
                      <>
                        <p>
                          <strong>Server · bản duyệt {item.reviews[task]?.revision ?? 0}:</strong>{" "}
                          {labelName(profile, task, item.reviews[task]?.label_id)}
                          {item.reviews[task]?.status === "confirmed" ? " · Đã xác nhận" :
                            item.reviews[task]?.status === "corrected" ? " · Đã sửa" : " · Chưa rà soát"}
                        </p>
                        <p className="server-note">Ghi chú server: {item.reviews[task]?.note || "(trống)"}</p>
                        {item.reviews[task]?.source_prediction_id && (
                          <p className="small review-source">Prediction nguồn server: {item.reviews[task]!.source_prediction_id}</p>
                        )}
                      </>
                    )}
                    <div className="inline-actions">
                      <button
                        type="button"
                        disabled={!hasNewReviewSnapshot(task)}
                        aria-label={`Tải bản server: ${taskName(task)}`}
                        onClick={() => resolveConflict(task, false)}
                      >Tải bản server, bỏ bản nháp</button>
                      <button
                        type="button"
                        disabled={!hasNewReviewSnapshot(task)}
                        aria-label={`Áp lại bản nháp: ${taskName(task)}`}
                        onClick={() => resolveConflict(task, true)}
                      >Áp lại bản nháp trên bản server</button>
                    </div>
                    <p className="small">Áp lại chỉ cập nhật bản nền. Bấm Lưu để ghi các thay đổi của bạn.</p>
                  </>
                )}
              </div>
            )}
            <div className="task-save">
              <span className="muted small">
                {item.reviews[task]
                  ? `Đã lưu · bản duyệt ${item.reviews[task]!.revision}`
                  : "Chưa lưu nhãn duyệt"}
              </span>
              <button
                type="button"
                disabled={
                  !drafts[task].dirty || !valid(task) || hasConflict(task) || busy || item.stale
                }
                onClick={() => void save(task)}
              >
                Lưu {task === "sentiment" ? "cảm xúc" : "chủ đề"}
              </button>
            </div>
          </fieldset>
        ))}
        {syncError != null && (
          <ErrorNotice
            error={syncError}
            retry={() => {
              onRetrySync();
              void refresh();
            }}
          />
        )}
        {error != null && (
          <ErrorNotice error={error} retry={() => void refresh()} />
        )}
        <div className="detail-save">
          <button
            disabled={busy || item.stale || tasks.some((t) => !valid(t) || hasConflict(t))}
            className="primary"
            onClick={() => void save(undefined, true)}
          >
            {busy ? "Đang lưu…" : "Lưu và câu tiếp theo →"}
          </button>
          {undo && (
            <button
              disabled={busy || item.stale}
              onClick={() => void undoReview()}
            >
              Hoàn tác lần lưu
            </button>
          )}
        </div>
      </section>
      {tasks.some((t) => item.reference?.[t]) && (
        <section>
          <h3>Nhãn tham chiếu</h3>
          <p className="muted small">
            Được nhập riêng từ nguồn đã xác nhận; không thay thế nhãn AI hoặc
            nhãn duyệt.
          </p>
          {tasks.map(
            (t) =>
              item.reference[t] && (
                <p key={t}>
                  <strong>{t === "sentiment" ? "Cảm xúc" : "Chủ đề"}:</strong>{" "}
                  {labelName(profile, t, item.reference[t]!.label_id)}{" "}
                  <span className="muted small">
                    · {item.reference[t]!.source}
                  </span>
                </p>
              ),
          )}
        </section>
      )}
      <details onToggle={(e) => setHistoryOpen(e.currentTarget.open)}>
        <summary>Lịch sử rà soát</summary>
        {historyOpen &&
          (history.isPending ? (
            <Loading />
          ) : history.isError ? (
            <ErrorNotice error={history.error} />
          ) : history.data?.length ? (
            history.data.map((r, i) => (
              <div
                className="review-history-row"
                key={`${r.task}-${r.revision}-${i}`}
              >
                <div>
                  <strong>
                    {r.task === "sentiment"
                      ? "Cảm xúc"
                      : r.task === "topic"
                        ? "Chủ đề"
                        : "Rà soát"}{" "}
                    · bản {r.revision}
                  </strong>
                  <p>
                    {r.task
                      ? labelName(profile, r.task, r.label_id)
                      : r.label_id}{" "}
                    ·{" "}
                    {r.status === "confirmed"
                      ? "Đã xác nhận"
                      : r.status === "corrected"
                        ? "Đã sửa"
                        : "Chưa rà soát"}
                  </p>
                  {r.note && <p className="small">{r.note}</p>}
                  <p className="muted small">
                    Văn bản bản {r.input_revision ?? "?"} · {date(r.created_at)}
                  </p>
                </div>
                <button
                  disabled={
                    busy ||
                    item.stale ||
                    !r.task ||
                    r.revision_id !== item.revision_id
                  }
                  onClick={() => void restore(r)}
                >
                  Khôi phục
                </button>
              </div>
            ))
          ) : (
            <p className="muted">Chưa có lịch sử rà soát.</p>
          ))}
      </details>
      <details onToggle={(e) => setRevisionOpen(e.currentTarget.open)}>
        <summary>Lịch sử văn bản</summary>
        {revisionOpen &&
          (revisions.isPending ? (
            <Loading />
          ) : revisions.isError ? (
            <ErrorNotice error={revisions.error} />
          ) : (
            revisions.data?.map((r) => (
              <div className="revision-row" key={r.revision_id}>
                <strong>Phiên bản {r.revision}</strong>
                <span className="muted small"> · {date(r.created_at)}</span>
                <p>{r.text}</p>
              </div>
            ))
          ))}
      </details>
      <details>
        <summary>Metadata gốc</summary>
        <pre>{JSON.stringify(item.metadata, null, 2)}</pre>
        <Badge>Schema {profile.schema_id}</Badge>
      </details>
    </div>
  );
}
function SignalSection({
  item,
  profile,
  tasks,
  policy,
  policyPending,
  policyError,
  onRetryPolicy,
}: {
  item: Item;
  profile: Profile;
  tasks: Task[];
  policy: ReviewPolicy | undefined;
  policyPending: boolean;
  policyError: unknown;
  onRetryPolicy: () => void;
}) {
  const sig = item.review_signals;
  const experimental = (sig?.experimental ?? policy?.experimental) !== false;
  const policyId = sig?.policy_id ?? policy?.id;
  const policyHash = sig?.policy_hash ?? policy?.hash;
  const hasAnySignal =
    sig != null &&
    (sig.sentiment.state === "flagged" ||
      sig.topic.state === "flagged" ||
      sig.truncated === true);

  const renderTaskBadge = (
    task: Task,
    taskSig: TaskReviewSignal | undefined,
  ) => {
    if (!taskSig || taskSig.state === "unavailable") {
      return <Badge tone="neutral">Chưa có tín hiệu điểm</Badge>;
    }
    if (taskSig.state === "flagged") {
      return (
        <Badge tone="warning">
          {task === "sentiment"
            ? "Model phân vân: cảm xúc"
            : "Model phân vân: chủ đề"}
        </Badge>
      );
    }
    return <span className="muted small">Không có cờ</span>;
  };

  return (
    <div className="signal-section">
      <div className="signal-header">
        <h4>Tín hiệu model</h4>
        {experimental && (
          <Badge tone="neutral">Ngưỡng thử nghiệm, chưa hiệu chuẩn</Badge>
        )}
      </div>
      <p className="muted small">
        Tín hiệu tính từ dự đoán AI gốc của lần đang xem (giữ nguyên khi đổi
        Nguồn nhãn hoặc sau khi lưu rà soát).
      </p>
      {sig?.truncated === true && (
        <div className="signal-truncated-row">
          <Badge tone="warning">Đầu vào bị cắt ngắn</Badge>
          <span className="small">
            Cảnh báo độ dài đầu vào, tách riêng với độ phân vân từ điểm mô
            hình. Dòng bị cắt ngắn chỉ rời hàng chờ “Có tín hiệu, chưa đối
            chiếu” sau khi đã rà soát cả cảm xúc và chủ đề theo dự đoán này hoặc
            chọn nhãn thủ công.
          </span>
        </div>
      )}
      <div className="signal-task-list">
        {tasks.map((task) => {
          const taskSig = sig?.[task];
          return (
            <div className="signal-task-row" key={task}>
              <div className="signal-task-top">
                <strong>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</strong>
                {renderTaskBadge(task, taskSig)}
              </div>
              {taskSig && taskSig.reasons.length > 0 && (
                <p className="small">
                  {taskSig.reasons.map(signalReasonText).join(" · ")}
                </p>
              )}
              {!taskSig && (
                <p className="muted small">
                  Chưa có dữ liệu tín hiệu cho tác vụ này.
                </p>
              )}
              <p className="muted small">
                Đối chiếu: {reviewRelationText(taskSig?.review_relation)}
              </p>
            </div>
          );
        })}
      </div>
      {hasAnySignal && (
        <p className="muted small">
          {sig.pending_signal_review
            ? "Trạng thái hàng chờ: còn tín hiệu chưa đối chiếu với dự đoán đang xem."
            : "Trạng thái hàng chờ: đã đối chiếu cho dự đoán đang xem; dấu hiệu trên dự đoán AI gốc vẫn được giữ."}
        </p>
      )}
      {policyError != null && (
        <ErrorNotice error={policyError} retry={onRetryPolicy} />
      )}
      <details className="signal-details">
        <summary>Vì sao được đánh dấu?</summary>
        {policyPending && !policy && (
          <p className="muted small">Đang tải ngưỡng chính sách rà soát…</p>
        )}
        {(policyId || policyHash) && (
          <p className="muted small technical-reason">
            Chính sách: {policyId ?? "—"}
            {experimental ? " · Ngưỡng thử nghiệm, chưa hiệu chuẩn" : ""}
            {policyHash ? ` · hash ${policyHash.slice(0, 12)}` : ""}
          </p>
        )}
        <p className="muted small">
          Gắn cờ khi điểm cao nhất (top1) &lt; ngưỡng top1 hoặc khoảng cách hai
          nhãn dẫn đầu (margin) &lt; ngưỡng margin trên điểm gốc chưa làm tròn.
          Đây không phải xác suất dự đoán đúng hay dấu hiệu phát hiện mỉa mai.
        </p>
        {tasks.map((task) => {
          const taskSig = sig?.[task];
          const threshold = policy?.[task];
          return (
            <div className="signal-task-detail" key={task}>
              <strong>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</strong>
              {!taskSig || taskSig.state === "unavailable" ? (
                <>
                  <p className="muted small">
                    {taskSig?.reasons.includes("INVALID_SCORES")
                      ? "Không thể tính tín hiệu (INVALID_SCORES): điểm mô hình không hợp lệ, thiếu nhãn hoặc tổng sai lệch vượt ngưỡng."
                      : "Chưa có dữ liệu điểm do chưa có dự đoán AI (NO_PREDICTION)."}
                  </p>
                  {threshold && (
                    <p className="muted small">
                      Ngưỡng chính sách: top1 &lt;{" "}
                      {formatThreshold(threshold.top1_min)}, margin &lt;{" "}
                      {formatThreshold(threshold.margin_min)}.
                    </p>
                  )}
                </>
              ) : (
                <dl className="signal-metrics">
                  <dt>Nhãn dẫn đầu (top1)</dt>
                  <dd>
                    {labelName(profile, task, taskSig.top1_label_id)} ·{" "}
                    {formatScore(taskSig.top1)}
                    {threshold
                      ? ` (ngưỡng < ${formatThreshold(threshold.top1_min)})`
                      : ""}
                  </dd>
                  <dt>Nhãn thứ hai (top2)</dt>
                  <dd>
                    {labelName(profile, task, taskSig.top2_label_id)} ·{" "}
                    {formatScore(taskSig.top2)}
                  </dd>
                  <dt>Khoảng cách (margin)</dt>
                  <dd>
                    {formatScore(taskSig.margin)}
                    {threshold
                      ? ` (ngưỡng < ${formatThreshold(threshold.margin_min)})`
                      : ""}
                  </dd>
                  <dt>Kết luận tín hiệu</dt>
                  <dd>
                    {taskSig.state === "flagged"
                      ? taskSig.reasons.map(signalReasonText).join(" · ")
                      : "Không vượt dưới ngưỡng gắn cờ (Không có cờ)"}
                  </dd>
                </dl>
              )}
            </div>
          );
        })}
      </details>
    </div>
  );
}
