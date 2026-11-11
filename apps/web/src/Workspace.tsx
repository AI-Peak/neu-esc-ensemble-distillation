import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import type { ColumnDef } from "@tanstack/react-table";
import { api, filterBody, post, query } from "./api";
import type {
  Dataset,
  Filters,
  Item,
  ItemPage,
  Job,
  Profile,
  Run,
  Summary,
  Task,
} from "./types";
import {
  activeJob,
  date,
  defaultFilters,
  labelName,
  normalizeReviewSignalFilter,
  reviewName,
} from "./types";
import { Badge, Empty, ErrorNotice, Loading, Modal } from "./ui";
import type { Notify } from "./App";
import { ItemDetail } from "./ItemDetail";
import { TopicAttention } from "./TopicAttention";
const jobLabel: Record<string, string> = {
  queued: "Đang chờ",
  pending: "Đang chờ",
  running: "Đang phân tích",
  loading_model: "Đang nạp model",
  completed: "Hoàn tất",
  failed: "Có lỗi",
  cancelled: "Đã hủy",
  cancelling: "Đang hủy",
  interrupted: "Bị gián đoạn",
  partial: "Hoàn tất một phần",
  completed_with_errors: "Hoàn tất, có dòng lỗi",
};
export function Workspace({
  dataset,
  profile,
  notify,
  onManage,
}: {
  dataset: Dataset;
  profile: Profile;
  notify: Notify;
  onManage: (mode: "rename" | "copy" | "delete") => void;
}) {
  const client = useQueryClient();
  const storageKey = `feedback-filters-${dataset.id}`;
  const [filters, setFilters] = useState<Filters>(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || "{}");
      return {
        ...defaultFilters,
        ...(saved && typeof saved === "object" ? saved : {}),
        review_signal: normalizeReviewSignalFilter(saved?.review_signal),
      };
    } catch {
      return defaultFilters;
    }
  });
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const [tab, setTab] = useState<"overview" | "items" | "review">("overview");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportScope, setExportScope] = useState("filtered");
  const [exportResult, setExportResult] = useState<{
    row_count: number;
    url: string;
    created_at: string;
  } | null>(null);
  const [newText, setNewText] = useState("");
  useEffect(() => {
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(filters));
    } catch {
      /* session storage may be unavailable */
    }
  }, [filters, storageKey]);
  const update = (patch: Partial<Filters>) =>
    setFilters((f) => ({ ...f, ...patch, page: patch.page ?? 1 }));
  const items = useQuery({
    queryKey: ["items", dataset.id, filters],
    queryFn: () =>
      api<ItemPage>(`/datasets/${dataset.id}/items?${query(filters)}`),
  });
  const itemsDataRef = useRef(items.data);
  itemsDataRef.current = items.data;
  useEffect(() => {
    if (!items.data) return;
    const lastPage = Math.max(
      1,
      Math.ceil(items.data.total / filters.page_size),
    );
    if (filters.page > lastPage)
      setFilters((current) => ({ ...current, page: lastPage }));
  }, [items.data, filters.page, filters.page_size]);
  const summaryFilters = useMemo(
    () => ({
      run_id: filters.run_id,
      label_source: filters.label_source,
      q: filters.q,
      sentiment: filters.sentiment,
      topic: filters.topic,
      review_status: filters.review_status,
      review_signal: filters.review_signal,
    }),
    [
      filters.run_id,
      filters.label_source,
      filters.q,
      filters.sentiment,
      filters.topic,
      filters.review_status,
      filters.review_signal,
    ],
  );
  const summary = useQuery({
    queryKey: ["summary", dataset.id, summaryFilters],
    queryFn: () =>
      api<Summary>(
        `/datasets/${dataset.id}/summary?${query(summaryFilters)}`,
      ),
  });
  const runs = useQuery({
    queryKey: ["runs", dataset.id],
    queryFn: () => api<Run[]>(`/datasets/${dataset.id}/analysis-runs`),
  });
  const currentRun =
    runs.data?.find((r) => r.id === filters.run_id) ?? runs.data?.[0];
  const job = useQuery({
    queryKey: ["job", currentRun?.job_id],
    queryFn: () => api<Job>(`/jobs/${currentRun!.job_id}`),
    enabled: !!currentRun?.job_id,
    refetchInterval: (q) =>
      q.state.data && activeJob(q.state.data.status) ? 1200 : false,
  });
  const running = job.data && activeJob(job.data.status);
  useEffect(() => {
    if (job.data) {
      void client.invalidateQueries({ queryKey: ["items", dataset.id] });
      void client.invalidateQueries({ queryKey: ["summary", dataset.id] });
      void client.invalidateQueries({ queryKey: ["item"] });
      void client.invalidateQueries({ queryKey: ["reviews"] });
      void client.invalidateQueries({ queryKey: ["datasets"] });
      if (!activeJob(job.data.status))
        void client.invalidateQueries({ queryKey: ["runs", dataset.id] });
    }
  }, [
    job.data?.completed,
    job.data?.failed,
    job.data?.status,
    client,
    dataset.id,
  ]);
  useEffect(() => {
    setSelected(null);
  }, [dataset.id]);
  async function analyze() {
    setBusy(true);
    try {
      const run = await api<Run>("/analysis-runs", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ dataset_id: dataset.id }),
      });
      update({ run_id: run.id });
      await client.invalidateQueries({ queryKey: ["runs", dataset.id] });
      notify("Đã đưa bộ phản hồi vào hàng chờ phân tích.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function jobAction(action: "cancel" | "retry") {
    if (!job.data) return;
    setBusy(true);
    try {
      await post(`/jobs/${job.data.id}/${action}`, {});
      await client.invalidateQueries({ queryKey: ["job", job.data.id] });
      notify(
        action === "cancel"
          ? "Đã yêu cầu hủy. Kết quả đã lưu vẫn được giữ."
          : "Đã xếp hàng chạy lại các dòng chưa hoàn tất.",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function doExport() {
    setBusy(true);
    try {
      const result = await post<{
        row_count: number;
        url: string;
        created_at: string;
      }>(
        `/datasets/${dataset.id}/exports`,
        filterBody(filters, exportScope === "all"),
      );
      setExportResult(result);
      notify(`Đã tạo bản chụp CSV gồm ${result.row_count} phản hồi.`);
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  async function addItems() {
    setBusy(true);
    try {
      const texts = newText.split(/\r?\n/).filter((t) => t.trim());
      await post(`/datasets/${dataset.id}/items`, {
        items: texts.map((text) => ({ text })),
      });
      setNewText("");
      update({ run_id: "" });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["items", dataset.id] }),
        client.invalidateQueries({ queryKey: ["summary", dataset.id] }),
        client.invalidateQueries({ queryKey: ["datasets"] }),
      ]);
      notify("Đã thêm phản hồi. Các câu mới chưa được phân tích.");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const columns = useMemo<ColumnDef<Item>[]>(
    () => [
      {
        accessorKey: "source_row",
        header: "Dòng",
        cell: (c) => <span className="muted">{c.row.original.source_row}</span>,
      },
      {
        accessorKey: "text",
        header: "Nội dung phản hồi",
        cell: (c) => (
          <button
            className="text-cell"
            onClick={() => setSelected(c.row.original.id)}
          >
            <span>{c.row.original.text}</span>
            {(c.row.original.stale ||
              c.row.original.prediction?.truncated ||
              c.row.original.error) && (
              <span className="row-flags">
                {c.row.original.stale ? "Văn bản đã thay đổi · " : ""}
                {c.row.original.prediction?.truncated ? "Cắt ngắn · " : ""}
                {c.row.original.error ? "Lỗi xử lý" : ""}
              </span>
            )}
          </button>
        ),
      },
      ...(["sentiment", "topic"] as Task[]).map((task) => ({
        id: task,
        header: task === "sentiment" ? "Cảm xúc" : "Chủ đề",
        cell: ({ row }: { row: { original: Item } }) => (
          <span className="label-cell">
            {labelName(
              profile,
              task,
              filters.label_source === "ai"
                ? row.original.prediction?.[task]?.label_id
                : row.original.effective[task],
            )}
          </span>
        ),
      })),
      {
        id: "signals",
        header: "Tín hiệu model",
        cell: (c) => <SignalBadges item={c.row.original} />,
      },
      {
        id: "review",
        header: "Rà soát",
        cell: (c) => (
          <Badge
            tone={
              reviewName(c.row.original) === "Đã rà soát"
                ? "success"
                : "neutral"
            }
          >
            {reviewName(c.row.original)}
          </Badge>
        ),
      },
    ],
    [profile, filters.label_source],
  );
  const table = useReactTable({
    data: items.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
  });
  const activeFilterCount = [
    filters.q,
    filters.sentiment,
    filters.topic,
    filters.review_status === "all" ? "" : filters.review_status,
    filters.review_signal === "all" ? "" : filters.review_signal,
  ].filter(Boolean).length;
  return (
    <>
      <div className="page-heading workspace-heading">
        <div>
          <a className="back-link" href="#/">
            ← Bộ phản hồi
          </a>
          <h1>{dataset.name}</h1>
          <p>
            {profile.name} · {dataset.item_count} phản hồi ·{" "}
            <span>
              {profile.model.available ? "Model sẵn sàng" : "Chưa có model"}
            </span>
            {profile.model.available && profile.model.model_id
              ? ` · ${profile.model.model_id}`
              : ""}
          </p>
        </div>
        <div className="inline-actions">
          <button
            className="primary"
            data-testid="analyze"
            disabled={
              busy ||
              !profile.model.available ||
              !!running ||
              !dataset.item_count
            }
            onClick={() => void analyze()}
          >
            {busy ? "Đang xử lý…" : "Phân tích AI"}
          </button>
          <button
            data-testid="export"
            onClick={() => {
              setExporting(true);
              setExportResult(null);
            }}
          >
            Xuất CSV
          </button>
          <details className="action-menu">
            <summary aria-label="Thao tác bộ phản hồi">•••</summary>
            <div>
              <button onClick={() => onManage("rename")}>Đổi tên</button>
              <button onClick={() => onManage("copy")}>
                Sao chép / đổi hệ nhãn
              </button>
              <button
                className="danger-text"
                onClick={() => onManage("delete")}
              >
                Xóa bộ phản hồi
              </button>
            </div>
          </details>
        </div>
      </div>
      {profile.model.available &&
        profile.model.preprocessing?.equivalence === "approximate" && (
          <div className="notice small">
            <span>
              Văn bản được tách từ trước khi phân tích. Kết quả trên dữ liệu bạn
              nhập có thể khác benchmark nghiên cứu.
            </span>
            <details>
              <summary>Chi tiết kỹ thuật & giới hạn</summary>
              <p className="technical-reason small">
                Model đang dùng: {profile.model.model_id} ·{" "}
                {profile.model.model_version}. Văn bản gốc được giữ nguyên khi
                lưu và xuất CSV; bước tách từ nội bộ dùng underthesea 9.5.0
                (khác pipeline tách từ NEU gốc của tác giả, tối đa 128 token).
                {profile.id === "neu" &&
                  " Trên NEU-ESC, nhãn Ngôn từ độc hại (Toxic) là lớp hiếm (2,5% dữ liệu huấn luyện) và ED có F1 Toxic thấp hơn SMART; chỉ dùng hỗ trợ rà soát, không tự động kết luận về người viết."}
              </p>
            </details>
          </div>
        )}
      {!profile.model.available && (
        <div className="notice warning">
          <strong>Chưa thể phân tích AI</strong>
          <span>
            Chưa có bộ model hợp lệ cho loại nội dung này. Bạn vẫn có thể đọc,
            gán nhãn thủ công và xuất dữ liệu.
          </span>
          <a href="#/help">Xem trạng thái model →</a>
          {profile.model.reason && (
            <details>
              <summary>Chi tiết kỹ thuật</summary>
              <p className="technical-reason small">{profile.model.reason}</p>
            </details>
          )}
        </div>
      )}
      {job.data && (
        <div className="job-strip" role="status">
          <div>
            <strong>{jobLabel[job.data.status] ?? job.data.status}</strong>
            <span>
              {job.data.completed}/{job.data.total} kết quả đã lưu
              {job.data.failed ? ` · ${job.data.failed} dòng lỗi` : ""}
              {job.data.cancel_requested ? " · Đã yêu cầu hủy" : ""}
            </span>
          </div>
          <progress
            value={job.data.completed}
            max={job.data.total || 1}
            aria-label="Tiến độ phân tích"
          />
          <div>
            {running ? (
              <button
                disabled={busy || job.data.cancel_requested}
                onClick={() => void jobAction("cancel")}
              >
                Hủy phân tích
              </button>
            ) : [
                "failed",
                "cancelled",
                "interrupted",
                "partial",
                "completed_with_errors",
              ].includes(job.data.status) || job.data.failed > 0 ? (
              <button
                disabled={busy || !profile.model.available}
                onClick={() => void jobAction("retry")}
              >
                Chạy lại phần chưa xong
              </button>
            ) : null}
          </div>
          {job.data.error && <p className="error-text">{job.data.error}</p>}
        </div>
      )}
      {job.isError && (
        <ErrorNotice error={job.error} retry={() => void job.refetch()} />
      )}
      <div
        className="tabs workspace-tabs"
        role="tablist"
        aria-label="Khu vực bộ phản hồi"
      >
        {(
          [
            ["overview", "Tổng quan"],
            ["items", "Tất cả phản hồi"],
            ["review", "Cần rà soát"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => {
              setTab(value);
              if (value === "review") update({ review_status: "needs_review" });
              else if (tab === "review") update({ review_status: "all" });
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="filterbar">
        <label className="filter-search">
          <span>Tìm nội dung</span>
          <input
            type="search"
            aria-label="Tìm nội dung"
            value={filters.q}
            onChange={(e) => update({ q: e.target.value })}
            placeholder="Từ khóa trong phản hồi…"
          />
        </label>
        {(["sentiment", "topic"] as Task[]).map((task) => (
          <label key={task}>
            {task === "sentiment" ? "Cảm xúc" : "Chủ đề"}
            <select
              aria-label={task === "sentiment" ? "Lọc cảm xúc" : "Lọc chủ đề"}
              value={filters[task]}
              onChange={(e) => update({ [task]: e.target.value })}
            >
              <option value="">Tất cả</option>
              {profile[task].map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label>
          Rà soát
          <select
            aria-label="Lọc trạng thái rà soát"
            value={filters.review_status}
            onChange={(e) => update({ review_status: e.target.value })}
          >
            <option value="all">Tất cả</option>
            <option value="unreviewed">Chưa rà soát</option>
            <option value="partial">Duyệt một phần</option>
            <option value="reviewed">Đã rà soát</option>
            <option value="needs_review">Cần rà soát (quy tắc hiện có)</option>
          </select>
        </label>
        <label>
          Tín hiệu model
          <select
            aria-label="Lọc tín hiệu model"
            value={filters.review_signal}
            onChange={(e) =>
              update({
                review_signal: normalizeReviewSignalFilter(e.target.value),
              })
            }
          >
            <option value="all">Tất cả</option>
            <option value="model_uncertain">Model phân vân (mọi tác vụ)</option>
            <option value="sentiment_uncertain">
              Model phân vân: cảm xúc
            </option>
            <option value="topic_uncertain">Model phân vân: chủ đề</option>
            <option value="truncated">Đầu vào bị cắt ngắn</option>
            <option value="pending_signal_review">
              Có tín hiệu, chưa đối chiếu
            </option>
          </select>
        </label>
        {activeFilterCount > 0 && (
          <button
            className="quiet"
            onClick={() => {
              update({
                q: "",
                sentiment: "",
                topic: "",
                review_status: "all",
                review_signal: "all",
              });
              if (tab === "review") setTab("items");
            }}
          >
            Bỏ lọc ({activeFilterCount})
          </button>
        )}
      </div>
      <div className="source-controls">
        <label>
          Nguồn nhãn
          <select
            value={filters.label_source}
            onChange={(e) =>
              update({
                label_source: e.target.value as Filters["label_source"],
              })
            }
          >
            <option value="effective">Đã duyệt nếu có, còn lại AI</option>
            <option value="ai">Chỉ dự đoán AI gốc</option>
          </select>
        </label>
        <label>
          Phiên bản dữ liệu
          <select
            aria-label="Lần phân tích"
            value={filters.run_id}
            onChange={(e) => update({ run_id: e.target.value })}
          >
            <option value="">Văn bản hiện tại</option>
            {runs.data?.map((r) => (
              <option key={r.id} value={r.id}>
                Lần chạy {date(r.created_at)} · {jobLabel[r.status] ?? r.status}
              </option>
            ))}
          </select>
        </label>
      </div>
      {tab === "review" && (
        <div className="notice small review-queue-notice">
          <p>
            <strong>Cần rà soát (quy tắc hiện có):</strong> chưa duyệt đủ hai
            tác vụ, có lỗi, bị cắt ngắn hoặc điểm cao nhất dưới 0,6. Điểm chưa
            hiệu chuẩn; đây là hàng chờ hỗ trợ. Khi lọc theo{" "}
            <em>Model phân vân</em>, dòng đã duyệt vẫn có thể xuất hiện để giữ
            nguyên dấu hiệu của dự đoán AI.
          </p>
          <p>
            <strong>Hàng chờ tín hiệu chưa đối chiếu:</strong> tách riêng theo
            cảm xúc và chủ đề; dòng rời hàng chờ khi tác vụ được gắn cờ đã xác
            nhận theo dự đoán đang xem hoặc tự chọn thủ công (đầu vào bị cắt
            ngắn cần đối chiếu cả hai tác vụ).
          </p>
          <div className="inline-actions">
            <button
              type="button"
              onClick={() =>
                update({
                  review_status: "all",
                  review_signal: "pending_signal_review",
                })
              }
            >
              Có tín hiệu, chưa đối chiếu
            </button>
          </div>
        </div>
      )}
      {filters.run_id && (
        <p className="notice small">
          Bạn đang xem văn bản tại lần phân tích đã chọn. Dòng được sửa sau đó
          sẽ có cảnh báo “Văn bản đã thay đổi”.
        </p>
      )}
      {tab === "overview" && (
        <>
          {summary.isPending ? (
            <Loading text="Đang tính tổng quan theo bộ lọc…" />
          ) : summary.isError ? (
            <ErrorNotice
              error={summary.error}
              retry={() => void summary.refetch()}
            />
          ) : (
            <>
              <div className="summary-line">
                <span>
                  <strong>{summary.data.total}</strong> phản hồi theo bộ lọc
                </span>
                <span>{summary.data.processed} đã phân tích</span>
                <span>{summary.data.reviewed} đã rà soát</span>
                <span>{summary.data.partial_review} duyệt một phần</span>
                <span>
                  {summary.data.errors} lỗi · {summary.data.truncated} cắt ngắn
                </span>
                {running && <Badge tone="warning">Kết quả tạm thời</Badge>}
              </div>
              <TopicAttention
                summary={summary.data}
                profile={profile}
                sentimentFilter={filters.sentiment}
                labelSource={filters.label_source}
                running={!!running}
                onSelectTopicNegative={(topicId, negativeLabelId) => {
                  update({
                    topic: String(topicId),
                    sentiment: String(negativeLabelId),
                    sort: "source_row",
                    direction: "asc",
                    page: 1,
                  });
                  setTab("items");
                }}
              />
              <div className="charts">
                <Distribution
                  title="Phân bố cảm xúc"
                  task="sentiment"
                  profile={profile}
                  summary={summary.data}
                  onSelect={(id) => {
                    update({ sentiment: String(id) });
                    setTab("items");
                  }}
                />
                <Distribution
                  title="Phân bố chủ đề"
                  task="topic"
                  profile={profile}
                  summary={summary.data}
                  onSelect={(id) => {
                    update({ topic: String(id) });
                    setTab("items");
                  }}
                />
              </div>
              <section className="cross-section">
                <h2>Cảm xúc trong từng chủ đề</h2>
                <p className="muted small">
                  Bấm một ô để xem phản hồi tương ứng. Mẫu số:{" "}
                  {summary.data.denominator.cross} dòng có đủ hai nhãn.
                </p>
                {summary.data.denominator.cross > 0 && (
                  <div className="table-scroll">
                    <table className="cross-table">
                      <thead>
                        <tr>
                          <th>Chủ đề</th>
                          {profile.sentiment.map((l) => (
                            <th key={l.id}>{l.name}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {profile.topic.map((t) => (
                          <tr key={t.id}>
                            <th>{t.name}</th>
                            {profile.sentiment.map((s) => {
                              const n =
                                summary.data.cross.find(
                                  (c) =>
                                    c.topic === t.id && c.sentiment === s.id,
                                )?.count ?? 0;
                              return (
                                <td key={s.id}>
                                  <button
                                    aria-label={`${t.name}, ${s.name}: ${n} phản hồi`}
                                    disabled={!n}
                                    onClick={() => {
                                      update({
                                        sentiment: String(s.id),
                                        topic: String(t.id),
                                      });
                                      setTab("items");
                                    }}
                                  >
                                    {n}
                                  </button>
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
      <section className="items-section">
        <div className="section-heading">
          <h2>
            {tab === "overview"
              ? "Phản hồi theo bộ lọc"
              : tab === "review"
                ? "Hàng chờ rà soát"
                : "Tất cả phản hồi"}{" "}
            <span className="muted">({items.data?.total ?? "…"})</span>
          </h2>
          <div className="inline-actions">
            <label className="compact-label">
              Sắp xếp
              <select
                aria-label="Sắp xếp phản hồi"
                value={filters.sort}
                onChange={(e) => update({ sort: e.target.value })}
              >
                <option value="source_row">Dòng nguồn</option>
                <option value="text">Nội dung</option>
                <option value="sentiment">Cảm xúc</option>
                <option value="topic">Chủ đề</option>
              </select>
            </label>
            <button
              aria-label={
                filters.direction === "asc"
                  ? "Đổi sang giảm dần"
                  : "Đổi sang tăng dần"
              }
              onClick={() =>
                update({
                  direction: filters.direction === "asc" ? "desc" : "asc",
                })
              }
            >
              {filters.direction === "asc" ? "↑ Tăng" : "↓ Giảm"}
            </button>
          </div>
        </div>
        {items.isPending ? (
          <Loading />
        ) : items.isError ? (
          <ErrorNotice error={items.error} retry={() => void items.refetch()} />
        ) : items.data.total === 0 ? (
          <Empty title="Không có phản hồi trong bộ lọc này">
            <p>
              Thử tìm từ khóa khác hoặc bỏ bớt điều kiện lọc. Các câu mới chưa
              phân tích vẫn có thể được rà soát thủ công.
            </p>
            {activeFilterCount > 0 && (
              <button
                onClick={() => {
                  update({
                    q: "",
                    sentiment: "",
                    topic: "",
                    review_status: "all",
                    review_signal: "all",
                  });
                  if (tab === "review") setTab("items");
                }}
              >
                Bỏ bộ lọc
              </button>
            )}
          </Empty>
        ) : (
          <>
            <div
              className={`table-scroll item-table ${items.isFetching ? "refreshing" : ""}`}
              aria-busy={items.isFetching}
            >
              <table>
                <thead>
                  {table.getHeaderGroups().map((group) => (
                    <tr key={group.id}>
                      {group.headers.map((h) => (
                        <th key={h.id}>
                          {flexRender(
                            h.column.columnDef.header,
                            h.getContext(),
                          )}
                        </th>
                      ))}
                    </tr>
                  ))}
                </thead>
                <tbody>
                  {table.getRowModel().rows.map((row) => (
                    <tr
                      key={row.id}
                      className={
                        selected === row.original.id ? "selected-row" : ""
                      }
                    >
                      {row.getVisibleCells().map((cell) => (
                        <td
                          key={cell.id}
                          data-label={
                            typeof cell.column.columnDef.header === "string"
                              ? cell.column.columnDef.header
                              : ""
                          }
                        >
                          {flexRender(
                            cell.column.columnDef.cell,
                            cell.getContext(),
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <label>
                Số dòng mỗi trang
                <select
                  value={filters.page_size}
                  onChange={(e) =>
                    update({ page_size: Number(e.target.value) })
                  }
                >
                  {[10, 25, 50, 100].map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <span>
                Trang {filters.page} /{" "}
                {Math.max(1, Math.ceil(items.data.total / filters.page_size))} ·{" "}
                {items.data.total} phản hồi
              </span>
              <div className="inline-actions">
                <button
                  disabled={filters.page === 1}
                  onClick={() => update({ page: filters.page - 1 })}
                >
                  ← Trước
                </button>
                <button
                  disabled={
                    filters.page * filters.page_size >= items.data.total
                  }
                  onClick={() => update({ page: filters.page + 1 })}
                >
                  Tiếp →
                </button>
              </div>
            </div>
          </>
        )}
      </section>
      <details className="section append-section">
        <summary>Thêm phản hồi vào bộ này</summary>
        <label>
          Phản hồi mới (mỗi dòng một câu)
          <textarea
            rows={4}
            value={newText}
            onChange={(e) => setNewText(e.target.value)}
          />
        </label>
        <button
          disabled={busy || !newText.trim()}
          onClick={() => void addItems()}
        >
          Thêm phản hồi
        </button>
      </details>
      <details className="section run-history">
        <summary>Lịch sử phân tích ({runs.data?.length ?? 0})</summary>
        {runs.isError ? (
          <ErrorNotice error={runs.error} />
        ) : runs.data?.length ? (
          runs.data.map((r) => (
            <div className="history-row" key={r.id}>
              <div>
                <strong>{date(r.created_at)}</strong>
                <p className="small muted">
                  {r.model_id} · {r.model_version} · {r.completed}/{r.total} kết
                  quả · {r.failed} lỗi
                </p>
              </div>
              <Badge>{jobLabel[r.status] ?? r.status}</Badge>
              <button onClick={() => update({ run_id: r.id })}>
                Xem lần này
              </button>
            </div>
          ))
        ) : (
          <p className="muted">
            Chưa có lần phân tích. Nhãn rà soát thủ công vẫn được lưu độc lập.
          </p>
        )}
      </details>
      {selected && (
        <ItemDetail
          key={selected + filters.run_id}
          itemId={selected}
          profile={profile}
          runId={filters.run_id}
          onClose={() => setSelected(null)}
          notify={notify}
          onNext={() => {
            const currentFilters = filtersRef.current;
            const pageData =
              client.getQueryData<ItemPage>([
                "items",
                dataset.id,
                currentFilters,
              ]) ?? itemsDataRef.current;
            const rows = pageData?.items ?? [];
            const total = pageData?.total ?? 0;
            const index = rows.findIndex((i) => i.id === selected);
            if (index >= 0 && index < rows.length - 1) {
              setSelected(rows[index + 1].id);
            } else if (index < 0 && rows.length > 0) {
              setSelected(rows[0].id);
            } else if (total === 0) {
              setSelected(null);
              notify("Không còn phản hồi trong bộ lọc hiện tại.");
            } else if (
              rows.length === 0 &&
              total > 0 &&
              currentFilters.page > 1
            ) {
              update({
                page: Math.max(1, Math.ceil(total / currentFilters.page_size)),
              });
              setSelected(null);
              notify("Đã chuyển về trang cuối còn phản hồi.");
            } else if (
              pageData &&
              currentFilters.page * currentFilters.page_size < total
            ) {
              update({ page: currentFilters.page + 1 });
              setSelected(null);
              notify(
                "Đã chuyển sang trang tiếp theo. Chọn phản hồi để tiếp tục.",
              );
            } else {
              setSelected(null);
              notify("Đã đến cuối trang phản hồi.");
            }
          }}
        />
      )}
      {exporting && (
        <Modal title="Xuất kết quả CSV" onClose={() => setExporting(false)}>
          <p>
            CSV UTF-8 có BOM. Bản chụp giữ riêng dự đoán AI, tham chiếu, nhãn
            duyệt, phiên bản model và văn bản. CSV giữ các cột hiện có; tín hiệu
            tự động không có cột riêng.
          </p>
          <label>
            Phạm vi xuất
            <select
              value={exportScope}
              disabled={busy}
              onChange={(e) => setExportScope(e.target.value)}
            >
              <option value="filtered">
                Phản hồi theo bộ lọc hiện tại ({items.data?.total ?? "…"})
              </option>
              <option value="all">Toàn bộ bộ phản hồi</option>
            </select>
          </label>
          <p className="muted small">
            Giữ lựa chọn lần phân tích và nguồn nhãn. “Toàn bộ” bỏ các bộ lọc
            tìm kiếm, nhãn, trạng thái rà soát và tín hiệu model.
          </p>
          {exportResult && (
            <div className="notice success">
              <strong>Đã tạo CSV: {exportResult.row_count} dòng</strong>
              <span>Bản chụp lúc {date(exportResult.created_at)}</span>
              <a className="button primary" href={exportResult.url} download>
                Tải CSV
              </a>
            </div>
          )}
          <div className="dialog-actions">
            <button onClick={() => setExporting(false)}>Đóng</button>
            <button
              className="primary"
              disabled={busy}
              onClick={() => void doExport()}
            >
              {busy
                ? "Đang tạo CSV…"
                : exportResult
                  ? "Tạo bản chụp mới"
                  : "Tạo bản chụp CSV"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
function SignalBadges({ item }: { item: Item }) {
  const sig = item.review_signals;
  if (!sig) {
    return (
      <div className="signal-badges">
        <Badge tone="neutral">Chưa có tín hiệu điểm</Badge>
      </div>
    );
  }
  const sFlagged = sig.sentiment.state === "flagged";
  const tFlagged = sig.topic.state === "flagged";
  const hasTruncated = sig.truncated === true;
  const hasUnavailable =
    sig.sentiment.state === "unavailable" || sig.topic.state === "unavailable";
  const hasAnySignal = sFlagged || tFlagged || hasTruncated;

  return (
    <div className="signal-badges">
      {sFlagged && <Badge tone="warning">Model phân vân: cảm xúc</Badge>}
      {tFlagged && <Badge tone="warning">Model phân vân: chủ đề</Badge>}
      {hasTruncated && <Badge tone="warning">Đầu vào bị cắt ngắn</Badge>}
      {hasUnavailable && <Badge tone="neutral">Chưa có tín hiệu điểm</Badge>}
      {!hasAnySignal && !hasUnavailable && (
        <span className="muted small">Không có cờ</span>
      )}
      {hasAnySignal && !sig.pending_signal_review && (
        <span className="muted small">Đã đối chiếu</span>
      )}
    </div>
  );
}
function Distribution({
  title,
  task,
  profile,
  summary,
  onSelect,
}: {
  title: string;
  task: Task;
  profile: Profile;
  summary: Summary;
  onSelect: (id: number) => void;
}) {
  const denominator = summary.denominator[task];
  return (
    <section className="distribution">
      <h2>{title}</h2>
      <p className="muted small">
        {denominator} dòng có nhãn · bấm thanh để lọc
      </p>
      {!!denominator &&
        profile[task].map((label) => {
          const n =
            summary[task].find((v) => v.label_id === label.id)?.count ?? 0;
          const percent = denominator ? (n / denominator) * 100 : 0;
          return (
            <button
              key={label.id}
              className="bar-row"
              onClick={() => onSelect(label.id)}
              aria-label={`${label.name}: ${n} phản hồi, ${percent.toFixed(1)} phần trăm`}
            >
              <span className="bar-label">{label.name}</span>
              <span className="bar-track">
                <span style={{ width: `${percent}%` }} />
              </span>
              <span className="bar-value">
                {n} <small>{percent.toFixed(0)}%</small>
              </span>
            </button>
          );
        })}
      {!denominator && (
        <p className="muted small">
          Chưa có nhãn theo nguồn và bộ lọc đang chọn.
        </p>
      )}
    </section>
  );
}
