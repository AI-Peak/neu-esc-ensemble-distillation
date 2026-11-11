import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getExplanation, post, ApiError } from "./api";
import type {
  Dataset,
  ExplanationResponse,
  Item,
  ItemPage,
  Job,
  Prediction,
  Profile,
  Summary,
} from "./types";
import { activeJob, labelName } from "./types";
import { SensitivityPanel } from "./SensitivityPanel";
import { TopicAttention } from "./TopicAttention";
import { validDemoTask } from "./demoPrediction";
import "./SentenceDemo.css";

export type SentenceDemoProps = {
  profiles?: Profile[];
  datasets?: Dataset[];
  notify?: (text: string, error?: boolean) => void;
};

const SAMPLE_SENTENCES = [
  {
    name: "Dịch vụ sinh viên",
    text: "Cổng đăng ký học phần báo lỗi liên tục, mình chưa đăng ký được môn bắt buộc.",
  },
  {
    name: "Trải nghiệm học tập",
    text: "Giảng viên giải thích bài tập rõ ràng, mình hiểu bài dễ hơn.",
  },
  {
    name: "Một thông báo",
    text: "Thư viện mở cửa đến chín giờ tối.",
  },
];

const formatPercent = (val: number): string =>
  (val * 100).toFixed(1).replace(".", ",");

