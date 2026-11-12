import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  api,
  getNetwork,
  getNetworkEvidence,
  post,
  ApiError,
} from "./api";
import type {
  Item,
  ItemPage,
  Job,
  Prediction,
  Profile,
  Summary,
} from "./types";
import { activeJob, labelName } from "./types";
import { AttributionTable } from "./AttributionTable";
import { ContributionDistribution } from "./ContributionDistribution";
import { TermNetwork } from "./TermNetwork";
import { SensitivityPanel } from "./SensitivityPanel";
import { validDemoTask } from "./demoPrediction";
import { useAttribution } from "./useAttribution";
import { defaultAttributionTarget } from "./attributionValidation";
import "./SentenceDemo.css";

export type SentenceDemoProps = {
  profiles?: Profile[];
  notify?: (text: string, error?: boolean) => void;
};

const formatPercent = (val: number): string =>
  (val * 100).toFixed(1).replace(".", ",");

export function SentenceDemo({
  profiles: initialProfiles,
  notify: parentNotify,
}: SentenceDemoProps) {
  const queryClient = useQueryClient();

  // Profile data can also be supplied by the app shell.
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api<Profile[]>("/profiles"),
    enabled: !initialProfiles,
    refetchInterval: 15000,
  });

  const profiles = initialProfiles ?? profilesQuery.data ?? [];

  // Profile state (defaults to "neu" if available, else first profile)
  const [profileId, setProfileId] = useState<string>("neu");
  const profile =
    profiles.find((p) => p.id === profileId) ?? profiles[0] ?? ({} as Profile);

  // Sync profileId once profiles load if "neu" isn't present
  useEffect(() => {
    if (profiles.length > 0 && !profiles.some((p) => p.id === profileId)) {
      setProfileId(profiles[0].id);
    }
  }, [profiles, profileId]);

  // Input states
  const [text, setText] = useState<string>("");
  const [submittedText, setSubmittedText] = useState<string>("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [currentRunId, setCurrentRunId] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Toast notification state
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback(
    (msg: string, isError = false) => {
      if (parentNotify) {
        parentNotify(msg, isError);
        return;
      }
      setToastMessage(msg);
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      toastTimerRef.current = setTimeout(() => {
        setToastMessage(null);
      }, 5000);
    },
    [parentNotify],
  );

  // Sensitivity explore state
  const [showExplore, setShowExplore] = useState<boolean>(false);
  const exploreContainerRef = useRef<HTMLDivElement>(null);

  // Overview, graph and evidence explain the same latest quick prediction.
  const labelSource = "ai" as const;

  // Evidence drill-down filter states
  const [evidenceSentimentId, setEvidenceSentimentId] = useState<number | null>(null);
  const [evidenceTopicId, setEvidenceTopicId] = useState<number | null>(null);
  const [networkSelection, setNetworkSelection] = useState<{
    networkId: string; type: "node" | "edge" | "community"; id: string;
    datasetId: string; labelSource: "ai" | "effective"; scopeToken: string;
  } | null>(null);
  const [evidenceFilterLabel, setEvidenceFilterLabel] = useState<string | null>(null);
  const [evidencePage, setEvidencePage] = useState<number>(1);
  const [networkVisible, setNetworkVisible] = useState(false);
  const [scopeNotice, setScopeNotice] = useState<string | null>(null);

  // Generation & abort refs
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const jobIdRef = useRef<string | null>(null);
  const busyGenerationRef = useRef<number | null>(null);

  const isCurrent = (generation: number) =>
    mountedRef.current && generation === generationRef.current;

  const cancelAbandonedJob = (id: string | null) => {
    if (id) void post(`/jobs/${id}/cancel`, {}).catch(() => {});
  };

  const job = useQuery({
    queryKey: ["quick-job", jobId],
    queryFn: ({ signal }) => api<Job>(`/jobs/${jobId}`, { signal }),
    enabled: !!jobId,
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: (q) =>
      ![404, 410].includes((q.state.error as ApiError | null)?.status ?? 0),
    refetchInterval: (q) =>
      q.state.error
        ? false
        : !q.state.data || activeJob(q.state.data.status)
          ? 1000
          : false,
  });

  const running =
    !!jobId && !job.isError && (!job.data || activeJob(job.data.status));
  const pollGone =
    job.isError && [404, 410].includes((job.error as ApiError).status ?? 0);
  const rawResult = job.data?.status === "completed" ? job.data.result : null;
  const item: Item | null =
    rawResult && "prediction" in rawResult ? (rawResult as Item) : null;
  const prediction: Prediction | null = item?.prediction ?? null;
  const sourceValid = !!(
    jobId &&
    currentRunId &&
    job.data?.kind === "quick" &&
    job.data.id === jobId &&
    job.data.run_id === currentRunId &&
    item &&
    prediction?.id &&
    item.id &&
    item.dataset_id &&
    item.revision_id &&
    Number.isInteger(item.revision) &&
    item.revision > 0 &&
    !item.stale &&
    item.text === submittedText &&
    prediction.run_id === currentRunId &&
    prediction.item_id === item.id &&
    prediction.revision_id === item.revision_id &&
    (!item.review_signals ||
      item.review_signals.prediction_id === prediction.id)
  );
  const sentimentValid =
    sourceValid && validDemoTask(prediction, profile, "sentiment");
  const topicValid = sourceValid && validDemoTask(prediction, profile, "topic");
  const validPrediction = sentimentValid && topicValid;
  const sourceDatasetId = validPrediction ? item!.dataset_id : "";
  const attribution = useAttribution(
    validPrediction && item && prediction && jobId ? { jobId, item, prediction, profile } : null,
    generationRef,
    mountedRef,
  );
  const { data: attributionData, loading: attributionLoading, error: attributionError,
    discard: discardAttribution } = attribution;


  const resetAnalysis = useCallback(() => {
    generationRef.current += 1;
    busyGenerationRef.current = null;

    const abandonedJob = jobIdRef.current;
    jobIdRef.current = null;
    cancelAbandonedJob(abandonedJob);
    if (abandonedJob) {
      void queryClient.cancelQueries({ queryKey: ["quick-job", abandonedJob] });
    }

    discardAttribution();
    setBusy(false);
    setJobId(null);
    setCurrentRunId("");
    setSubmittedText("");
    setShowExplore(false);
    setSubmitError(null);
  }, [queryClient, discardAttribution]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      cancelAbandonedJob(jobIdRef.current);
      if (jobIdRef.current) {
        void queryClient.cancelQueries({
          queryKey: ["quick-job", jobIdRef.current],
        });
      }
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [queryClient]);

  // Handle switching profile
  const handleProfileChange = (newProfileId: string) => {
    if (newProfileId === profileId) return;
    setProfileId(newProfileId);
    setEvidenceSentimentId(null);
    setEvidenceTopicId(null);
    setNetworkSelection(null);
    setEvidenceFilterLabel(null);
    resetAnalysis();
  };

  // Handle analyze click
  const handleAnalyze = async () => {
    if (
      !text.trim() ||
      running ||
      busy ||
      busyGenerationRef.current !== null ||
      !profile.model?.available
    )
      return;
    const submitted = text.trim();
    const submittedProfile = profileId;
    resetAnalysis();
    const generation = generationRef.current;
    busyGenerationRef.current = generation;
    setBusy(true);
    try {
      const response = await post<{ job_id: string; run_id: string }>(
        "/quick-analysis",
        {
          profile: submittedProfile,
          text: submitted,
        },
      );
      if (!isCurrent(generation)) {
        cancelAbandonedJob(response.job_id);
        return;
      }
      setSubmittedText(submitted);
      setCurrentRunId(response.run_id);
      jobIdRef.current = response.job_id;
      setJobId(response.job_id);
    } catch (e: unknown) {
      if (!isCurrent(generation)) return;
      const err = e as ApiError;
      setSubmitError(err.message || "Không thể gửi yêu cầu phân tích.");
    } finally {
      if (isCurrent(generation)) {
        busyGenerationRef.current = null;
        setBusy(false);
      }
    }
  };

  const handleCancel = async () => {
    if (!jobId) return;
    const generation = generationRef.current;
    try {
      await post(`/jobs/${jobId}/cancel`, {});
      if (!isCurrent(generation)) return;
      await job.refetch();
      if (isCurrent(generation)) showToast("Đã yêu cầu hủy phân tích câu.");
    } catch (e: unknown) {
      if (isCurrent(generation))
        showToast((e as ApiError).message || "Không thể hủy phân tích.", true);
    }
  };

  const handleRetryJob = async () => {
    if (!jobId || busyGenerationRef.current !== null) return;
    const generation = generationRef.current;
    const targetJobId = jobId;
    busyGenerationRef.current = generation;
    setBusy(true);
    setSubmitError(null);
    try {
      await post(`/jobs/${targetJobId}/retry`, {});
      if (!isCurrent(generation)) { cancelAbandonedJob(targetJobId); return; }
      await job.refetch();
    } catch (error) {
      if (isCurrent(generation)) setSubmitError((error as Error).message);
    } finally {
      if (isCurrent(generation)) { busyGenerationRef.current = null; setBusy(false); }
    }
  };

  // Summary query for Overview Section (P1)
  const summaryQuery = useQuery({
    queryKey: [
      "demo-dataset-summary",
      sourceDatasetId,
      currentRunId,
      labelSource,
      "current",
    ],
    queryFn: async ({ signal }) => {
      const result = await api<Summary>(
        `/datasets/${sourceDatasetId}/summary?label_source=${labelSource}&run_id=${currentRunId}`,
        { signal },
      );
      if (result.dataset_id !== sourceDatasetId || result.resolved_run_id !== currentRunId ||
          result.label_source !== labelSource || result.total !== 1) {
        throw new Error("Thống kê không khớp câu vừa phân tích. Hãy phân tích lại câu.");
      }
      return result;
    },
    enabled: !!sourceDatasetId,
    refetchOnWindowFocus: true,
  });
  const summary = summaryQuery.isError ? undefined : summaryQuery.data;
  const attention = summary?.attention;

  // Topic attention list sorted by negative_count descending
  const attentionTopics = useMemo(() => {
    if (!attention?.topics) return [];
    return [...attention.topics].sort(
      (a, b) => b.negative_count - a.negative_count,
    );
  }, [attention?.topics]);

  useEffect(() => {
    const element = document.getElementById("network");
    if (!element) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { setNetworkVisible(true); observer.disconnect(); }
    }, { rootMargin: "100px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A graph is a worker-owned snapshot, never a client-supplied list of member IDs.
  const networkQuery = useQuery({
    queryKey: ["demo-dataset-network", sourceDatasetId, currentRunId, labelSource, summary?.scope_token],
    queryFn: ({ signal }) =>
      getNetwork(sourceDatasetId, labelSource, currentRunId, signal),
    enabled: !!sourceDatasetId && !!summary && networkVisible,
    staleTime: 60000,
    retry: (failureCount, error) => failureCount < 2 && ![404, 409, 410, 422].includes((error as ApiError).status ?? 0),
    refetchInterval: (query) => query.state.error ? false : ["queued", "running"].includes(query.state.data?.status ?? "") ? 500 : false,
  });
  const networkData = networkQuery.data?.scope_token === summary?.scope_token &&
    networkQuery.data?.dataset_id === sourceDatasetId && networkQuery.data?.label_source === labelSource
    ? networkQuery.data : null;
  const activeNetworkSelection = networkSelection?.datasetId === sourceDatasetId &&
    networkSelection.labelSource === labelSource && networkSelection.scopeToken === summary?.scope_token
    ? networkSelection : null;
  useEffect(() => {
    if (!networkQuery.data || !summary?.scope_token || networkQuery.data.scope_token === summary.scope_token) return;
    setScopeNotice("Dữ liệu đã đổi. Đang tải lại thống kê để khớp mạng từ.");
    void queryClient.invalidateQueries({ queryKey: ["demo-dataset-summary", sourceDatasetId] });
  }, [networkQuery.data, summary?.scope_token, sourceDatasetId, queryClient]);

  // Evidence Items Query
  const evidenceQuery = useQuery({
    queryKey: [
      "demo-evidence-items",
      sourceDatasetId,
      labelSource,
      evidenceSentimentId,
      evidenceTopicId,
      activeNetworkSelection,
      evidencePage,
      summary?.scope_token,
    ],
    queryFn: async ({ signal }) => {
      if (!sourceDatasetId) return null;
      if (activeNetworkSelection) {
        return getNetworkEvidence(activeNetworkSelection.networkId, activeNetworkSelection.type, activeNetworkSelection.id, evidencePage, 10, signal);
      }
      const params = new URLSearchParams({
        label_source: labelSource,
        page: String(evidencePage),
        page_size: "10",
      });
      if (summary?.scope_token) params.set("scope_token", summary.scope_token);
      if (summary?.resolved_run_id)
        params.set("expected_run_id", summary.resolved_run_id);
      if (summary?.revision_scope === "run" && summary.resolved_run_id) {
        params.set("run_id", summary.resolved_run_id);
      }
      if (evidenceSentimentId !== null)
        params.set("sentiment", String(evidenceSentimentId));
      if (evidenceTopicId !== null) params.set("topic", String(evidenceTopicId));

      return api<ItemPage>(`/datasets/${sourceDatasetId}/items?${params}`, {
        signal,
      });
    },
    enabled: !!sourceDatasetId && !!summary,
    staleTime: 5000,
    retry: (failureCount, error) => failureCount < 2 && ![404, 409, 410, 422].includes((error as ApiError).status ?? 0),
  });

  useEffect(() => {
    setEvidencePage(1);
    setEvidenceSentimentId(null);
    setEvidenceTopicId(null);
    setNetworkSelection(null);
    setEvidenceFilterLabel(null);
  }, [sourceDatasetId, labelSource, summary?.scope_token]);

  useEffect(() => {
    if ((evidenceQuery.error as ApiError | null)?.status !== 409) return;
    setScopeNotice("Dữ liệu hoặc nhãn đã đổi. Đã tải lại thống kê và mạng từ.");
    setNetworkSelection(null);
    setEvidenceSentimentId(null);
    setEvidenceTopicId(null);
    setEvidenceFilterLabel(null);
    setEvidencePage(1);
    void queryClient.invalidateQueries({ queryKey: ["demo-dataset-summary", sourceDatasetId] });
    void queryClient.invalidateQueries({ queryKey: ["demo-dataset-network", sourceDatasetId] });
  }, [evidenceQuery.error, queryClient, sourceDatasetId]);

  // Handle clearing evidence filters
  const handleClearFilters = () => {
    setEvidenceSentimentId(null);
    setEvidenceTopicId(null);
    setNetworkSelection(null);
    setEvidenceFilterLabel(null);
    setEvidencePage(1);
  };

  const hasActiveFilters =
    evidenceSentimentId !== null ||
    evidenceTopicId !== null ||
    networkSelection !== null;

  // Predictions labels and values
  const sentimentLabelName =
    sentimentValid && prediction
      ? labelName(profile, "sentiment", prediction.sentiment.label_id)
      : "Không đủ dữ liệu cảm xúc";
  const sentimentScoreVal =
    sentimentValid && prediction
      ? prediction.sentiment.scores[prediction.sentiment.label_id]
      : null;
  const sentimentKey = profile.sentiment?.find((label) => label.id === prediction?.sentiment.label_id)?.key.toLowerCase();
  const sentimentClass = sentimentKey === "negative" ? "negative-text" : sentimentKey === "positive" ? "positive-text" :
    sentimentKey === "toxic" ? "toxic-text" : "muted-text";

  const topicLabelName =
    topicValid && prediction
      ? labelName(profile, "topic", prediction.topic.label_id)
      : "Không đủ dữ liệu chủ đề";
  const topicScoreVal =
    topicValid && prediction
      ? prediction.topic.scores[prediction.topic.label_id]
      : null;
  const scoreText = (value: number | null) =>
    value === null ? "—" : formatPercent(value);

  const currentTarget = attributionData?.method?.target ??
    (validPrediction && prediction ? defaultAttributionTarget(prediction, profile) : null);
  const attributionTargetLabelName = currentTarget?.kind === "label_score"
    ? labelName(profile, "sentiment", currentTarget.label_id) : "Tích cực / Tiêu cực";
  const isPolarity = !currentTarget || currentTarget.kind === "polarity_margin";
  const scrollSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
  };

  return (
    <div className="sentence-demo-root">
      <a
        className="skip-link"
        href="#main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main")?.focus();
        }}
      >
        Đến nội dung chính
      </a>

      {/* Header */}
      <header className="app-header">
        <div className="header-inner">
          <a
            className="brand"
            href="#analysis"
            onClick={(event) => { event.preventDefault(); scrollSection("analysis"); }}
            aria-label="NEU-ESC, phân tích phản hồi"
          >
            <span className="brand-mark" aria-hidden="true">
              N
            </span>
            <strong>
              NEU<span>–</span>ESC
            </strong>
          </a>
          <nav aria-label="Nội dung trang">
            <a href="#analysis" className="nav-current" onClick={(event) => { event.preventDefault(); scrollSection("analysis"); }}>
              Phân tích câu
            </a>
            <a href="#overview" onClick={(event) => { event.preventDefault(); scrollSection("overview"); }}>Câu vừa phân tích</a>
            <a href="#network" onClick={(event) => { event.preventDefault(); setNetworkVisible(true); scrollSection("network"); }}>Mạng từ</a>
          </nav>
          <div className="profile-pill" style={{ marginLeft: "auto" }}>
            <label htmlFor="schema-select" className="sr-only">
              Hệ nhãn
            </label>
            <select
              id="schema-select"
              value={profileId}
              onChange={(e) => handleProfileChange(e.target.value)}
              style={{
                fontSize: "14px",
                padding: "4px 8px",
                border: "1px solid var(--line)",
                borderRadius: "6px",
                background: "white",
              }}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  Tiếng Việt · {p.id.toUpperCase()} ({p.name})
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main id="main" tabIndex={-1}>
        {/* Section: Analysis Surface */}
        <section
          id="analysis"
          className="analysis-section"
          aria-labelledby="page-title"
        >
          <div className="page-heading">
            <h1 id="page-title">Phân tích phản hồi</h1>
            <span className="quiet-label">Cảm xúc &amp; chủ đề</span>
          </div>

          <div className="analysis-surface">
            {/* Input Pane */}
            <form
              id="analysis-form"
              className="input-pane"
              onSubmit={(e) => {
                e.preventDefault();
                void handleAnalyze();
              }}
            >
              <label htmlFor="sentence" className="pane-heading">
                Nội dung phản hồi
              </label>
              <textarea
                id="sentence"
                spellCheck={false}
                maxLength={5000}
                placeholder="Nhập phản hồi tiếng Việt…"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  resetAnalysis();
                }}
              />

              <div className="input-actions">
                <button
                  type="submit"
                  id="analyze"
                  className="button-primary"
                  disabled={
                    !text.trim() || running || busy || !profile.model?.available
                  }
                >
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="m13 3-8 10h6l-1 8 9-11h-6z" />
                  </svg>
                  <span>
                    {busy
                      ? "Đang gửi…"
                      : running
                        ? "Đang phân tích…"
                        : "Phân tích"}
                  </span>
                  <span aria-hidden="true">→</span>
                </button>

                <button
                  type="button"
                  id="clear"
                  className="button-plain"
                  onClick={() => {
                    setText("");
                    resetAnalysis();
                    document.getElementById("sentence")?.focus();
                  }}
                >
                  Xóa
                </button>

                <span id="character-count" className="character-count">
                  {text.length} / 5.000 ký tự
                </span>
              </div>

              {submitError && (
                <div
                  className="input-status notice error"
                  role="alert"
                  style={{ marginTop: 12 }}
                >
                  <strong>Lỗi gửi phân tích: </strong>
                  <span>{submitError}</span>
                </div>
              )}

              {profile.model && !profile.model.available && (
                <div
                  className="notice warning input-notice"
                  role="alert"
                  style={{ marginTop: 12 }}
                >
                  <strong>Model chưa sẵn sàng: </strong>
                  <span>
                    {profile.model.reason ||
                      "Cần cài bộ model hợp lệ để phân tích."}
                  </span>
                </div>
              )}
            </form>

            {/* Prediction Pane */}
            <section
              className="prediction-pane"
              aria-labelledby="prediction-heading"
              aria-busy={running}
            >
              <div className="pane-heading-row">
                <h2 id="prediction-heading" className="pane-heading">
                  Kết quả phân tích
                </h2>
                {prediction ? (
                  <span className="sample-label">
                    {prediction.model_id}
                  </span>
                ) : (
                  <span className="sample-label">Kết quả AI</span>
                )}
              </div>

              {/* Empty State */}
              {!jobId && !prediction && !running && (
                <div id="empty-state" className="prediction-empty">
                  <span className="empty-symbol" aria-hidden="true">
                    ↗
                  </span>
                  <p>Kết quả sẽ xuất hiện ở đây sau khi phân tích.</p>
                </div>
              )}

              {/* Waiting State */}
              {running && (
                <div
                  id="waiting-state"
                  className="waiting-state"
                  role="status"
                  style={{ padding: "24px 0" }}
                >
                  <div
                    className="wait-heading"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 12,
                    }}
                  >
                    <span className="pulse-dot" aria-hidden="true" />
                    <h3 style={{ fontSize: "16px", fontWeight: 600 }}>
                      {job.data?.status === "loading_model"
                        ? "Đang nạp model vào bộ nhớ…"
                        : "Đang phân tích câu…"}
                    </h3>
                  </div>
                  <p style={{ fontSize: "14px", color: "var(--muted)" }}>
                    Lần phân tích đầu có thể mất vài giây để model PhoBERT nạp vào
                    bộ nhớ máy.
                  </p>
                  <div style={{ marginTop: 16 }}>
                    <button
                      type="button"
                      id="cancel"
                      className="button-secondary"
                      disabled={job.data?.cancel_requested}
                      onClick={() => void handleCancel()}
                    >
                      Hủy phân tích
                    </button>
                  </div>
                </div>
              )}

              {/* Polling Error */}
              {job.isError && (
                <div
                  className="notice error"
                  role="alert"
                  id="poll-error"
                  style={{ marginTop: 12 }}
                >
                  <strong>
                    {pollGone
                      ? "Tác vụ không còn khả dụng hoặc đã hết hạn."
                      : "Chưa đọc được trạng thái phân tích."}
                  </strong>
                  <span>{(job.error as Error).message}</span>
                  <div>
                    <button type="button" className="button-secondary" onClick={() => {
                      if (pollGone) void handleAnalyze(); else void job.refetch();
                    }}>{pollGone ? "Phân tích lại câu" : "Thử đọc lại trạng thái"}</button>
                  </div>
                </div>
              )}

              {jobId && !job.isError && job.data && ["failed", "cancelled", "interrupted", "completed_with_errors"].includes(job.data.status) && (
                <div className="notice warning" role="status">
                  <p>Phân tích chưa hoàn tất. {job.data.error ?? "Có thể chạy lại tác vụ."}</p>
                  <button type="button" className="button-secondary" disabled={busy} onClick={() => void handleRetryJob()}>
                    Chạy lại tác vụ này
                  </button>
                </div>
              )}

              {/* Actual Prediction Result Content */}
              {prediction && (
                <div id="result-content" aria-live="polite">
                  {!validPrediction && (
                    <div
                      className="notice error"
                      role="alert"
                      style={{ marginTop: 8 }}
                    >
                      Dự đoán thiếu điểm hợp lệ hoặc không khớp schema/model hiện
                      tại.
                    </div>
                  )}

                  {prediction.truncated && (
                    <div
                      className="notice warning"
                      role="alert"
                      style={{ marginTop: 8 }}
                    >
                      <strong>Đầu vào bị cắt ngắn: </strong>
                      <span>
                        Model cắt văn bản tại 128 token. Kết quả dựa trên phần
                        đã đọc.
                      </span>
                    </div>
                  )}

                  <div className="prediction-headlines">
                    <div>
                      <span className="field-label">Cảm xúc</span>
                      <div className="prediction-line">
                        <strong
                          id="sentiment"
                          className={sentimentClass}
                        >
                          {sentimentLabelName}
                        </strong>
                        <span className="prediction-percent" id="sentiment-score">
                          {scoreText(sentimentScoreVal)}
                          <small>%</small>
                        </span>
                      </div>
                    </div>
                    <div>
                      <span className="field-label">Chủ đề</span>
                      <div className="prediction-line">
                        <strong id="topic">{topicLabelName}</strong>
                        <span className="prediction-percent" id="topic-score">
                          {scoreText(topicScoreVal)}
                          <small>%</small>
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Score Stack Bar */}
                  {sentimentValid && (
                    <div
                      className="score-stack"
                      aria-label="Phân bố điểm cảm xúc"
                    >
                      {profile.sentiment.map((label) => {
                        const score = prediction.sentiment.scores[label.id] ?? 0;
                        const key = label.key.toLowerCase();
                        const segClass =
                          key === "negative"
                            ? "segment-negative"
                            : key === "positive"
                              ? "segment-positive"
                              : key === "toxic"
                                ? "segment-toxic"
                                : "segment-neutral";
                        return (
                          <span
                            key={label.id}
                            className={segClass}
                            style={{ width: `${Math.max(1, score * 100)}%` }}
                            title={`${label.name}: ${formatPercent(score)}%`}
                          />
                        );
                      })}
                    </div>
                  )}

                  {/* Prediction Legend */}
                  {sentimentValid && (
                    <div className="prediction-legend" id="scores">
                      {profile.sentiment.map((label) => {
                        const score = prediction.sentiment.scores[label.id] ?? 0;
                        const key = label.key.toLowerCase();
                        const dotClass =
                          key === "negative"
                            ? "negative-dot"
                            : key === "positive"
                              ? "positive-dot"
                              : key === "toxic"
                                ? "toxic-dot"
                                : "neutral-dot";
                        return (
                          <span key={label.id} className="score-row">
                            <i className={`dot ${dotClass}`} />
                            <span>{label.name}</span>
                            <strong style={{ marginLeft: 4 }}>{formatPercent(score)}%</strong>
                          </span>
                        );
                      })}
                    </div>
                  )}

                  {validPrediction && <p className="chart-note">Điểm softmax chưa hiệu chuẩn, không phải xác suất dự đoán đúng.</p>}
                  {validPrediction && (item?.review_signals?.sentiment.state === "flagged" || item?.review_signals?.topic.state === "flagged") && (
                    <p className="notice warning">Điểm mô hình còn khó phân biệt; nên rà soát cảm xúc hoặc chủ đề.</p>
                  )}
                  {/* Topic Details Accordion */}
                  {topicValid && (
                    <details className="topic-details" open>
                      <summary>
                        Xem điểm {profile.topic.length} chủ đề{" "}
                        <span aria-hidden="true">⌄</span>
                      </summary>
                      <div id="topic-scores" className="topic-scores">
                        {profile.topic.map((label) => {
                          const score = prediction.topic.scores[label.id] ?? 0;
                          return (
                            <div className="topic-score score-row" key={label.id}>
                              <span>{label.name}</span>
                              <div className="topic-score-track score-track">
                                <span
                                  style={{
                                    display: "block",
                                    height: "100%",
                                    width: `${Math.min(100, Math.max(0, score * 100))}%`,
                                  }}
                                />
                              </div>
                              <strong>{formatPercent(score)}%</strong>
                            </div>
                          );
                        })}
                      </div>
                    </details>
                  )}
                </div>
              )}
            </section>
          </div>
        </section>

        {/* Section: Word Analysis & Attribution (P0 - R04, R05, R06, R07) */}
        <section
          id="word-analysis"
          className="word-section"
          aria-labelledby="words-heading"
        >
          <div className="section-heading">
            <div>
              <h2 id="words-heading">Từ ngữ &amp; đóng góp</h2>
              <p>Đối chiếu từng cụm từ với điểm cảm xúc.</p>
            </div>
            <div className="direction-legend">
              {isPolarity ? (
                <>
                  <span>
                    <i className="dot positive-dot" />
                    Nghiêng tích cực
                  </span>
                  <span>
                    <i className="dot negative-dot" />
                    Nghiêng tiêu cực
                  </span>
                </>
              ) : (
                <>
                  <span>
                    <i className="dot blue-dot" />
                    Tăng điểm {attributionTargetLabelName}
                  </span>
                  <span>
                    <i className="dot toxic-dot" />
                    Giảm điểm {attributionTargetLabelName}
                  </span>
                </>
              )}
            </div>
          </div>

          {attributionLoading && (
            <div
              className="attribution-surface"
              role="status"
              aria-live="polite"
              style={{ padding: "36px 24px", textAlign: "center" }}
            >
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <span className="pulse-dot" aria-hidden="true" />
                <strong style={{ fontSize: "16px" }}>
                  Đang tính trọng số Shapley cho từng cụm từ…
                </strong>
              </div>
              <p
                style={{
                  color: "var(--muted)",
                  fontSize: "14px",
                  marginTop: 8,
                }}
              >
                Ước lượng bằng 8 hoán vị trên mô hình local.
              </p>
              <div style={{ marginTop: 14 }}>
                <button
                  type="button"
                  className="button-plain"
                  onClick={() => void attribution.cancel()}
                >
                  Hủy tính toán
                </button>
              </div>
            </div>
          )}

          {!attributionLoading && attributionError && (
            <div
              className="notice error"
              role="alert"
              style={{ padding: "20px 24px", borderRadius: "8px" }}
            >
              <strong>Lỗi tính đóng góp từ ngữ: </strong>
              <span>{attributionError}</span>
              {jobId && prediction && prediction.id && attribution.status !== "source_error" && (
                <div style={{ marginTop: 10 }}>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={attribution.retry}
                  >
                    Thử lại tính đóng góp
                  </button>
                </div>
              )}
            </div>
          )}

          {!attributionLoading && !attributionError && attributionData && (
            <AttributionTable
              key={attributionData.attribution_id}
              rawText={item?.text ?? ""}
              attribution={attributionData}
              targetLabelName={attributionTargetLabelName}
            />
          )}

          {!attributionLoading &&
            !attributionError &&
            !attributionData &&
            !prediction && (
              <div id="attribution-empty" className="attribution-empty">
                Phân tích một phản hồi để xem các cụm từ và đóng góp.
              </div>
            )}
        </section>

        {/* Section: Sensitivity Exploration */}
        {item && validPrediction && (
          <section
            className="explore-panel"
            aria-labelledby="explore-heading"
            style={{ marginTop: 32 }}
          >
            <div className="explore-intro">
              <span className="explore-icon" aria-hidden="true">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.6"
                >
                  <path d="M4 6h11m-4-4 4 4-4 4M20 18H9m4-4-4 4 4 4M4 12v6h2m14-6V6h-2" />
                </svg>
              </span>
              <div>
                <h2 id="explore-heading" style={{ fontSize: "1.125rem" }}>
                  Điều gì xảy ra nếu bỏ một cụm từ?
                </h2>
                <p style={{ fontSize: "14px", color: "var(--muted)" }}>
                  So sánh câu gốc và câu biến thể để kiểm tra trực tiếp độ nhạy
                  của mô hình.
                </p>
              </div>
              <button
                id="toggle-explore"
                type="button"
                className="button-secondary"
                aria-expanded={showExplore}
                aria-controls="explore-body"
                onClick={() => setShowExplore((prev) => !prev)}
              >
                {showExplore ? "Ẩn thử nghiệm" : "Khám phá độ nhạy"}{" "}
                <span aria-hidden="true">↗</span>
              </button>
            </div>

            {showExplore && (
              <div
                id="explore-body"
                ref={exploreContainerRef}
                style={{ marginTop: 16 }}
              >
                <SensitivityPanel
                  embedded
                  item={item}
                  profile={profile}
                  runId={job.data?.run_id ?? currentRunId}
                  editingSourceText={false}
                  onReloadItem={() => {
                    if (jobIdRef.current === jobId) void job.refetch();
                  }}
                />
              </div>
            )}
          </section>
        )}

        {/* Section: Overview (P1 - R08) */}
        <section
          id="overview"
          className="overview-section"
          aria-labelledby="overview-heading"
        >
          <div className="section-heading">
            <div>
              <h2 id="overview-heading">Câu vừa phân tích</h2>
              <p>
                {summary
                  ? "Thống kê và mạng từ chỉ dùng câu vừa phân tích, không cộng dồn."
                  : "Phân tích một câu để xem thống kê và mạng từ của câu đó."}
              </p>
            </div>
            <div className="dataset-badge">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="4" y="4" width="16" height="16" rx="2" />
                <path d="M4 10h16M10 10v10" />
              </svg>
              <span>{profile.name}</span>
            </div>
          </div>

          {!sourceDatasetId ? (
            <div className="attribution-empty">
              <h3>Chưa có câu đã phân tích</h3>
              <p style={{ marginTop: 6, color: "var(--muted)" }}>
                Nhập câu ở trên rồi bấm Phân tích. Kết quả mới sẽ thay thế câu trước.
              </p>
            </div>
          ) : (
            <div className="overview-surface">
              {/* Donut Pane */}
              <section
                className="distribution-pane"
                aria-labelledby="distribution-heading"
              >
                <div className="subheading-row">
                  <h3 id="distribution-heading">Tỷ trọng đóng góp của cụm từ</h3>
                </div>
                <ContributionDistribution
                  attribution={attributionData}
                  profile={profile}
                  loading={attributionLoading}
                  error={attributionError}
                />
              </section>

              {/* Topic Attention Pane */}
              <section
                className="attention-pane"
                aria-labelledby="attention-heading"
              >
                <div className="subheading-row">
                  <h3 id="attention-heading">Chủ đề cần chú ý</h3>
                  <span>Tiêu cực / tổng</span>
                </div>
                {summaryQuery.isError ? <div className="notice error">
                  <strong>Lỗi tải thống kê: </strong><span>{(summaryQuery.error as Error).message}</span>
                </div> : summaryQuery.isPending || summaryQuery.isFetching ? <p className="chart-note" role="status">
                  Đang tải thống kê của câu vừa phân tích…
                </p> : <>
                <p className="attention-denominator chart-note" data-testid="attention-status">
                  Đủ hai nhãn: {attention?.eligible_count ?? 0} / {attention?.filtered_count ?? summary?.total ?? 0}.
                  {summary?.run_status ? ` Run: ${summary.run_status}.` : " Chưa có lượt phân tích."}
                  {summary && <span> {Math.max(0, summary.total - (summary.denominator?.topic ?? 0))} thiếu chủ đề · {Math.max(0, summary.total - (summary.denominator?.sentiment ?? 0))} thiếu cảm xúc · {summary.errors} lỗi · {Math.max(0, summary.total - summary.processed - summary.errors)} chưa xử lý</span>}
                </p>
                <div className="topic-attention" id="topic-attention">
                  {attentionTopics.length === 0 ? (
                    <p className="chart-note" style={{ padding: 12 }}>
                      Chưa có phản hồi nào đủ nhãn chủ đề và cảm xúc.
                    </p>
                  ) : (
                    attentionTopics.map((t) => {
                      const isSelected = evidenceTopicId === t.topic_id;
                      const pct =
                        t.eligible_count > 0
                          ? (t.negative_count / t.eligible_count) * 100
                          : 0;
                      return (
                        <button
                          type="button"
                          key={t.topic_id}
                          className="attention-row"
                          disabled={t.negative_count === 0}
                          aria-pressed={isSelected}
                          style={{
                            background: isSelected ? "#eef6f1" : undefined,
                            outline: isSelected
                              ? "2px solid var(--teal)"
                              : undefined,
                          }}
                          onClick={() => {
                            setNetworkSelection(null);
                            if (evidenceTopicId === t.topic_id) {
                              setEvidenceTopicId(null);
                              setEvidenceSentimentId(null);
                              setEvidenceFilterLabel(null);
                            } else {
                              setEvidenceTopicId(t.topic_id);
                              setEvidenceSentimentId(attention?.negative_label_id ?? null);
                              setEvidenceFilterLabel(
                                `Chủ đề: ${labelName(
                                  profile,
                                  "topic",
                                  t.topic_id,
                                )} (${t.negative_count} tiêu cực)`,
                              );
                            }
                            setEvidencePage(1);
                          }}
                        >
                          <div className="attention-row-head">
                            <strong>
                              {labelName(profile, "topic", t.topic_id)}
                            </strong>
                            <span>
                              <b>{t.negative_count}</b> / {t.eligible_count}
                              <small>
                                {" "}
                                ({t.eligible_count > 0 ? `${pct.toFixed(1).replace(".", ",")}%` : "—"})
                              </small>
                            </span>
                            <span
                              className="attention-chevron"
                              aria-hidden="true"
                            >
                              ›
                            </span>
                          </div>
                          <div className="attention-track">
                            <span
                              style={{
                                width: `${Math.min(100, Math.max(0, pct))}%`,
                                background: "#c76b5d",
                              }}
                            />
                          </div>
                          <div className="attention-row-meta">
                            <span>
                              {t.topic_count} phản hồi · {t.missing_sentiment_count} thiếu cảm xúc
                            </span>
                            {t.toxic_count !== null && t.toxic_count > 0 && (
                              <span className="toxic-note">
                                Toxic: {t.toxic_count}
                              </span>
                            )}
                            {t.small_sample && <span>(Ít dữ liệu)</span>}
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
                <p className="chart-note">
                  Xếp theo số phản hồi tiêu cực. Toxic được tính riêng.
                </p>
                </>}
              </section>
            </div>
          )}
        </section>

        {/* Section: Word Co-occurrence Network (P2 - R09) */}
        <section
          id="network"
          className="network-section"
          aria-labelledby="network-heading"
        >
          <div className="section-heading">
            <div>
              <h2 id="network-heading">Các từ đang kết nối với nhau</h2>
              <p>Khám phá những cụm từ cùng xuất hiện trong phản hồi.</p>
            </div>
            <span className="network-caption" id="network-count">
              {networkData
                ? `${networkData.nodes.length} từ · ${networkData.edges.length} liên kết`
                : ""}
            </span>
          </div>

          {!sourceDatasetId ? (
            <div className="attribution-empty">
              Phân tích một câu ở trên để xem các từ kết nối trong câu đó.
            </div>
          ) : !networkVisible ? (
            <button type="button" className="button-secondary" onClick={() => setNetworkVisible(true)}>Tải mạng từ ngữ</button>
          ) : networkQuery.isError || networkQuery.data?.status === "failed" ? (
            <div className="notice error" role="alert">
              Không thể tải mạng từ ngữ. {networkQuery.data?.error?.message ?? (networkQuery.error as Error | null)?.message}
              <button type="button" onClick={() => void networkQuery.refetch()}>Thử lại mạng từ</button>
            </div>
          ) : (
            <TermNetwork
              key={networkData?.network_id ?? "empty"}
              network={networkData}
              loading={networkQuery.isLoading || ["queued", "running"].includes(networkData?.status ?? "")}
              onFilterEvidence={(type, id, label) => {
                if (!networkData?.network_id || !summary?.scope_token) return;
                setEvidenceSentimentId(null);
                setEvidenceTopicId(null);
                setNetworkSelection({ networkId: networkData.network_id, type, id, datasetId: sourceDatasetId,
                  labelSource, scopeToken: summary.scope_token });
                setEvidenceFilterLabel(label);
                setEvidencePage(1);
                document
                  .getElementById("evidence")
                  ?.scrollIntoView({ behavior: "smooth" });
              }}
            />
          )}
        </section>

        {/* Section: Evidence Drill-Down */}
        {sourceDatasetId && (
          <section
            id="evidence"
            className="evidence-section"
            aria-labelledby="evidence-heading"
          >
            <div className="section-heading">
              <div>
                <h2 id="evidence-heading">Phản hồi để đối chiếu</h2>
                <p id="evidence-description">
                  {evidenceFilterLabel
                    ? `Đang lọc: ${evidenceFilterLabel}`
                    : "Nội dung của câu vừa phân tích."}
                </p>
              </div>
              {hasActiveFilters && (
                <button
                  type="button"
                  id="clear-filters"
                  className="button-secondary"
                  onClick={handleClearFilters}
                >
                  Bỏ bộ lọc <span aria-hidden="true">×</span>
                </button>
              )}
            </div>

            {hasActiveFilters && (
              <div className="active-filters" id="active-filters">
                {evidenceSentimentId !== null && (
                  <span className="filter-chip">
                    Cảm xúc:{" "}
                    {labelName(profile, "sentiment", evidenceSentimentId)}
                  </span>
                )}
                {evidenceTopicId !== null && (
                  <span className="filter-chip">
                    Chủ đề: {labelName(profile, "topic", evidenceTopicId)}
                  </span>
                )}
                {networkSelection && (
                  <span className="filter-chip">
                    {evidenceFilterLabel}
                  </span>
                )}
              </div>
            )}

            {scopeNotice && <p className="notice warning" role="status">{scopeNotice}</p>}
            {evidenceQuery.isLoading ? (
              <div className="no-evidence">Đang tải danh sách phản hồi…</div>
            ) : evidenceQuery.isError ? (
              <div className="notice error">
                Không thể tải phản hồi: {(evidenceQuery.error as Error).message}
              </div>
            ) : !evidenceQuery.data ||
              evidenceQuery.data.items.length === 0 ? (
              <div className="no-evidence">
                Không tìm thấy phản hồi nào phù hợp với bộ lọc hiện tại.
              </div>
            ) : (
              <>
                <div className="evidence-list" id="evidence-list">
                  {evidenceQuery.data.items.map((row) => {
                    const sentimentLabel = labelName(
                      profile,
                      "sentiment",
                      labelSource === "ai" ? row.prediction?.sentiment.label_id : row.effective.sentiment,
                    );
                    const topicLabel = labelName(
                      profile,
                      "topic",
                      labelSource === "ai" ? row.prediction?.topic.label_id : row.effective.topic,
                    );
                    const isNeg =
                      sentimentLabel.toLowerCase().includes("tiêu cực") ||
                      sentimentLabel.toLowerCase().includes("negative");
                    const isPos =
                      sentimentLabel.toLowerCase().includes("tích cực") ||
                      sentimentLabel.toLowerCase().includes("positive");
                    const isTox =
                      sentimentLabel.toLowerCase().includes("toxic") ||
                      sentimentLabel.toLowerCase().includes("độc hại");
                    const badgeClass = isNeg
                      ? "badge-negative"
                      : isPos
                        ? "badge-positive"
                        : isTox
                          ? "badge-toxic"
                          : "badge-neutral";

                    return (
                      <article className="evidence-row" key={row.id}>
                        <span className="evidence-id">#{row.source_row}</span>
                        <div className="evidence-text">
                          <p>{row.text}</p>
                        </div>
                        <div className="evidence-meta">
                          <span className={`sentiment-badge ${badgeClass}`}>
                            {sentimentLabel}
                          </span>
                          <span
                            style={{
                              fontSize: "14px",
                              color: "var(--muted)",
                            }}
                          >
                            {topicLabel}
                          </span>
                        </div>
                      </article>
                    );
                  })}
                </div>

                {evidenceQuery.data.total > 10 && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      gap: 16,
                      marginTop: 16,
                    }}
                  >
                    <button
                      type="button"
                      className="button-plain"
                      disabled={evidencePage <= 1}
                      onClick={() => setEvidencePage((p) => Math.max(1, p - 1))}
                    >
                      ← Trang trước
                    </button>
                    <span
                      style={{ fontSize: "14px", color: "var(--muted)" }}
                    >
                      Trang {evidencePage} /{" "}
                      {Math.ceil(evidenceQuery.data.total / 10)} (Tổng{" "}
                      {evidenceQuery.data.total})
                    </span>
                    <button
                      type="button"
                      className="button-plain"
                      disabled={
                        evidencePage >= Math.ceil(evidenceQuery.data.total / 10)
                      }
                      onClick={() => setEvidencePage((p) => p + 1)}
                    >
                      Trang sau →
                    </button>
                  </div>
                )}
              </>
            )}

          </section>
        )}

        {/* Page Footer */}
        <footer className="page-footer">
          <span>
            NEU–ESC <span className="footer-divider">/</span> Phân tích phản hồi
          </span>
          <a href="#analysis">Về đầu trang ↑</a>
        </footer>
      </main>

      {/* Toast Notification */}
      {toastMessage && (
        <div id="toast" role="status" aria-live="polite">
          {toastMessage}
        </div>
      )}
    </div>
  );
}

export default SentenceDemo;