export function SentenceDemo({
  profiles: initialProfiles,
  datasets: initialDatasets,
  notify: parentNotify,
}: SentenceDemoProps) {
  const queryClient = useQueryClient();

  // Queries for profiles & datasets if not passed via props
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: () => api<Profile[]>("/profiles"),
    enabled: !initialProfiles,
    refetchInterval: 15000,
  });

  const datasetsQuery = useQuery({
    queryKey: ["datasets"],
    queryFn: () => api<Dataset[]>("/datasets"),
    enabled: !initialDatasets,
  });

  const profiles = initialProfiles ?? profilesQuery.data ?? [];
  const datasets = initialDatasets ?? datasetsQuery.data ?? [];

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

  // Explanation states (Layer 2)
  const [explanation, setExplanation] = useState<ExplanationResponse | null>(null);
  const [explaining, setExplaining] = useState<boolean>(false);
  const [explanationError, setExplanationError] = useState<{
    status?: number;
    message: string;
  } | null>(null);

  // Sensitivity explore state
  const [showExplore, setShowExplore] = useState<boolean>(false);
  const exploreContainerRef = useRef<HTMLDivElement>(null);

  // Layer 3 (Decision support) states
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [labelSource, setLabelSource] = useState<"effective" | "ai">("effective");
  const [drillDownTopicId, setDrillDownTopicId] = useState<number | null>(null);
  const [drillDownPage, setDrillDownPage] = useState<number>(1);

  // Quick add state
  const [quickAddTarget, setQuickAddTarget] = useState<string>("");
  const [addingToDataset, setAddingToDataset] = useState<boolean>(false);
  const [addedToDataset, setAddedToDataset] = useState<boolean>(false);

  // A generation owns every async callback (including POST success/error/finally).
  const generationRef = useRef(0);
  const mountedRef = useRef(true);
  const jobIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastExplainedKeyRef = useRef("");
  const busyGenerationRef = useRef<number | null>(null);
  const explanationPendingRef = useRef(false);
  const isCurrent = (generation: number) => mountedRef.current && generation === generationRef.current;
  const cancelAbandonedJob = (id: string | null) => {
    if (id) void post(`/jobs/${id}/cancel`, {}).catch(() => { /* best effort; server may have completed */ });
  };

  const job = useQuery({
    queryKey: ["quick-job", jobId],
    queryFn: ({ signal }) => api<Job>(`/jobs/${jobId}`, { signal }),
    enabled: !!jobId,
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: (q) => ![404, 410].includes((q.state.error as ApiError | null)?.status ?? 0),
    refetchInterval: (q) => q.state.error ? false :
      (!q.state.data || activeJob(q.state.data.status) ? 1000 : false),
  });
  const running = !!jobId && !job.isError && (!job.data || activeJob(job.data.status));
  const pollGone = job.isError && [404, 410].includes((job.error as ApiError).status ?? 0);
  const rawResult = job.data?.status === "completed" ? job.data.result : null;
  const item: Item | null = rawResult && "prediction" in rawResult ? (rawResult as Item) : null;
  const prediction: Prediction | null = item?.prediction ?? null;
  const sourceValid = !!(jobId && currentRunId && job.data?.kind === "quick" &&
    job.data.id === jobId && job.data.run_id === currentRunId && item && prediction?.id &&
    item.id && item.dataset_id && item.revision_id && Number.isInteger(item.revision) && item.revision > 0 &&
    !item.stale && item.text === submittedText && prediction.run_id === currentRunId &&
    prediction.item_id === item.id && prediction.revision_id === item.revision_id &&
    (!item.review_signals || item.review_signals.prediction_id === prediction.id));
  const sentimentValid = sourceValid && validDemoTask(prediction, profile, "sentiment");
  const topicValid = sourceValid && validDemoTask(prediction, profile, "topic");
  const validPrediction = sentimentValid && topicValid;
  const explanationSnapshot = item && prediction ? {
    run_id: currentRunId, item_id: item.id, revision_id: item.revision_id,
    profile_id: profileId, schema_id: prediction.schema_id,
    classifier_model_id: prediction.model_id, classifier_model_version: prediction.model_version,
  } : null;

  const resetAnalysis = useCallback(() => {
    generationRef.current += 1;
    busyGenerationRef.current = null;
    explanationPendingRef.current = false;
    const abandoned = jobIdRef.current;
    jobIdRef.current = null;
    cancelAbandonedJob(abandoned);
    if (abandoned) void queryClient.cancelQueries({ queryKey: ["quick-job", abandoned] });
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    lastExplainedKeyRef.current = "";
    setBusy(false);
    setJobId(null);
    setCurrentRunId("");
    setSubmittedText("");
    setExplanation(null);
    setExplaining(false);
    setExplanationError(null);
    setShowExplore(false);
    setSubmitError(null);
    setAddingToDataset(false);
    setAddedToDataset(false);
  }, [queryClient]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
      abortControllerRef.current?.abort();
      cancelAbandonedJob(jobIdRef.current);
      if (jobIdRef.current) void queryClient.cancelQueries({ queryKey: ["quick-job", jobIdRef.current] });
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [queryClient]);

  // Handle switching profile
  const handleProfileChange = (newProfileId: string) => {
    if (newProfileId === profileId) return;
    setProfileId(newProfileId);
    setSelectedDatasetId("");
    setDrillDownTopicId(null);
    setQuickAddTarget("");
    setAddedToDataset(false);
    setScopeNotice("");
    resetAnalysis();
  };

  // Explanation fetch function
  const triggerExplanation = useCallback(
    async (
      targetJobId: string,
      targetPredictionId: string,
      snapshot: NonNullable<typeof explanationSnapshot>,
      force = false,
    ) => {
      const key = `${targetJobId}:${targetPredictionId}`;
      if (force && explanationPendingRef.current) return;
      if (!force && lastExplainedKeyRef.current === key) {
        return;
      }
      lastExplainedKeyRef.current = key;

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const currentGen = generationRef.current;

      explanationPendingRef.current = true;
      setExplaining(true);
      setExplanationError(null);
      setExplanation(null);

      try {
        const res = await getExplanation(
          targetJobId,
          targetPredictionId,
          controller.signal,
        );
        if (!isCurrent(currentGen) || abortControllerRef.current !== controller) return;
        if (res.status !== "completed" || res.job_id !== targetJobId ||
            res.source_prediction_id !== targetPredictionId ||
            Object.entries(snapshot).some(([name, value]) => res[name as keyof ExplanationResponse] !== value)) {
          throw new ApiError("Diễn giải không khớp kết quả hiện tại. Hãy thử lại.", "EXPLANATION_IDENTITY_CONFLICT", undefined, 409);
        }
        setExplanation(res);
      } catch (err: unknown) {
        if (!isCurrent(currentGen) || abortControllerRef.current !== controller) return;
        if (controller.signal.aborted) return;
        const apiErr = err as ApiError;
        setExplanationError({
          status: apiErr.status,
          message:
            apiErr.message ||
            "Không thể tải diễn giải. Vui lòng thử lại sau.",
        });
      } finally {
        if (isCurrent(currentGen) && abortControllerRef.current === controller) {
          explanationPendingRef.current = false;
          setExplaining(false);
        }
      }
    },
    [],
  );

  // Automatically trigger explanation as soon as prediction arrives
  useEffect(() => {
    if (!validPrediction) {
      explanationPendingRef.current = false;
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      lastExplainedKeyRef.current = "";
      setExplanation(null);
      setExplanationError(null);
      setExplaining(false);
      return;
    }
    if (job.data?.status === "completed" && validPrediction && prediction && jobId && explanationSnapshot) {
      const sourcePredId =
        prediction.id || item?.review_signals?.prediction_id || "";
      if (sourcePredId) {
        void triggerExplanation(jobId, sourcePredId, explanationSnapshot);
      }
    }
  }, [job.data?.status, validPrediction, prediction, jobId, item, triggerExplanation]);

  // Expand the embedded SensitivityPanel details element when explore opens
  useEffect(() => {
    if (showExplore && exploreContainerRef.current) {
      const details =
        exploreContainerRef.current.querySelector<HTMLDetailsElement>(
          "details.sensitivity-panel",
        );
      if (details && !details.open) {
        details.open = true;
      }
    }
  }, [showExplore]);

  // Do not abort this POST: a late accepted job must still be cancelled by ID.
  const handleAnalyze = async () => {
    if (!text.trim() || running || busy || busyGenerationRef.current !== null || !profile.model?.available) return;
    const submitted = text.trim();
    const submittedProfile = profileId;
    resetAnalysis();
    const generation = generationRef.current;
    busyGenerationRef.current = generation;
    setBusy(true);
    try {
      const response = await post<{ job_id: string; run_id: string }>("/quick-analysis", {
        profile: submittedProfile, text: submitted,
      });
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
      if (isCurrent(generation)) { busyGenerationRef.current = null; setBusy(false); }
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
      if (isCurrent(generation)) showToast((e as ApiError).message || "Không thể hủy phân tích.", true);
    }
  };

  const handleRetryJob = async () => {
    if (!jobId || busy || busyGenerationRef.current !== null || !profile.model?.available) return;
    const generation = generationRef.current;
    const targetJobId = jobId;
    busyGenerationRef.current = generation;
    setBusy(true);
    try {
      await post(`/jobs/${targetJobId}/retry`, {});
      if (!isCurrent(generation)) {
        cancelAbandonedJob(targetJobId);
        return;
      }
      lastExplainedKeyRef.current = "";
      setExplanation(null);
      setExplanationError(null);
      await job.refetch();
    } catch (e: unknown) {
      if (isCurrent(generation)) setSubmitError((e as ApiError).message || "Không thể thử lại tác vụ.");
    } finally {
      if (isCurrent(generation)) { busyGenerationRef.current = null; setBusy(false); }
    }
  };

  // Retry explanation only
  const handleRetryExplanation = () => {
    if (jobId && prediction && validPrediction && explanationSnapshot && !explaining) {
      const sourcePredId =
        prediction.id || item?.review_signals?.prediction_id || "";
      if (sourcePredId) {
        void triggerExplanation(jobId, sourcePredId, explanationSnapshot, true);
      }
    }
  };

  // Quick Add current sentence to selected dataset
  const handleQuickAdd = async () => {
    if (!quickAddTarget || !submittedText) return;
    const generation = generationRef.current;
    setAddingToDataset(true);
    try {
      await post(`/datasets/${quickAddTarget}/items`, {
        items: [{ text: submittedText }],
      });
      await queryClient.invalidateQueries({ queryKey: ["datasets"] });
      await queryClient.invalidateQueries({ queryKey: ["items", quickAddTarget] });
      await queryClient.invalidateQueries({ queryKey: ["summary", quickAddTarget] });
      await queryClient.invalidateQueries({ queryKey: ["demo-dataset-summary", quickAddTarget] });
      await queryClient.invalidateQueries({ queryKey: ["demo-drilldown-items", quickAddTarget] });
      if (!isCurrent(generation)) return;
      setAddedToDataset(true);
      showToast(
        "Đã thêm câu vào bộ phản hồi. Chạy phân tích trong bộ đó để lưu kết quả gắn với phiên bản mới.",
      );
    } catch (e: unknown) {
      const err = e as ApiError;
      if (isCurrent(generation)) showToast(err.message || "Không thể thêm câu vào bộ phản hồi.", true);
    } finally {
      if (isCurrent(generation)) setAddingToDataset(false);
    }
  };

  // Summary and items must represent one validated storage snapshot.
  const summaryQuery = useQuery({
    queryKey: ["demo-dataset-summary", selectedDatasetId, labelSource, "current"],
    queryFn: ({ signal }) => api<Summary>(
      `/datasets/${selectedDatasetId}/summary?label_source=${labelSource}`, { signal }),
    enabled: !!selectedDatasetId,
    refetchOnWindowFocus: true,
  });
  const summary = summaryQuery.isError ? undefined : summaryQuery.data;
  const attention = summary?.attention;
  const topPriorityTopic = attention?.topics?.[0];
  const [scopeNotice, setScopeNotice] = useState("");
  const scopeIdentity = `${selectedDatasetId}:${labelSource}:${summary?.scope_token ?? ""}:${summary?.resolved_run_id ?? ""}:${summary?.revision_scope ?? ""}`;
  useEffect(() => {
    setDrillDownTopicId(null);
    setDrillDownPage(1);
  }, [scopeIdentity]);

  const drillDownQuery = useQuery({
    queryKey: ["demo-drilldown-items", selectedDatasetId, scopeIdentity,
      drillDownTopicId, attention?.negative_label_id, labelSource, drillDownPage],
    queryFn: async ({ signal }) => {
      if (!summary || !attention) throw new Error("Chưa có phạm vi thống kê.");
      const params = new URLSearchParams({
        topic: String(drillDownTopicId), sentiment: String(attention.negative_label_id),
        label_source: labelSource, page: String(drillDownPage), page_size: "5",
        scope_token: summary.scope_token ?? "", expected_run_id: summary.resolved_run_id ?? "",
      });
      if (summary.revision_scope === "run" && summary.resolved_run_id) params.set("run_id", summary.resolved_run_id);
      const response = await api<ItemPage>(`/datasets/${selectedDatasetId}/items?${params}`, { signal });
      if (response.scope_token !== summary.scope_token || response.dataset_id !== selectedDatasetId ||
          response.label_source !== labelSource || response.resolved_run_id !== summary.resolved_run_id ||
          response.revision_scope !== summary.revision_scope) {
        throw new ApiError("Phạm vi dữ liệu đã thay đổi; cần tải lại thống kê.", "SCOPE_CHANGED", undefined, 409);
      }
      return response;
    },
    enabled: !!selectedDatasetId && !!summary?.scope_token && drillDownTopicId !== null && !summaryQuery.isFetching,
    staleTime: 0,
    retry: false,
  });
  useEffect(() => {
    if (drillDownQuery.isError && (drillDownQuery.error as ApiError).status === 409) {
      setDrillDownTopicId(null);
      setDrillDownPage(1);
      setScopeNotice("Dữ liệu hoặc nhãn đã thay đổi. Đã tải lại thống kê; hãy chọn lại chủ đề.");
      void summaryQuery.refetch();
    }
  }, [drillDownQuery.isError, drillDownQuery.error, summaryQuery.refetch]);

  const reviewSignals = item?.review_signals;
  const isTruncated = reviewSignals?.truncated === true || prediction?.truncated === true;
  const sentimentState = sentimentValid ? reviewSignals?.sentiment?.state ?? "unavailable" : "unavailable";
  const topicState = topicValid ? reviewSignals?.topic?.state ?? "unavailable" : "unavailable";
  const hasLocalSignalWarning = sentimentState !== "clear" || topicState !== "clear" || isTruncated;
  const signalText = (task: "sentiment" | "topic", state: string) => {
    const title = task === "sentiment" ? "Cảm xúc" : "Chủ đề";
    if (state === "unavailable") return `${title}: chưa đủ dữ liệu tín hiệu model để đối chiếu.`;
    if (state === "clear") return `${title}: không có cờ nghi ngờ theo chính sách rà soát; điểm cao không bảo đảm dự đoán đúng.`;
    const reasons = reviewSignals?.[task]?.reasons ?? [];
    return `${title}: ${reasons.includes("low_top1") || reasons.includes("LOW_TOP1") ? "điểm nhãn dẫn đầu thấp; " : ""}${reasons.includes("small_margin") || reasons.includes("SMALL_MARGIN") ? "cách biệt hai nhãn dẫn đầu nhỏ; " : ""}cần đối chiếu văn bản gốc.`;
  };
  const sentimentLabelName = sentimentValid && prediction ? labelName(profile, "sentiment", prediction.sentiment.label_id) : "Không đủ dữ liệu cảm xúc";
  const sentimentScoreVal = sentimentValid && prediction ? prediction.sentiment.scores[prediction.sentiment.label_id] : null;
  const isSentimentNegative = sentimentLabelName.toLowerCase().includes("tiêu cực") || sentimentLabelName.toLowerCase().includes("negative");
  const topicLabelName = topicValid && prediction ? labelName(profile, "topic", prediction.topic.label_id) : "Không đủ dữ liệu chủ đề";
  const topicScoreVal = topicValid && prediction ? prediction.topic.scores[prediction.topic.label_id] : null;
  const scoreText = (value: number | null) => value === null ? "—" : formatPercent(value);

  // Filter datasets belonging to the active profile
  const compatibleDatasets = datasets.filter((d) => d.profile === profileId);

  return (
    <div className="sentence-demo-root">
      <a
        className="skip"
        href="#demo-main"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("demo-main")?.focus();
        }}
      >
        Đến nội dung chính
      </a>

      {/* Header */}
      <header className="site-header">
        <a
          className="brand"
          href="#/demo"
          aria-label="NEU-ESC — Demo phân tích câu"
        >
          <span className="brand-icon">N</span>
          <strong>NEU–ESC</strong>
          <span className="brand-description">Hiểu phản hồi tiếng Việt</span>
        </a>
        <nav aria-label="Chức năng điều hướng">
          <a href="#/">
            Làm việc với bộ dữ liệu <span aria-hidden="true">↗</span>
          </a>
          <a href="#/research">Nghiên cứu</a>
        </nav>
      </header>

      {/* Main Container */}
      <main id="demo-main" tabIndex={-1}>
        {/* Intro */}
        <div className="intro">
          <div>
            <span className="mode-label">
              <span className="status-dot" />
              Demo phân tích phản hồi
            </span>
            <h1>Hiểu rõ từng phản hồi.</h1>
            <p>
              Nhập phản hồi để khám phá <strong>cảm xúc</strong> và{" "}
              <strong>chủ đề</strong> mà model nhận diện.
            </p>
          </div>
          <div className="profile-pill">
            <label htmlFor="schema-select">Hệ nhãn đang xem</label>
            <select
              id="schema-select"
              value={profileId}
              onChange={(e) => handleProfileChange(e.target.value)}
            >
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.id.toUpperCase()} · {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Vertical Stack: Layer 1 Grid */}
        <div className="analysis-grid">
          {/* Section: Input Panel */}
          <section className="input-panel" aria-labelledby="input-heading">
            <header className="section-head">
              <h2 id="input-heading">Câu của bạn</h2>
              <span>Tiếng Việt</span>
            </header>

            <label className="sr-only" htmlFor="sentence">
              Văn bản cần phân tích
            </label>
            <textarea
              id="sentence"
              maxLength={5000}
              spellCheck={false}
              value={text}
              placeholder="Nhập một phản hồi tiếng Việt…"
              onChange={(e) => {
                setText(e.target.value);
                resetAnalysis();
              }}
            />

            <div className="editor-footer">
              <span>Văn bản gốc luôn được giữ nguyên</span>
              <span>{text.length} / 5.000 ký tự</span>
            </div>

            {/* Approximate preprocessing notice if applicable */}
            {profile.model?.available &&
              profile.model.preprocessing?.equivalence === "approximate" && (
                <div className="notice input-notice status">
                  <span>
                    Văn bản được tách từ trước khi phân tích. Kết quả trên dữ
                    liệu bạn nhập có thể khác benchmark nghiên cứu.
                  </span>
                </div>
              )}

            {/* Model unavailable notice if applicable */}
            {profile.model && !profile.model.available && (
              <div className="notice warning input-notice" role="alert">
                <strong>Model chưa sẵn sàng</strong>
                <span>
                  {profile.model.reason ||
                    "Cần cài bộ model hợp lệ cho loại nội dung này để phân tích."}
                </span>
                <a href="#/help">Xem hướng dẫn cài đặt model ↗</a>
              </div>
            )}

            {submitError && (
              <div className="notice error input-notice" role="alert">
                <strong>Lỗi gửi phân tích:</strong>
                <span>{submitError}</span>
              </div>
            )}

            {/* 3 Sample Sentences */}
            <div className="examples">
              <p>Thử nhanh với một câu mẫu</p>
              <div>
                {SAMPLE_SENTENCES.map((sample) => {
                  const isActive = text.trim() === sample.text;
                  return (
                    <button
                      key={sample.name}
                      type="button"
                      className={`example ${isActive ? "active" : ""}`}
                      aria-pressed={isActive}
                      onClick={() => {
                        setText(sample.text);
                        resetAnalysis();
                      }}
                    >
                      {sample.name}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="submit-row">
              <button
                type="button"
                className="primary"
                id="analyze"
                disabled={
                  !text.trim() || running || busy || !profile.model?.available
                }
                onClick={() => void handleAnalyze()}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  aria-hidden="true"
                >
                  <path d="m13 3-8 10h6l-1 8 9-11h-6z" />
                </svg>
                <span>
                  {busy
                    ? "Đang gửi…"
                    : running
                      ? "Đang phân tích…"
                      : "Phân tích câu"}
                </span>
                <span aria-hidden="true">→</span>
              </button>

              <button
                type="button"
                className="clear-button"
                id="clear"
                  onClick={() => {
                  setText("");
                  resetAnalysis();
                  document.getElementById("sentence")?.focus();
                }}
              >
                Xóa nội dung
              </button>
            </div>

            <p className="demo-explanation">
              Phân loại chạy trên máy; câu và kết quả được gửi tới dịch vụ diễn
              giải.
            </p>
          </section>

          {/* Section: Result Panel (Layer 1) */}
          <section
            className="result-panel"
            aria-labelledby="result-heading"
            aria-busy={running}
          >
            <header className="section-head">
              <h2 id="result-heading">
                <span className="layer-tag">Lớp 1 · Prediction</span>
                Kết quả phân tích
              </h2>
              {prediction ? (
                <span className="sample-label">
                  {prediction.model_id} · {prediction.model_version}
                </span>
              ) : (
                <span className="sample-label">Kết quả AI</span>
              )}
            </header>

            {/* Empty State */}
            {!jobId && !prediction && !running && (
              <div id="empty-state" className="empty-state">
                <span className="empty-symbol" aria-hidden="true">
                  ↗
                </span>
                <h3>Kết quả sẽ xuất hiện ở đây</h3>
                <p>
                  Nhập một phản hồi hoặc chọn một câu mẫu và bấm Phân tích câu.
                </p>
              </div>
            )}

            {/* Real Waiting State */}
            {running && (
              <div id="waiting-state" className="waiting-state" role="status">
                <div className="wait-heading">
                  <span className="pulse-dot" aria-hidden="true" />
                  <h3>Đang chuẩn bị kết quả</h3>
                </div>
                <ol>
                  <li className="done">
                    <span aria-hidden="true">✓</span>
                    Tiếp nhận văn bản
                  </li>
                  <li className="current">
                    <span aria-hidden="true">2</span>
                    {job.data?.status === "loading_model"
                      ? "Đang nạp model vào bộ nhớ…"
                      : job.data?.status === "running"
                        ? "Đang phân tích câu…"
                        : "Đang chờ worker phân tích…"}
                  </li>
                  <li>
                    <span aria-hidden="true">3</span>
                    Hiển thị cảm xúc và chủ đề
                  </li>
                </ol>
                <p>
                  Lần phân tích đầu có thể lâu hơn một chút vì model cần được nạp
                  vào bộ nhớ máy tính.
                </p>
                <div className="wait-footer">
                  <small>
                    Mã tác vụ: {jobId ? jobId.slice(0, 8) : "—"} (
                    {job.data?.status ?? "queued"})
                  </small>
                  <button
                    type="button"
                    id="cancel"
                    disabled={job.data?.cancel_requested}
                    onClick={() => void handleCancel()}
                  >
                    Hủy phân tích
                  </button>
                </div>
              </div>
            )}

            {job.isError && (
              <div className="notice error" role="alert" id="poll-error">
                <strong>{pollGone ? "Tác vụ không còn khả dụng hoặc đã hết hạn." : "Chưa đọc được trạng thái phân tích."}</strong>
                <span>{(job.error as Error).message}</span>
                {!pollGone && <button type="button" onClick={() => void job.refetch()}>Thử đọc lại trạng thái</button>}
                {!pollGone && job.data && activeJob(job.data.status) && <button type="button" onClick={() => void handleCancel()}>Hủy phân tích</button>}
                <button type="button" onClick={resetAnalysis}>Bỏ tác vụ để phân tích lại</button>
              </div>
            )}

            {/* Cancelled or Error State */}
            {job.data && !activeJob(job.data.status) && !prediction && (
              <div className="notice warning" role="status">
                <strong>
                  {job.data.status === "cancelled"
                    ? "Đã hủy phân tích."
                    : job.data.error || "Tác vụ kết thúc nhưng chưa có kết quả."}
                </strong>
                <button
                  type="button"
                  style={{ alignSelf: "flex-start", marginTop: 8 }}
                  disabled={busy || !profile.model?.available}
                  onClick={() => void handleRetryJob()}
                >
                  Chạy lại tác vụ này
                </button>
              </div>
            )}

            {/* Actual Result Content */}
            {prediction && (
              <div id="result-content" aria-live="polite">
                {!validPrediction && <div className="notice error" role="alert">Dự đoán thiếu điểm hợp lệ hoặc không khớp schema/model hiện tại. Phần dữ liệu hợp lệ vẫn hiển thị; chưa thể yêu cầu diễn giải.</div>}
                {prediction.truncated && (
                  <div className="notice warning" role="alert">
                    <strong>Đầu vào bị cắt ngắn:</strong>
                    <span>
                      Model đã cắt ngắn văn bản (tối đa 128 token). Kết quả chỉ
                      dựa trên phần văn bản model đã đọc.
                    </span>
                  </div>
                )}

                <div className="prediction-columns">
                  {/* Sentiment Column */}
                  <section
                    className="prediction-column"
                    aria-label="Kết quả cảm xúc"
                  >
                    <div className="result-line">
                      <div>
                        <span className="task-label">Cảm xúc</span>
                        <strong
                          className={`sentiment-value ${
                            isSentimentNegative ? "negative" : ""
                          }`}
                          id="sentiment"
                        >
                          {sentimentLabelName}
                        </strong>
                        <p>Cách người viết thể hiện cảm nhận</p>
                      </div>
                      <div className="score-number">
                        <strong id="sentiment-score">
                          {scoreText(sentimentScoreVal)}
                          <span>%</span>
                        </strong>
                        <small>điểm model</small>
                      </div>
                    </div>

                    <div className="distribution">
                      <h3>Điểm từng nhãn cảm xúc</h3>
                      <div id="scores">
                        {sentimentValid && profile.sentiment.map((label) => {
                          const score =
                            prediction.sentiment.scores[label.id];
                          const isLeading =
                            prediction.sentiment.label_id === label.id;
                          return (
                            <div className="score-row" key={label.id}>
                              <span>{label.name}</span>
                              <div className="score-track">
                                <span
                                  className={isLeading ? "leading" : ""}
                                  style={{
                                    width: `${score * 100}%`,
                                  }}
                                />
                              </div>
                              <strong>{formatPercent(score)}%</strong>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </section>

                  {/* Topic Column */}
                  <section
                    className="prediction-column"
                    aria-label="Kết quả chủ đề"
                  >
                    <div className="result-line">
                      <div>
                        <span className="task-label">Chủ đề</span>
                        <strong className="topic-value" id="topic">
                          {topicLabelName}
                        </strong>
                        <p>Nội dung chính của phản hồi</p>
                      </div>
                      <div className="score-number">
                        <strong id="topic-score">
                          {scoreText(topicScoreVal)}
                          <span>%</span>
                        </strong>
                        <small>điểm model</small>
                      </div>
                    </div>

                    <div className="distribution">
                      <h3>Điểm từng nhãn chủ đề</h3>
                      <div id="topic-scores">
                        {topicValid && profile.topic.map((label) => {
                          const score =
                            prediction.topic.scores[label.id];
                          const isLeading =
                            prediction.topic.label_id === label.id;
                          return (
                            <div className="score-row" key={label.id}>
                              <span>{label.name}</span>
                              <div className="score-track">
                                <span
                                  className={isLeading ? "leading" : ""}
                                  style={{
                                    width: `${score * 100}%`,
                                  }}
                                />
                              </div>
                              <strong>{formatPercent(score)}%</strong>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </section>
                </div>

                <p className="score-disclaimer">
                  Phân bố điểm dự đoán. Điểm model chưa hiệu chuẩn, không phải xác
                  suất dự đoán đúng.
                </p>
              </div>
            )}
          </section>
        </div>

        {/* Small footer note under grid */}
        <div className="under-grid">
          <span>
            <span className="tiny-lock" aria-hidden="true">
              ◇
            </span>{" "}
            Phân loại chạy trên máy; câu và kết quả được gửi tới dịch vụ diễn
            giải.
          </span>
        </div>

        {/* Section: Layer 2 - Interpretability & Diễn giải */}
        <section className="interpret-panel" aria-labelledby="interpret-heading">
          <h2 id="interpret-heading">
            <span className="layer-tag">Lớp 2 · Interpretability</span>
            Đọc kỹ dự đoán
          </h2>
          <p className="section-description">
            Đối chiếu từng câu và nhận biết trường hợp khó phân loại.
          </p>

          {!prediction ? (
            <p
              id="interpret-empty"
              style={{ marginTop: 20, color: "var(--muted)" }}
            >
              Phân tích một câu để xem phần đối chiếu tín hiệu và diễn giải ngữ
              cảnh.
            </p>
          ) : (
            <div id="interpret-content">
              {/* Sentence reading */}
              <div className="sentence-reading">
                <span className="task-label">Phản hồi vừa phân tích</span>
                <p id="sentence-reading">{submittedText}</p>
                <strong id="sentence-labels">
                  {sentimentLabelName} · {scoreText(sentimentScoreVal)}% /{" "}
                  {topicLabelName} · {scoreText(topicScoreVal)}%
                </strong>
              </div>

              {/* Local Signals (Item.review_signals) */}
              <div className={`signal ${hasLocalSignalWarning ? "" : "clear"}`} id="signal" role="status">
                <span aria-hidden="true">{hasLocalSignalWarning ? "!" : "✓"}</span>
                <div>
                  <strong>{hasLocalSignalWarning ? "Tín hiệu cần đối chiếu" : "Không có cờ nghi ngờ theo chính sách"}</strong>
                  <p data-signal-task="sentiment">{signalText("sentiment", sentimentState)}</p>
                  <p data-signal-task="topic">{signalText("topic", topicState)}</p>
                  {isTruncated && <p>Đầu vào bị cắt ngắn trước khi mã hóa.</p>}
                  <p>Tín hiệu heuristic từ backend, thử nghiệm và chưa hiệu chuẩn; không phải suy luận nội bộ của classifier.</p>
                </div>
              </div>

              {/* Automatic Diễn giải kết quả */}
              <article
                className="ai-explanation"
                aria-labelledby="ai-heading"
              >
                <div className="ai-heading">
                  <div>
                    <span className="layer-tag">Diễn giải kết quả</span>
                    <h3 id="ai-heading">Hiểu kết quả trong ngữ cảnh</h3>
                  </div>
                  <span className="sample-label">AI Diễn giải</span>
                </div>
                <p>
                  Đọc phần diễn giải ngắn dựa trên câu nhập, nhãn dự đoán và
                  điểm model. Kết quả phân tích phía trên luôn có sẵn trước.
                </p>

                {/* Explanation Loading State */}
                {explaining && (
                  <div id="explanation-loading" role="status">
                    <span>Đang diễn giải…</span>
                    <div className="loading-track">
                      <span />
                    </div>
                  </div>
                )}

                {/* Explanation Error States */}
                {!explaining && explanationError && (
                  <div
                    className={`notice ${
                      explanationError.status === 503 ||
                      explanationError.message.includes("Chưa cấu hình")
                        ? "warning"
                        : "error"
                    }`}
                    role="status"
                  >
                    {explanationError.status === 503 ||
                    explanationError.message.includes("Chưa cấu hình") ? (
                      <>
                        <strong>Chưa cấu hình dịch vụ diễn giải.</strong>
                        <span>
                          Dịch vụ diễn giải (9router/LLM) chưa được kích hoạt ở
                          backend.
                        </span>
                        <a href="#/help">Xem hướng dẫn cấu hình ↗</a>
                        <span>Sau khi đổi environment, khởi động lại backend rồi thử diễn giải lại.</span>
                        <button type="button" onClick={handleRetryExplanation}>Thử lại diễn giải</button>
                      </>
                    ) : (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: 12,
                          flexWrap: "wrap",
                        }}
                      >
                        <div>
                          <strong>Chưa tải được diễn giải</strong>
                          <p style={{ marginTop: 4, fontSize: 14 }}>
                            {explanationError.message}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleRetryExplanation}
                        >
                          Thử lại diễn giải
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Explanation Success State */}
                {validPrediction && !explaining && explanation && (
                  <div id="ai-content">
                    <div className="ai-answer">
                      <h4>Cách đọc kết quả này</h4>
                      <p id="ai-reading">{explanation.reading}</p>
                      <h4>Điểm cần lưu ý</h4>
                      <p id="ai-caution">{explanation.caution}</p>
                    </div>
                    <p className="ai-evidence" id="ai-evidence">
                      Dữ kiện: câu hiện tại · {sentimentLabelName}{" "}
                      {scoreText(sentimentScoreVal)}% · {topicLabelName}{" "}
                      {scoreText(topicScoreVal)}% · phân bố điểm.
                    </p>
                    <p className="score-disclaimer">
                      Diễn giải hỗ trợ, không xác nhận cơ chế suy luận bên trong
                      model.
                    </p>
                  </div>
                )}
              </article>
            </div>
          )}
        </section>

        {/* Section: Khám phá độ nhạy (Sensitivity Exploration) */}
        {item && validPrediction && (
          <section className="explore-panel" aria-labelledby="explore-heading">
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
                <h2 id="explore-heading">
                  Điều gì xảy ra nếu bỏ một cụm từ?
                </h2>
                <p>
                  So sánh câu gốc và câu biến thể để quan sát độ nhạy của dự
                  đoán.
                </p>
              </div>
              <button
                id="toggle-explore"
                type="button"
                aria-expanded={showExplore}
                aria-controls="explore-body"
                onClick={() => setShowExplore((prev) => !prev)}
              >
                Khám phá dự đoán <span aria-hidden="true">↗</span>
              </button>
            </div>

            {showExplore && (
              <div id="explore-body" ref={exploreContainerRef}>
                <SensitivityPanel
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

        {/* Section: Layer 3 - Decision Support (Nhìn từ một tập phản hồi) */}
        <section className="decision-panel" aria-labelledby="decision-heading">
          <div className="decision-heading">
            <div>
              <span className="layer-tag">Lớp 3 · Decision Support</span>
              <h2 id="decision-heading">Nhìn từ một tập phản hồi</h2>
              <p className="section-description">
                Thống kê từ bộ dữ liệu thực tế giúp phát hiện cụm vấn đề cần ưu
                tiên xử lý.
              </p>
            </div>
            {summary && (
              <span className="sample-label">
                {summary.total} phản hồi · {summary.processed} đã phân tích
              </span>
            )}
          </div>

          {/* Dataset selector & Label source */}
          <div className="dataset-select-bar">
            <label htmlFor="dataset-select">
              <span>Bộ phản hồi:</span>
              <select
                id="dataset-select"
                value={selectedDatasetId}
                onChange={(e) => {
                  setSelectedDatasetId(e.target.value);
                  setDrillDownTopicId(null);
                  setDrillDownPage(1);
                  setScopeNotice("");
                }}
              >
                <option value="">
                  Chọn bộ phản hồi để xem thống kê theo chủ đề
                </option>
                {compatibleDatasets.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} ({d.item_count} phản hồi)
                  </option>
                ))}
              </select>
            </label>

            {selectedDatasetId && (
              <div className="label-source-group" role="group" aria-label="Nguồn nhãn">
                <button
                  type="button"
                  className={`label-source-btn ${
                    labelSource === "effective" ? "active" : ""
                  }`}
                  onClick={() => { setLabelSource("effective"); setDrillDownTopicId(null); setDrillDownPage(1); setScopeNotice(""); }}
                >
                  Đã duyệt nếu có, còn lại AI
                </button>
                <button
                  type="button"
                  className={`label-source-btn ${
                    labelSource === "ai" ? "active" : ""
                  }`}
                  onClick={() => { setLabelSource("ai"); setDrillDownTopicId(null); setDrillDownPage(1); setScopeNotice(""); }}
                >
                  Chỉ dự đoán AI gốc
                </button>
              </div>
            )}
          </div>

          {scopeNotice && <p className="notice warning" role="status">{scopeNotice}</p>}

          {/* Empty state when no dataset is selected */}
          {!selectedDatasetId ? (
            <div className="empty-state" style={{ padding: "36px 16px" }}>
              <span className="empty-symbol" aria-hidden="true">
                ▤
              </span>
              <h3>Chọn bộ phản hồi để xem thống kê</h3>
              <p>
                Thống kê lớp 3 được tính trực tiếp từ bộ dữ liệu thực tế đã phân
                tích, không sử dụng số liệu giả lập.
              </p>
              {compatibleDatasets.length === 0 && (
                <p style={{ marginTop: 8, fontSize: 14, color: "var(--muted)" }}>
                  Chưa có bộ phản hồi nào dùng hệ nhãn {profile.name}. Bạn có thể
                  tạo bộ mới ở mục{" "}
                  <a href="#/new" style={{ color: "var(--teal)" }}>
                    Làm việc với bộ dữ liệu
                  </a>
                  .
                </p>
              )}
            </div>
          ) : summaryQuery.isPending || summaryQuery.isFetching ? (
            <div className="notice status">
              <span>Đang tải thống kê từ bộ phản hồi…</span>
            </div>
          ) : summaryQuery.isError ? (
            <div className="notice error">
              <strong>Lỗi tải thống kê:</strong>
              <span>
                {(summaryQuery.error as Error).message ||
                  "Không thể tải dữ liệu."}
              </span>
            </div>
          ) : summary && attention ? (
            <>
              <p className="scope-description">Bộ phản hồi: {datasets.find(d => d.id === selectedDatasetId)?.name} · Lần chạy: {summary.resolved_run_id ?? "chưa có"} · Phạm vi: {summary.revision_scope === "current" ? "nội dung hiện tại" : "snapshot lần chạy"} · Nguồn: {labelSource === "ai" ? "Chỉ dự đoán AI gốc" : "Đã duyệt nếu có, còn lại AI"}.</p>
              <TopicAttention summary={summary} profile={profile} sentimentFilter="" labelSource={labelSource} running={false}
                onSelectTopicNegative={(topicId) => { setDrillDownTopicId(topicId); setDrillDownPage(1); }} />
              <div className="decision-grid">
                {/* Priority Note Card */}
                <article className="priority-note">
                  <span className="task-label">Chủ đề cần chú ý</span>
                  {topPriorityTopic && topPriorityTopic.negative_count > 0 ? (
                    <>
                      <h3>
                        {labelName(
                          profile,
                          "topic",
                          topPriorityTopic.topic_id,
                        )}
                      </h3>
                      <p>
                        <strong>
                          {topPriorityTopic.negative_count} /{" "}
                          {topPriorityTopic.eligible_count} phản hồi tiêu cực ·{" "}
                          {formatPercent(topPriorityTopic.negative_rate ?? 0)}%
                        </strong>{" "}
                        trong chủ đề này. Đây là chủ đề có nhiều phản hồi tiêu cực nhất trong phạm vi đang xem.
                      </p>
                      <p>
                        Nên đọc các phản hồi gốc để xác định vấn đề cụ thể trước
                        khi đưa ra hành động.
                      </p>
                      <button
                        type="button"
                        className="drill-down-btn"
                        onClick={() => {
                          setDrillDownTopicId(topPriorityTopic.topic_id);
                          setDrillDownPage(1);
                        }}
                      >
                        Xem {topPriorityTopic.negative_count} phản hồi tiêu cực
                        của chủ đề này ↓
                      </button>
                    </>
                  ) : (
                    <>
                      <h3>{attention.eligible_count === 0 ? "Chưa đủ dữ liệu kết luận" : "Chưa có nhãn Tiêu cực trong phạm vi"}</h3>
                      <p>{attention.eligible_count === 0 ? "Cần phân tích hoặc duyệt đủ cả chủ đề và cảm xúc." : "Đọc trạng thái, mẫu số và số Toxic riêng trước khi kết luận."}</p>
                    </>
                  )}
                </article>

                {/* Topic Distribution Summary Card */}
                <div className="topic-summary">
                  <h3>Phân bố theo chủ đề</h3>
                  <p>
                    Chiều dài thanh = tỷ lệ trên tổng{" "}
                    <strong>{attention.eligible_count}</strong> phản hồi có đủ
                    hai nhãn.
                  </p>

                  {attention.topics.map((t) => {
                    const pct =
                      attention.eligible_count > 0
                        ? (t.eligible_count / attention.eligible_count) * 100
                        : 0;
                    const isSelected = drillDownTopicId === t.topic_id;
                    return (
                      <button
                        type="button"
                        key={t.topic_id}
                        className={`aggregate-row ${
                          isSelected ? "selected" : ""
                        }`}
                        onClick={() => {
                          setDrillDownTopicId(t.topic_id);
                          setDrillDownPage(1);
                        }}
                        disabled={t.negative_count === 0}
                        aria-pressed={isSelected}
                        title="Xem phản hồi tiêu cực của chủ đề này"
                      >
                        <span>
                          {labelName(profile, "topic", t.topic_id)}
                        </span>
                        <div className="score-track">
                          <span
                            className="leading"
                            style={{
                              width: `${Math.min(100, Math.max(0, pct))}%`,
                            }}
                          />
                        </div>
                        <strong>
                          {t.eligible_count} · {pct.toFixed(1).replace(".", ",")}%
                        </strong>
                        <small>
                          {t.negative_count} tiêu cực / {t.eligible_count}
                          {attention.toxic_label_id !== null && ` · Toxic: ${t.toxic_count ?? 0}`}
                          {t.small_sample && " · Ít dữ liệu"}
                        </small>
                      </button>
                    );
                  })}
                </div>
              </div>

              <p className="score-disclaimer">
                Đây là thống kê số lượng phản hồi từ bộ dữ liệu, không phải điểm
                mô hình.
              </p>

              {/* Inline Drill-Down Feedback List */}
              {drillDownTopicId !== null && (
                <div className="drilldown-card">
                  <div className="drilldown-head">
                    <h4>
                      Phản hồi tiêu cực ·{" "}
                      {labelName(profile, "topic", drillDownTopicId)} (
                      {drillDownQuery.data?.total ?? "…"})
                    </h4>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <a
                        href={`#/datasets/${selectedDatasetId}`}
                        className="version-link"
                      >
                        Mở trong Workspace ↗
                      </a>
                      <button
                        type="button"
                        onClick={() => setDrillDownTopicId(null)}
                      >
                        Đóng
                      </button>
                    </div>
                  </div>

                  {drillDownQuery.isPending || drillDownQuery.isFetching ? (
                    <p style={{ color: "var(--muted)", padding: 12 }}>
                      Đang tải danh sách phản hồi…
                    </p>
                  ) : drillDownQuery.isError ? (
                    <div className="notice error">
                      Không thể tải danh sách phản hồi:{" "}
                      {(drillDownQuery.error as Error).message}
                    </div>
                  ) : drillDownQuery.data?.items.length === 0 ? (
                    <p style={{ color: "var(--muted)", padding: 12 }}>
                      Không có phản hồi tiêu cực nào thuộc chủ đề này trong bộ lọc
                      hiện tại.
                    </p>
                  ) : (
                    <div className="drilldown-items">
                      {drillDownQuery.data?.items.map((row) => (
                        <div className="drilldown-item" key={row.id}>
                          <p>{row.text}</p>
                          <div className="drilldown-meta">
                            <span>Dòng {row.source_row}</span>
                            <span>·</span>
                            <span>
                              Cảm xúc:{" "}
                              {labelName(
                                profile,
                                "sentiment",
                                labelSource === "effective"
                                  ? row.effective.sentiment
                                  : row.prediction?.sentiment.label_id,
                              )}
                            </span>
                            <span>·</span>
                            <span>
                              Chủ đề:{" "}
                              {labelName(
                                profile,
                                "topic",
                                labelSource === "effective"
                                  ? row.effective.topic
                                  : row.prediction?.topic.label_id,
                              )}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Drilldown Pagination */}
                  {drillDownQuery.data && drillDownQuery.data.total > 5 && (
                    <div className="drilldown-pagination">
                      <button
                        type="button"
                        disabled={drillDownPage <= 1}
                        onClick={() => setDrillDownPage((p) => p - 1)}
                      >
                        ← Trang trước
                      </button>
                      <span>
                        Trang {drillDownPage} /{" "}
                        {Math.max(
                          1,
                          Math.ceil(drillDownQuery.data.total / 5),
                        )}
                      </span>
                      <button
                        type="button"
                        disabled={
                          drillDownPage >=
                          Math.ceil(drillDownQuery.data.total / 5)
                        }
                        onClick={() => setDrillDownPage((p) => p + 1)}
                      >
                        Trang sau →
                      </button>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : null}

          {/* Quick Add to Dataset */}
          {submittedText && (
            <div className="quick-add-box">
              <div>
                <strong>Lưu câu vào bộ phản hồi</strong>
                <span>
                  Lưu phản hồi vừa phân tích vào một bộ phản hồi cùng hệ nhãn{" "}
                  {profile.name}.
                </span>
              </div>
              <div className="quick-add-controls">
                <select
                  aria-label="Lưu câu vào bộ phản hồi cùng hệ nhãn"
                  value={quickAddTarget}
                  disabled={addingToDataset || addedToDataset}
                  onChange={(e) => {
                    setQuickAddTarget(e.target.value);
                    setAddedToDataset(false);
                  }}
                >
                  <option value="">Chọn bộ phản hồi</option>
                  {compatibleDatasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="primary"
                  disabled={
                    !quickAddTarget || addingToDataset || addedToDataset
                  }
                  onClick={() => void handleQuickAdd()}
                >
                  {addedToDataset
                    ? "Đã thêm câu"
                    : addingToDataset
                      ? "Đang lưu…"
                      : "Thêm câu vào bộ"}
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Footer */}
        <footer>
          <a className="version-link" href="#/">
            ← Về danh sách bộ phản hồi
          </a>
          <span>NEU–ESC · Demo phân tích phản hồi</span>
          <span>AI hỗ trợ phân tích. Bạn đánh giá ý nghĩa trong ngữ cảnh.</span>
        </footer>
      </main>

      {/* Floating Toast notification */}
      {toastMessage && (
        <div id="toast" role="status" aria-live="polite">
          {toastMessage}
        </div>
      )}
    </div>
  );
}
export default SentenceDemo;
