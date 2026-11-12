import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  cancelJob,
  createSensitivityExperiment,
  getSensitivityExperiment,
  retryJob,
} from "./api";
import type {
  Item,
  Profile,
  SensitivityExperiment,
  SensitivityScoreDelta,
  SensitivityTaskComparison,
  Task,
} from "./types";
import { activeJob, date, labelName } from "./types";
import { Badge, ErrorNotice } from "./ui";

type Props = {
  item: Item;
  profile: Profile;
  runId: string;
  editingSourceText: boolean;
  onReloadItem: () => void;
  embedded?: boolean;
};

type SpanSelection = {
  start_utf16: number;
  end_utf16: number;
  text: string;
};

type TrackedJobState = {
  experimentId: string;
  jobId: string;
  status: string;
  cancelRequested: boolean;
  attempt?: number;
};

const TASKS: Task[] = ["sentiment", "topic"];

const SHA256_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
] as const;

const SHA256_INIT = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19,
] as const;

const rotr = (value: number, bits: number) =>
  (value >>> bits) | (value << (32 - bits));

function sha256BytesFallback(bytes: Uint8Array): string {
  const bitLen = bytes.length * 8;
  const paddedLength = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLength);
  padded.set(bytes);
  padded[bytes.length] = 0x80;
  const view = new DataView(padded.buffer);
  const highBits = Math.floor(bytes.length / 0x20000000);
  view.setUint32(paddedLength - 8, highBits >>> 0, false);
  view.setUint32(paddedLength - 4, bitLen >>> 0, false);

  const hash = new Uint32Array(SHA256_INIT);
  const w = new Uint32Array(64);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i += 1) {
      w[i] = view.getUint32(offset + i * 4, false);
    }
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }

    let a = hash[0];
    let b = hash[1];
    let c = hash[2];
    let d = hash[3];
    let e = hash[4];
    let f = hash[5];
    let g = hash[6];
    let h = hash[7];

    for (let i = 0; i < 64; i += 1) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA256_K[i] + w[i]) >>> 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }

    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }

  return Array.from(hash, (word) => word.toString(16).padStart(8, "0")).join(
    "",
  );
}

async function sha256Utf8Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  if (
    typeof crypto !== "undefined" &&
    crypto.subtle &&
    typeof crypto.subtle.digest === "function"
  ) {
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
  }
  return sha256BytesFallback(bytes);
}

function generateIdempotencyKey(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.getRandomValues === "function"
  ) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) {
      bytes[i] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(
    "",
  );
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

type GraphemeBoundaryInfo = {
  boundaries: Set<number> | null;
  sorted: number[] | null;
};

function computeGraphemeBoundaries(text: string): GraphemeBoundaryInfo {
  type SegmenterInstance = { segment(input: string): Iterable<{ index: number }> };
  type SegmenterConstructor = new (
    locales?: string | string[],
    options?: { granularity?: "grapheme" | "word" | "sentence" },
  ) => SegmenterInstance;
  const IntlObj = Intl as typeof Intl & { Segmenter?: SegmenterConstructor };
  if (typeof IntlObj.Segmenter !== "function") {
    return { boundaries: null, sorted: null };
  }
  const segmenter = new IntlObj.Segmenter(undefined, {
    granularity: "grapheme",
  });
  const boundaries = new Set<number>([0, text.length]);
  for (const part of segmenter.segment(text)) {
    boundaries.add(part.index);
  }
  return {
    boundaries,
    sorted: Array.from(boundaries).sort((a, b) => a - b),
  };
}

function isSplitSurrogate(text: string, pos: number): boolean {
  if (pos <= 0 || pos >= text.length) return false;
  const prev = text.charCodeAt(pos - 1);
  const curr = text.charCodeAt(pos);
  return prev >= 0xd800 && prev <= 0xdbff && curr >= 0xdc00 && curr <= 0xdfff;
}

function isValidBoundary(
  text: string,
  pos: number,
  boundaryInfo: GraphemeBoundaryInfo,
): boolean {
  if (pos < 0 || pos > text.length) return false;
  if (isSplitSurrogate(text, pos)) return false;
  if (boundaryInfo.boundaries) return boundaryInfo.boundaries.has(pos);
  return true;
}

function snapContextStart(
  text: string,
  approxPos: number,
  boundaryInfo: GraphemeBoundaryInfo,
): number {
  if (approxPos <= 0) return 0;
  if (boundaryInfo.sorted) {
    let best = 0;
    for (const b of boundaryInfo.sorted) {
      if (b <= approxPos) best = b;
      else break;
    }
    return best;
  }
  return isSplitSurrogate(text, approxPos) ? approxPos + 1 : approxPos;
}

function snapContextEnd(
  text: string,
  approxPos: number,
  boundaryInfo: GraphemeBoundaryInfo,
): number {
  if (approxPos >= text.length) return text.length;
  if (boundaryInfo.sorted) {
    for (const b of boundaryInfo.sorted) {
      if (b >= approxPos) return b;
    }
    return text.length;
  }
  return isSplitSurrogate(text, approxPos) ? approxPos + 1 : approxPos;
}

function findOccurrences(
  text: string,
  needle: string,
  boundaryInfo: GraphemeBoundaryInfo,
): { valid: SpanSelection[]; skippedNonGrapheme: number } {
  if (!needle) return { valid: [], skippedNonGrapheme: 0 };
  const valid: SpanSelection[] = [];
  let skippedNonGrapheme = 0;
  let searchFrom = 0;
  while (searchFrom <= text.length - needle.length) {
    const idx = text.indexOf(needle, searchFrom);
    if (idx === -1) break;
    const end = idx + needle.length;
    if (
      isValidBoundary(text, idx, boundaryInfo) &&
      isValidBoundary(text, end, boundaryInfo)
    ) {
      valid.push({ start_utf16: idx, end_utf16: end, text: needle });
    } else {
      skippedNonGrapheme += 1;
    }
    searchFrom = idx + 1;
  }
  return { valid, skippedNonGrapheme };
}

function validateSpanChoice(
  fullText: string,
  span: SpanSelection | null,
  queryText: string,
  validOccurrences: SpanSelection[],
  skippedNonGrapheme: number,
  boundaryInfo: GraphemeBoundaryInfo,
): { ok: true; span: SpanSelection; variantText: string } | { ok: false; message: string; focusTarget: "input" | "radio" } {
  if (!span) {
    if (!queryText) {
      return {
        ok: false,
        message: "Chọn hoặc nhập một đoạn có trong phản hồi.",
        focusTarget: "input",
      };
    }
    if (!queryText.trim()) {
      return {
        ok: false,
        message: "Đoạn cần bỏ không được chỉ gồm khoảng trắng.",
        focusTarget: "input",
      };
    }
    if (validOccurrences.length > 1) {
      return {
        ok: false,
        message: `Đoạn này xuất hiện ${validOccurrences.length} lần. Chọn một vị trí cụ thể bên dưới trước khi chạy thử.`,
        focusTarget: "radio",
      };
    }
    if (skippedNonGrapheme > 0) {
      return {
        ok: false,
        message:
          "Đoạn nhập vào cắt ngang dấu ghép hoặc ký tự emoji; hãy nhập trọn một chữ/cụm từ.",
        focusTarget: "input",
      };
    }
    return {
      ok: false,
      message: "Không tìm thấy chính xác đoạn này trong văn bản gốc.",
      focusTarget: "input",
    };
  }

  if (!span.text || !span.text.trim()) {
    return {
      ok: false,
      message: "Đoạn cần bỏ không được rỗng hoặc chỉ gồm khoảng trắng.",
      focusTarget: "input",
    };
  }
  if (
    span.start_utf16 < 0 ||
    span.end_utf16 > fullText.length ||
    span.start_utf16 >= span.end_utf16 ||
    fullText.slice(span.start_utf16, span.end_utf16) !== span.text
  ) {
    return {
      ok: false,
      message: "Vùng chọn không khớp với văn bản gốc đang xem.",
      focusTarget: "input",
    };
  }
  if (
    !isValidBoundary(fullText, span.start_utf16, boundaryInfo) ||
    !isValidBoundary(fullText, span.end_utf16, boundaryInfo)
  ) {
    return {
      ok: false,
      message:
        "Vùng chọn cắt ngang một ký tự tổ hợp hoặc emoji; hãy chọn lại theo ranh giới chữ viết.",
      focusTarget: "input",
    };
  }

  const variantText =
    fullText.slice(0, span.start_utf16) + fullText.slice(span.end_utf16);
  if (!variantText.trim()) {
    return {
      ok: false,
      message:
        "Không thể bỏ toàn bộ nội dung phản hồi. Hãy chọn đoạn ngắn hơn.",
      focusTarget: "input",
    };
  }
  if (!/[\p{L}\p{N}]/u.test(variantText)) {
    return {
      ok: false,
      message:
        "Văn bản sau khi bỏ chỉ còn dấu câu hoặc ký tự đặc biệt; cần còn ít nhất một chữ cái hoặc chữ số.",
      focusTarget: "input",
    };
  }
  return { ok: true, span, variantText };
}

function activeStatusText(status: string): string {
  if (status === "queued" || status === "pending") return "Đang chờ worker";
  if (status === "loading_model") return "Đang nạp model";
  if (status === "cancelling") return "Đang hủy thử nghiệm…";
  return "Đang so sánh hai văn bản";
}

function formatScore3(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : "—";
}

function formatDelta3(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (Object.is(value, -0) || Math.abs(value) < 0.0005) return "0.000";
  return value > 0 ? `+${value.toFixed(3)}` : value.toFixed(3);
}

function formatApiErrorDetail(err: unknown): {
  message: string;
  existingJobId: string | null;
  retryAfterSeconds: number | null;
  needsReload: boolean;
  focusSelection: boolean;
  clearIdempotency: boolean;
} {
  if (!(err instanceof ApiError)) {
    return {
      message: err instanceof Error ? err.message : String(err),
      existingJobId: null,
      retryAfterSeconds: null,
      needsReload: false,
      focusSelection: false,
      clearIdempotency: false,
    };
  }
  const details =
    err.details && typeof err.details === "object"
      ? (err.details as Record<string, unknown>)
      : null;

  if (err.code === "EXPERIMENT_IN_PROGRESS") {
    const existingJobId =
      typeof details?.existing_job_id === "string"
        ? details.existing_job_id
        : null;
    return {
      message:
        "Phản hồi này đang có một thử nghiệm độ nhạy chưa kết thúc. Bạn có thể xem hoặc hủy thử nghiệm đang chạy.",
      existingJobId,
      retryAfterSeconds: null,
      needsReload: false,
      focusSelection: false,
      clearIdempotency: true,
    };
  }
  if (err.code === "EXPERIMENT_LIMIT") {
    const retryAfter =
      typeof details?.retry_after_seconds === "number" &&
      Number.isFinite(details.retry_after_seconds)
        ? details.retry_after_seconds
        : null;
    return {
      message:
        retryAfter != null
          ? `Hệ thống cục bộ đang đạt giới hạn thử nghiệm. Vui lòng thử lại sau khoảng ${Math.max(1, Math.ceil(retryAfter))} giây.`
          : "Hệ thống cục bộ đang đạt giới hạn thử nghiệm. Vui lòng thử lại sau ít phút.",
      existingJobId: null,
      retryAfterSeconds: retryAfter,
      needsReload: false,
      focusSelection: false,
      clearIdempotency: true,
    };
  }
  if (
    err.code === "REVISION_CONFLICT" ||
    err.code === "SOURCE_CONTEXT_CHANGED"
  ) {
    return {
      message:
        "Văn bản hoặc dự đoán nguồn của phản hồi đã thay đổi từ lúc mở bảng chi tiết. Tải lại phản hồi để đồng bộ ngữ cảnh mới (nhãn rà soát đang nhập vẫn được giữ).",
      existingJobId: null,
      retryAfterSeconds: null,
      needsReload: true,
      focusSelection: false,
      clearIdempotency: true,
    };
  }
  if (err.code === "IDEMPOTENCY_CONFLICT") {
    return {
      message:
        "Khóa gửi bị trùng với nội dung khác. Hệ thống đã đặt lại khóa mới; bấm thử lại nếu bạn vẫn muốn chạy.",
      existingJobId: null,
      retryAfterSeconds: null,
      needsReload: false,
      focusSelection: false,
      clearIdempotency: true,
    };
  }
  if (
    err.code === "INVALID_SELECTION" ||
    err.code === "EMPTY_VARIANT" ||
    err.code === "NON_LEXICAL_VARIANT" ||
    err.code === "TEXT_TOO_LONG"
  ) {
    return {
      message: err.message,
      existingJobId: null,
      retryAfterSeconds: null,
      needsReload: false,
      focusSelection: true,
      clearIdempotency: true,
    };
  }
  return {
    message: err.message,
    existingJobId: null,
    retryAfterSeconds: null,
    needsReload: false,
    focusSelection: false,
    clearIdempotency: err.status != null && err.status >= 400 && err.status < 500,
  };
}

export function SensitivityPanel({
  item,
  profile,
  runId,
  editingSourceText,
  onReloadItem,
  embedded = false,
}: Props) {
  const queryClient = useQueryClient();
  const inputId = useId();
  const errorId = useId();
  const radioGroupName = useId();

  const rawTextRef = useRef<HTMLParagraphElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const firstRadioRef = useRef<HTMLInputElement>(null);
  const wasOpenRef = useRef(embedded);
  const [detailsOpen, setDetailsOpen] = useState(embedded);
  const panelOpen = embedded || detailsOpen;

  const generationRef = useRef(0);
  const activeJobIdRef = useRef<string | null>(null);
  const retrySeqRef = useRef(0);
  const trackedJobRef = useRef<TrackedJobState | null>(null);
  const submittingRef = useRef(false);
  const actionBusyRef = useRef(false);
  const submitAttemptRef = useRef<{ signature: string; key: string } | null>(
    null,
  );
  const prevContextKeyRef = useRef(
    `${item.id}|${item.revision_id}|${runId}`,
  );

  const [queryText, setQueryText] = useState("");
  const [selectedSpan, setSelectedSpan] = useState<SpanSelection | null>(null);
  const [selectionMessage, setSelectionMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ReturnType<
    typeof formatApiErrorDetail
  > | null>(null);
  const [experimentId, setExperimentId] = useState<string | null>(null);
  const [retrySeq, setRetrySeq] = useState(0);
  const [trackedJob, setTrackedJob] = useState<TrackedJobState | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const updateTrackedJob = (next: TrackedJobState | null) => {
    trackedJobRef.current = next;
    setTrackedJob(next);
  };

  const boundaryInfo = useMemo(
    () => computeGraphemeBoundaries(item.text),
    [item.text],
  );

  const occurrenceResult = useMemo(
    () => findOccurrences(item.text, queryText, boundaryInfo),
    [item.text, queryText, boundaryInfo],
  );
  const validOccurrences = occurrenceResult.valid;

  const cancelActiveIfAny = () => {
    const activeId = activeJobIdRef.current;
    activeJobIdRef.current = null;
    if (activeId) {
      void cancelJob(activeId).catch(() => {});
    }
  };

  const resetForChange = (resetSelection: boolean) => {
    generationRef.current += 1;
    cancelActiveIfAny();
    submitAttemptRef.current = null;
    submittingRef.current = false;
    actionBusyRef.current = false;
    setSubmitting(false);
    setActionBusy(false);
    setExperimentId(null);
    updateTrackedJob(null);
    setSubmitError(null);
    setActionError(null);
    setSelectionMessage(null);
    if (resetSelection) {
      setQueryText("");
      setSelectedSpan(null);
    }
  };

  useEffect(() => {
    const contextKey = `${item.id}|${item.revision_id}|${runId}`;
    if (prevContextKeyRef.current !== contextKey) {
      prevContextKeyRef.current = contextKey;
      generationRef.current += 1;
      cancelActiveIfAny();
      submitAttemptRef.current = null;
      submittingRef.current = false;
      actionBusyRef.current = false;
      setSubmitting(false);
      setActionBusy(false);
      setExperimentId(null);
      updateTrackedJob(null);
      setSubmitError(null);
      setActionError(null);
      setSelectionMessage(null);
      setQueryText("");
      setSelectedSpan(null);
    }
    const targetItemId = item.id;
    const targetRevisionId = item.revision_id;
    const targetRunId = runId;
    return () => {
      generationRef.current += 1;
      submittingRef.current = false;
      actionBusyRef.current = false;
      const activeId = activeJobIdRef.current;
      activeJobIdRef.current = null;
      trackedJobRef.current = null;
      if (activeId) {
        void cancelJob(activeId).catch(() => {});
      }
      queryClient.removeQueries({
        queryKey: [
          "sensitivity-experiment",
          targetItemId,
          targetRevisionId,
          targetRunId,
        ],
      });
    };
  }, [item.id, item.revision_id, runId, queryClient]);

  useEffect(() => {
    setSubmitError((prev) => (prev?.needsReload ? null : prev));
  }, [item.id, item.revision_id, item.prediction?.id, item.stale]);

  const experimentQuery = useQuery({
    queryKey: [
      "sensitivity-experiment",
      item.id,
      item.revision_id,
      runId,
      experimentId,
      retrySeq,
    ],
    queryFn: () => getSensitivityExperiment(experimentId!),
    enabled: panelOpen && experimentId != null,
    gcTime: 30_000,
    staleTime: 0,
    retry: (failureCount, err) =>
      !(
        err instanceof ApiError &&
        err.status != null &&
        err.status >= 400 &&
        err.status < 500
      ) && failureCount < 1,
    refetchInterval: (q) => {
      if (q.state.error) return false;
      const status = q.state.data?.status;
      if (status) return activeJob(status) ? 1000 : false;
      const tracked = trackedJobRef.current;
      if (
        tracked &&
        tracked.experimentId === experimentId &&
        (tracked.attempt == null || tracked.attempt === retrySeq) &&
        !activeJob(tracked.status)
      ) {
        return false;
      }
      return 1000;
    },
  });

  const exp = experimentQuery.data ?? null;
  const isQueryNotFound =
    experimentQuery.isError &&
    experimentQuery.error instanceof ApiError &&
    (experimentQuery.error.status === 404 ||
      experimentQuery.error.code === "NOT_FOUND");

  const activeTracked =
    experimentId != null &&
    trackedJob?.experimentId === experimentId &&
    (trackedJob.attempt == null || trackedJob.attempt === retrySeq)
      ? trackedJob
      : null;

  const isConfirmedNotFound =
    isQueryNotFound || activeTracked?.status === "not_found";

  const confirmedTerminal =
    isConfirmedNotFound ||
    (exp != null && !activeJob(exp.status)) ||
    (activeTracked != null && !activeJob(activeTracked.status));

  const isJobActive = experimentId != null && !confirmedTerminal;
  const knownJobId =
    experimentId != null
      ? (exp?.job_id ?? activeTracked?.jobId ?? experimentId)
      : null;
  const knownCancelRequested = Boolean(
    exp?.cancel_requested || activeTracked?.cancelRequested,
  );

  useEffect(() => {
    if (experimentId == null) {
      activeJobIdRef.current = null;
      return;
    }
    if (isQueryNotFound) {
      activeJobIdRef.current = null;
      const prev = trackedJobRef.current;
      if (
        !prev ||
        prev.experimentId !== experimentId ||
        prev.attempt !== retrySeq ||
        prev.status !== "not_found"
      ) {
        updateTrackedJob({
          experimentId,
          jobId: knownJobId ?? experimentId,
          status: "not_found",
          cancelRequested: false,
          attempt: retrySeq,
        });
      }
      return;
    }
    const locallyTerminal =
      trackedJobRef.current != null &&
      trackedJobRef.current.experimentId === experimentId &&
      (trackedJobRef.current.attempt == null ||
        trackedJobRef.current.attempt === retrySeq) &&
      !activeJob(trackedJobRef.current.status);
    if (locallyTerminal) {
      activeJobIdRef.current = null;
      return;
    }
    if (exp) {
      activeJobIdRef.current = activeJob(exp.status) ? exp.job_id : null;
      const prev = trackedJobRef.current;
      if (
        prev &&
        prev.experimentId === experimentId &&
        prev.attempt === retrySeq &&
        prev.jobId === exp.job_id &&
        prev.status === exp.status &&
        prev.cancelRequested === exp.cancel_requested
      ) {
        return;
      }
      updateTrackedJob({
        experimentId,
        jobId: exp.job_id,
        status: exp.status,
        cancelRequested: exp.cancel_requested,
        attempt: retrySeq,
      });
    }
  }, [experimentId, retrySeq, exp, isQueryNotFound, knownJobId]);

  const handleToggleDetails = (open: boolean) => {
    const effectiveOpen = embedded || open;
    setDetailsOpen(effectiveOpen);
    if (effectiveOpen) {
      wasOpenRef.current = true;
      return;
    }
    if (wasOpenRef.current) {
      wasOpenRef.current = false;
      resetForChange(true);
      queryClient.removeQueries({
        queryKey: [
          "sensitivity-experiment",
          item.id,
          item.revision_id,
          runId,
        ],
      });
    }
  };

  const handleInputChange = (nextValue: string) => {
    resetForChange(false);
    setQueryText(nextValue);
    if (!nextValue) {
      setSelectedSpan(null);
      return;
    }
    const found = findOccurrences(item.text, nextValue, boundaryInfo);
    if (found.valid.length === 1) {
      setSelectedSpan(found.valid[0]);
    } else {
      setSelectedSpan(null);
    }
  };

  const handlePickOccurrence = (occ: SpanSelection) => {
    const isSame =
      selectedSpan != null &&
      selectedSpan.start_utf16 === occ.start_utf16 &&
      selectedSpan.end_utf16 === occ.end_utf16;
    if (!isSame) {
      resetForChange(false);
      setSelectedSpan(occ);
    }
  };

  const handleDirectTextSelection = () => {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return;
    }
    const range = selection.getRangeAt(0);
    const textNode = rawTextRef.current?.firstChild;
    if (
      !textNode ||
      textNode.nodeType !== Node.TEXT_NODE ||
      range.startContainer !== textNode ||
      range.endContainer !== textNode
    ) {
      setSelectionMessage(
        "Vùng chọn vượt ra ngoài khung văn bản gốc. Hãy bôi chọn trong đoạn văn bản hoặc nhập vào ô bên dưới.",
      );
      return;
    }
    const start = Math.min(range.startOffset, range.endOffset);
    const end = Math.max(range.startOffset, range.endOffset);
    if (start === end) return;
    const exactSlice = item.text.slice(start, end);
    if (!exactSlice.trim()) {
      setSelectionMessage("Đoạn bôi chọn không được chỉ gồm khoảng trắng.");
      return;
    }
    if (
      !isValidBoundary(item.text, start, boundaryInfo) ||
      !isValidBoundary(item.text, end, boundaryInfo)
    ) {
      setSelectionMessage(
        "Vùng bôi chọn cắt ngang một ký tự tổ hợp hoặc emoji; hãy chọn lại hoặc dùng ô nhập bên dưới.",
      );
      return;
    }
    const isSame =
      selectedSpan != null &&
      selectedSpan.start_utf16 === start &&
      selectedSpan.end_utf16 === end;
    if (!isSame) {
      resetForChange(false);
    } else {
      setSelectionMessage(null);
    }
    if (!exactSlice.includes("\n") && !exactSlice.includes("\r")) {
      setQueryText(exactSlice);
    } else {
      setQueryText("");
    }
    setSelectedSpan({
      start_utf16: start,
      end_utf16: end,
      text: exactSlice,
    });
  };

  const liveValidation = selectedSpan
    ? validateSpanChoice(
        item.text,
        selectedSpan,
        queryText,
        validOccurrences,
        occurrenceResult.skippedNonGrapheme,
        boundaryInfo,
      )
    : null;

  const previewVariant =
    selectedSpan &&
    selectedSpan.start_utf16 >= 0 &&
    selectedSpan.end_utf16 <= item.text.length &&
    item.text.slice(selectedSpan.start_utf16, selectedSpan.end_utf16) ===
      selectedSpan.text
      ? item.text.slice(0, selectedSpan.start_utf16) +
        item.text.slice(selectedSpan.end_utf16)
      : null;

  const cannotCreateReason = item.stale
    ? "Chuyển về văn bản hiện tại để thử"
    : editingSourceText
      ? "Lưu hoặc hủy nháp văn bản nguồn trước khi thử nghiệm độ nhạy."
      : !profile.model.available
        ? "Model cho hệ nhãn này chưa sẵn sàng nên chưa thể tạo thử nghiệm mới."
        : null;

  async function handleSubmit() {
    if (
      cannotCreateReason ||
      submittingRef.current ||
      submitting ||
      actionBusyRef.current ||
      actionBusy ||
      isJobActive ||
      activeJobIdRef.current != null
    ) {
      return;
    }

    const check = validateSpanChoice(
      item.text,
      selectedSpan,
      queryText,
      validOccurrences,
      occurrenceResult.skippedNonGrapheme,
      boundaryInfo,
    );
    if (!check.ok) {
      setSelectionMessage(check.message);
      if (check.focusTarget === "radio" && firstRadioRef.current) {
        firstRadioRef.current.focus();
      } else {
        inputRef.current?.focus();
      }
      return;
    }

    setSelectionMessage(null);
    setSubmitError(null);
    setActionError(null);

    const signature = `${item.id}|${item.revision_id}|${runId}|${check.span.start_utf16}:${check.span.end_utf16}`;
    if (
      !submitAttemptRef.current ||
      submitAttemptRef.current.signature !== signature
    ) {
      submitAttemptRef.current = {
        signature,
        key: generateIdempotencyKey(),
      };
    }
    const idempotencyKey = submitAttemptRef.current.key;
    const reqGen = ++generationRef.current;

    submittingRef.current = true;
    setSubmitting(true);
    try {
      const textHash = await sha256Utf8Hex(item.text);
      if (reqGen !== generationRef.current) return;

      const created = await createSensitivityExperiment(
        item.id,
        {
          revision_id: item.revision_id,
          expected_revision: item.revision,
          text_sha256: textHash,
          run_id: runId || null,
          source_prediction_id: item.prediction?.id ?? null,
          selection: check.span,
        },
        idempotencyKey,
      );

      if (reqGen !== generationRef.current) {
        if (!created.status || activeJob(created.status)) {
          void cancelJob(created.job_id).catch(() => {});
        }
        return;
      }

      submitAttemptRef.current = null;
      const nextSeq = retrySeqRef.current + 1;
      retrySeqRef.current = nextSeq;
      activeJobIdRef.current = activeJob(created.status)
        ? created.job_id
        : null;
      updateTrackedJob({
        experimentId: created.experiment_id,
        jobId: created.job_id,
        status: created.status,
        cancelRequested: created.cancel_requested,
        attempt: nextSeq,
      });
      setRetrySeq(nextSeq);
      setExperimentId(created.experiment_id);
      queryClient.setQueryData(
        [
          "sensitivity-experiment",
          item.id,
          item.revision_id,
          runId,
          created.experiment_id,
          nextSeq,
        ],
        created,
      );
    } catch (err) {
      if (reqGen !== generationRef.current) return;
      const parsed = formatApiErrorDetail(err);
      if (parsed.clearIdempotency) {
        submitAttemptRef.current = null;
      }
      setSubmitError(parsed);
      if (parsed.focusSelection) {
        setSelectionMessage(parsed.message);
        inputRef.current?.focus();
      }
    } finally {
      if (reqGen === generationRef.current) {
        submittingRef.current = false;
        setSubmitting(false);
      }
    }
  }

  async function handleCancelActive(targetJobId: string) {
    if (
      actionBusyRef.current ||
      actionBusy ||
      submittingRef.current ||
      submitting
    ) {
      return;
    }
    const reqGen = generationRef.current;
    actionBusyRef.current = true;
    setActionBusy(true);
    setActionError(null);
    try {
      const cancelled = await cancelJob(targetJobId);
      if (reqGen !== generationRef.current) return;
      const jobStillActive = activeJob(cancelled.status);
      if (
        experimentId != null &&
        (exp?.job_id ?? activeTracked?.jobId ?? experimentId) === targetJobId
      ) {
        activeJobIdRef.current = jobStillActive ? cancelled.id : null;
        updateTrackedJob({
          experimentId,
          jobId: cancelled.id,
          status: cancelled.status,
          cancelRequested: cancelled.cancel_requested,
          attempt: retrySeqRef.current,
        });
        const expKey = [
          "sensitivity-experiment",
          item.id,
          item.revision_id,
          runId,
          experimentId,
          retrySeqRef.current,
        ] as const;
        queryClient.setQueryData<SensitivityExperiment>(expKey, (prev) =>
          prev
            ? {
                ...prev,
                status: cancelled.status,
                cancel_requested: cancelled.cancel_requested,
              }
            : prev,
        );
        if (jobStillActive) {
          void queryClient.invalidateQueries({ queryKey: expKey });
        }
      }
      setSubmitError((prev) =>
        prev?.existingJobId === targetJobId ? null : prev,
      );
    } catch (err) {
      if (reqGen !== generationRef.current) return;
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      if (reqGen === generationRef.current) {
        actionBusyRef.current = false;
        setActionBusy(false);
      }
    }
  }

  async function handleRetryExperiment(targetJobId: string) {
    if (
      actionBusyRef.current ||
      actionBusy ||
      submittingRef.current ||
      submitting
    ) {
      return;
    }
    const reqGen = generationRef.current;
    const retryExperimentId = experimentId ?? targetJobId;
    const oldExpKey = [
      "sensitivity-experiment",
      item.id,
      item.revision_id,
      runId,
      retryExperimentId,
      retrySeqRef.current,
    ] as const;

    actionBusyRef.current = true;
    setActionBusy(true);
    setActionError(null);
    setSubmitError(null);
    try {
      const updated = await retryJob(targetJobId);
      if (reqGen !== generationRef.current) {
        const cancelTargetId = updated?.id || targetJobId;
        if (!updated?.status || activeJob(updated.status)) {
          void cancelJob(cancelTargetId).catch(() => {});
        }
        return;
      }
      const nextSeq = retrySeqRef.current + 1;
      retrySeqRef.current = nextSeq;
      activeJobIdRef.current = activeJob(updated.status) ? updated.id : null;
      updateTrackedJob({
        experimentId: retryExperimentId,
        jobId: updated.id,
        status: updated.status,
        cancelRequested: updated.cancel_requested,
        attempt: nextSeq,
      });
      setRetrySeq(nextSeq);
      if (experimentId == null) {
        setExperimentId(retryExperimentId);
      }
      queryClient.removeQueries({ queryKey: oldExpKey, exact: true });
    } catch (err) {
      if (reqGen !== generationRef.current) return;
      if (
        err instanceof ApiError &&
        (err.code === "MODEL_IDENTITY_CHANGED" ||
          err.code === "REVISION_CONFLICT" ||
          err.code === "JOB_NOT_RETRYABLE" ||
          err.status === 404)
      ) {
        setActionError(
          "Không thể chạy tiếp thử nghiệm cũ vì model, phiên bản văn bản hoặc trạng thái job đã thay đổi. Hãy bấm “Chạy thử khi bỏ đoạn” để tạo thử nghiệm mới.",
        );
      } else {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (reqGen === generationRef.current) {
        actionBusyRef.current = false;
        setActionBusy(false);
      }
    }
  }

  return (
    <details
      className="sensitivity-panel"
      open={panelOpen}
      onToggle={(e) => handleToggleDetails(e.currentTarget.open)}
    >
      <summary hidden={embedded}>Khám phá dự đoán</summary>
      <div className="sensitivity-body">
        <p className="muted small">
          Thử bỏ một cụm từ trong bản gốc để quan sát thay đổi điểm số trên cùng
          model đang bật. Thao tác này không làm thay đổi văn bản, dự đoán gốc
          hay nhãn rà soát của bạn.
        </p>

        {cannotCreateReason && (
          <div className="notice warning small">{cannotCreateReason}</div>
        )}

        <div className="sensitivity-raw-box">
          <span className="muted small">
            Văn bản gốc (có thể bôi đen trực tiếp trên máy tính):
          </span>
          <p
            ref={rawTextRef}
            className="sensitivity-raw-text"
            onMouseUp={handleDirectTextSelection}
            onKeyUp={handleDirectTextSelection}
          >
            {item.text}
          </p>
        </div>

        <label htmlFor={inputId}>
          Nhập đoạn cần bỏ (đúng như văn bản gốc)
          <input
            id={inputId}
            ref={inputRef}
            type="text"
            value={queryText}
            aria-describedby={selectionMessage ? errorId : undefined}
            aria-invalid={selectionMessage ? true : undefined}
            onChange={(e) => handleInputChange(e.target.value)}
            placeholder="Nhập đúng cụm ký tự có trong phản hồi…"
          />
        </label>

        {queryText.length > 0 && validOccurrences.length === 0 && (
          <p className="muted small">
            {occurrenceResult.skippedNonGrapheme > 0
              ? "Đoạn khớp cắt ngang ký tự tổ hợp hoặc emoji nên không được chọn."
              : "Không có vị trí khớp nguyên văn trong phản hồi (phân biệt chữ hoa/thường và khoảng trắng)."}
          </p>
        )}

        {validOccurrences.length > 1 && (
          <fieldset className="sensitivity-occurrences">
            <legend>
              Tìm thấy {validOccurrences.length} lần xuất hiện — chọn 1 vị trí
            </legend>
            {validOccurrences.map((occ, idx) => {
              const ctxStart = snapContextStart(
                item.text,
                occ.start_utf16 - 18,
                boundaryInfo,
              );
              const ctxEnd = snapContextEnd(
                item.text,
                occ.end_utf16 + 18,
                boundaryInfo,
              );
              const beforeCtx = item.text.slice(ctxStart, occ.start_utf16);
              const afterCtx = item.text.slice(occ.end_utf16, ctxEnd);
              const isChecked =
                selectedSpan != null &&
                selectedSpan.start_utf16 === occ.start_utf16 &&
                selectedSpan.end_utf16 === occ.end_utf16;
              return (
                <label
                  className="sensitivity-radio-option"
                  key={`${occ.start_utf16}-${occ.end_utf16}`}
                >
                  <input
                    ref={idx === 0 ? firstRadioRef : undefined}
                    type="radio"
                    name={radioGroupName}
                    checked={isChecked}
                    onChange={() => handlePickOccurrence(occ)}
                  />
                  <span>
                    <strong>
                      Lần {idx + 1}/{validOccurrences.length}
                    </strong>{" "}
                    <span className="muted small">
                      {ctxStart > 0 ? "…" : ""}
                      {beforeCtx}
                      <mark className="sensitivity-match-mark">{occ.text}</mark>
                      {afterCtx}
                      {ctxEnd < item.text.length ? "…" : ""}
                    </span>
                  </span>
                </label>
              );
            })}
          </fieldset>
        )}

        {previewVariant !== null && selectedSpan && (
          <div className="sensitivity-preview">
            <span className="muted small">
              Xem trước văn bản sau khi bỏ (đoạn dài {selectedSpan.text.length}{" "}
              đơn vị UTF-16 tại vị trí {selectedSpan.start_utf16}–
              {selectedSpan.end_utf16}):
            </span>
            <p className="sensitivity-variant-preview">{previewVariant}</p>
            {liveValidation && !liveValidation.ok && (
              <p className="error-text small">{liveValidation.message}</p>
            )}
          </div>
        )}

        {selectionMessage && (
          <p id={errorId} className="error-text small" role="alert">
            {selectionMessage}
          </p>
        )}

        <div className="inline-actions sensitivity-actions">
          <button
            type="button"
            className="primary"
            disabled={
              !!cannotCreateReason || submitting || actionBusy || isJobActive
            }
            onClick={() => void handleSubmit()}
          >
            {submitting ? "Đang gửi thử nghiệm…" : "Chạy thử khi bỏ đoạn"}
          </button>
        </div>

        {submitError && !submitError.focusSelection && (
          <div className="notice warning small" role="alert">
            <span>{submitError.message}</span>
            {submitError.existingJobId && (
              <div className="inline-actions">
                <button
                  type="button"
                  disabled={actionBusy || submitting}
                  onClick={() => {
                    if (actionBusyRef.current || submittingRef.current) return;
                    const existingId = submitError.existingJobId!;
                    const nextSeq = retrySeqRef.current + 1;
                    retrySeqRef.current = nextSeq;
                    setSubmitError(null);
                    setActionError(null);
                    activeJobIdRef.current = existingId;
                    updateTrackedJob({
                      experimentId: existingId,
                      jobId: existingId,
                      status: "running",
                      cancelRequested: false,
                      attempt: nextSeq,
                    });
                    setRetrySeq(nextSeq);
                    setExperimentId(existingId);
                  }}
                >
                  Xem thử nghiệm đang chạy
                </button>
                <button
                  type="button"
                  disabled={actionBusy || submitting}
                  onClick={() =>
                    void handleCancelActive(submitError.existingJobId!)
                  }
                >
                  Hủy thử nghiệm đang chạy
                </button>
              </div>
            )}
            {submitError.needsReload && (
              <button
                type="button"
                onClick={() => {
                  setSubmitError(null);
                  onReloadItem();
                }}
              >
                Tải lại phản hồi
              </button>
            )}
          </div>
        )}

        {experimentId != null && (
          <div className="sensitivity-result-area">
            {isConfirmedNotFound ? (
              <div className="notice warning small" role="status">
                Kết quả tạm đã hết hạn hoặc không còn tồn tại; chạy lại nếu cần.
              </div>
            ) : !isJobActive &&
              activeTracked?.status === "cancelled" &&
              (!exp || activeJob(exp.status)) ? (
              <div className="notice small" role="status" aria-live="polite">
                <strong>Đã hủy thử nghiệm</strong>
                <span>Bạn có thể chọn lại đoạn hoặc bấm chạy thử mới.</span>
              </div>
            ) : experimentQuery.isError && isJobActive ? (
              <>
                <ErrorNotice
                  error={experimentQuery.error}
                  retry={() => void experimentQuery.refetch()}
                />
                {knownJobId && (
                  <div
                    className="sensitivity-status"
                    role="status"
                    aria-live="polite"
                  >
                    <div>
                      <strong>
                        {knownCancelRequested
                          ? "Đang gửi hủy thử nghiệm…"
                          : "Không đọc được trạng thái thử nghiệm hiện tại"}
                      </strong>
                      <span className="muted small">
                        {" "}
                        · Tách biệt với dự đoán AI gốc đã lưu
                      </span>
                    </div>
                    <button
                      type="button"
                      disabled={actionBusy || submitting || knownCancelRequested}
                      onClick={() => void handleCancelActive(knownJobId)}
                    >
                      {knownCancelRequested
                        ? "Đang gửi hủy…"
                        : "Hủy thử nghiệm"}
                    </button>
                  </div>
                )}
              </>
            ) : !exp ? (
              experimentQuery.isError ? (
                <ErrorNotice
                  error={experimentQuery.error}
                  retry={() => void experimentQuery.refetch()}
                />
              ) : (
                <div
                  className="sensitivity-status"
                  role="status"
                  aria-live="polite"
                >
                  <div>
                    <strong>
                      {activeStatusText(activeTracked?.status ?? "queued")}
                    </strong>
                    <span className="muted small">
                      {" "}
                      · Tách biệt với dự đoán AI gốc đã lưu
                    </span>
                  </div>
                  <button
                    type="button"
                    disabled={actionBusy || submitting || knownCancelRequested}
                    onClick={() =>
                      void handleCancelActive(knownJobId ?? experimentId)
                    }
                  >
                    {knownCancelRequested ? "Đang gửi hủy…" : "Hủy thử nghiệm"}
                  </button>
                </div>
              )
            ) : activeJob(exp.status) ? (
              <div
                className="sensitivity-status"
                role="status"
                aria-live="polite"
              >
                <div>
                  <strong>{activeStatusText(exp.status)}</strong>
                  <span className="muted small">
                    {" "}
                    · Tách biệt với dự đoán AI gốc đã lưu
                  </span>
                </div>
                <button
                  type="button"
                  disabled={actionBusy || submitting || knownCancelRequested}
                  onClick={() => void handleCancelActive(exp.job_id)}
                >
                  {knownCancelRequested ? "Đang gửi hủy…" : "Hủy thử nghiệm"}
                </button>
              </div>
            ) : exp.status === "cancelled" ? (
              <div className="notice small" role="status" aria-live="polite">
                <strong>Đã hủy thử nghiệm</strong>
                <span>Bạn có thể chọn lại đoạn hoặc bấm chạy thử mới.</span>
              </div>
            ) : exp.status === "interrupted" ||
              exp.status === "failed" ||
              exp.status === "completed_with_errors" ? (
              <div className="notice warning small" role="status" aria-live="polite">
                <strong>
                  {exp.status === "interrupted"
                    ? "Thử nghiệm bị gián đoạn"
                    : "Thử nghiệm không thể hoàn tất"}
                </strong>
                <span>
                  {exp.error?.message ??
                    "Không có kết quả hoàn chỉnh cho cặp văn bản này."}
                </span>
                {exp.error?.code && (
                  <span className="muted small technical-reason">
                    Mã lỗi: {exp.error.code}
                  </span>
                )}
                <button
                  type="button"
                  disabled={actionBusy || submitting}
                  onClick={() => void handleRetryExperiment(exp.job_id)}
                >
                  Thử lại thử nghiệm
                </button>
              </div>
            ) : exp.status === "completed" && exp.result ? (
              <ExperimentResultView
                experiment={exp}
                profile={profile}
                hadSourcePrediction={exp.source.prediction_id !== null}
              />
            ) : (
              <div className="notice warning small">
                Chưa có dữ liệu so sánh hợp lệ cho trạng thái {exp.status}.
              </div>
            )}
          </div>
        )}

        {actionError && (
          <p className="error-text small" role="alert">
            {actionError}
          </p>
        )}
      </div>
    </details>
  );
}

function ExperimentResultView({
  experiment,
  profile,
  hadSourcePrediction,
}: {
  experiment: SensitivityExperiment;
  profile: Profile;
  hadSourcePrediction: boolean;
}) {
  const res = experiment.result!;
  const hasInputEqual =
    res.model_input_equal || res.warnings.includes("MODEL_INPUT_UNCHANGED");
  const hasTokenWindowWarning = res.warnings.includes(
    "TOKEN_WINDOW_MAY_CHANGE",
  );
  const anyTruncated =
    res.baseline.prediction.truncated || res.variant.prediction.truncated;

  return (
    <div className="sensitivity-results">
      <div className="notice small" role="note">
        <strong>
          Thử nghiệm độ nhạy: thay đổi đầu vào có thể làm thay đổi nghĩa; đây
          không phải bằng chứng chắc chắn về nguyên nhân model dự đoán.
        </strong>
      </div>

      {!hadSourcePrediction && (
        <p className="muted small">
          Phản hồi này chưa có dự đoán AI gốc trước đó; cặp gốc và biến thể
          được tính mới cho thử nghiệm và không thay thế phần Dự đoán AI gốc.
        </p>
      )}
      {hadSourcePrediction && experiment.execution.source_model_changed && (
        <p className="muted small">
          Tính lại cả hai văn bản bằng model hiện tại; dự đoán đã lưu không thay
          đổi.
        </p>
      )}
      {experiment.source_stale && (
        <div className="notice warning small">
          Văn bản nguồn đã thay đổi sang phiên bản mới sau khi chạy thử nghiệm.
          Kết quả bên dưới thuộc ảnh chụp văn bản tại thời điểm thử nghiệm.
        </div>
      )}
      {experiment.active_model_changed && (
        <div className="notice small">
          Model đang kích hoạt hiện tại đã khác với model ({experiment.execution.model_id}{" "}
          · {experiment.execution.model_version}) lúc chạy thử nghiệm này.
        </div>
      )}

      {(hasInputEqual || hasTokenWindowWarning || anyTruncated) && (
        <div className="notice warning small">
          {hasInputEqual && (
            <span>
              Sau tiền xử lý và cắt ngắn, đầu vào model của hai văn bản giống
              nhau.
            </span>
          )}
          {hasTokenWindowWarning && (
            <span>
              Bỏ đoạn có thể đổi cách tách từ và đưa phần văn bản phía sau vào
              giới hạn 128 token.
            </span>
          )}
          {anyTruncated && (
            <span>
              Số token trước cắt: Gốc{" "}
              {res.baseline.prediction.token_count_before_truncation}
              {res.baseline.prediction.truncated ? " (bị cắt)" : ""} · Sau bỏ{" "}
              {res.variant.prediction.token_count_before_truncation}
              {res.variant.prediction.truncated ? " (bị cắt)" : ""}.
            </span>
          )}
        </div>
      )}

      <div className="sensitivity-pair">
        <div className="sensitivity-pair-card">
          <div className="sensitivity-pair-head">
            <strong>Văn bản gốc · chạy lại cho thử nghiệm</strong>
            <span className="muted small">
              {res.baseline.prediction.token_count_before_truncation} token trước
              cắt
            </span>
          </div>
          <p className="sensitivity-pair-text">{res.baseline.text}</p>
          <div className="sensitivity-leading-tags">
            {TASKS.map((task) => (
              <Badge key={task} tone="neutral">
                {task === "sentiment" ? "Cảm xúc" : "Chủ đề"}:{" "}
                {labelName(
                  profile,
                  task,
                  res.comparison[task].baseline_label_id,
                )}
              </Badge>
            ))}
          </div>
        </div>

        <div className="sensitivity-pair-card">
          <div className="sensitivity-pair-head">
            <strong>Văn bản sau khi bỏ đoạn</strong>
            <span className="muted small">
              {res.variant.prediction.token_count_before_truncation} token trước
              cắt
            </span>
          </div>
          <p className="sensitivity-pair-text">{res.variant.text}</p>
          <div className="sensitivity-leading-tags">
            {TASKS.map((task) => (
              <Badge key={task} tone="neutral">
                {task === "sentiment" ? "Cảm xúc" : "Chủ đề"}:{" "}
                {labelName(
                  profile,
                  task,
                  res.comparison[task].variant_label_id,
                )}
              </Badge>
            ))}
          </div>
        </div>
      </div>

      <p className="muted small">
        Điểm trên thang 0–1 (chưa hiệu chuẩn; không phải xác suất dự đoán đúng).
        Nhãn dẫn đầu không đổi vẫn là một kết quả hợp lệ.
      </p>

      {TASKS.map((task) => (
        <TaskComparisonBlock
          key={task}
          task={task}
          profile={profile}
          comparison={res.comparison[task]}
        />
      ))}

      <p className="muted small model-info">
        Model chạy thử: {experiment.execution.model_id} ·{" "}
        {experiment.execution.model_version} · {experiment.execution.mode}
        {experiment.expires_at
          ? ` · Kết quả tạm lưu đến ${date(experiment.expires_at)}`
          : ""}
      </p>
    </div>
  );
}

function TaskComparisonBlock({
  task,
  profile,
  comparison,
}: {
  task: Task;
  profile: Profile;
  comparison: SensitivityTaskComparison;
}) {
  const [showAll, setShowAll] = useState(false);

  const highlightIds = useMemo(() => {
    const ids: number[] = [comparison.baseline_label_id];
    if (comparison.variant_label_id !== comparison.baseline_label_id) {
      ids.push(comparison.variant_label_id);
    }
    return new Set(ids);
  }, [comparison.baseline_label_id, comparison.variant_label_id]);

  const highlightedRows = comparison.scores.filter((row) =>
    highlightIds.has(row.label_id),
  );
  const labelSwitched =
    comparison.baseline_label_id !== comparison.variant_label_id;

  const renderRows = (rows: SensitivityScoreDelta[]) =>
    rows.map((row) => {
      const isBaselineLeader = row.label_id === comparison.baseline_label_id;
      const isVariantLeader = row.label_id === comparison.variant_label_id;
      const roleNote =
        isBaselineLeader && isVariantLeader
          ? "Dẫn đầu gốc & sau bỏ"
          : isBaselineLeader
            ? "Dẫn đầu gốc"
            : isVariantLeader
              ? "Dẫn đầu sau bỏ"
              : null;

      return (
        <tr key={row.label_id}>
          <td>
            <div className="sensitivity-label-cell">
              <span>{labelName(profile, task, row.label_id)}</span>
              {roleNote && <span className="muted small">{roleNote}</span>}
            </div>
          </td>
          <td className="num">{formatScore3(row.before)}</td>
          <td className="num">{formatScore3(row.after)}</td>
          <td className="num">{formatDelta3(row.delta)}</td>
        </tr>
      );
    });

  return (
    <div className="sensitivity-task-block">
      <div className="sensitivity-task-head">
        <h4>{task === "sentiment" ? "Cảm xúc" : "Chủ đề"}</h4>
        <Badge tone={labelSwitched ? "accent" : "neutral"}>
          {labelSwitched
            ? `Đổi nhãn dẫn đầu: ${labelName(profile, task, comparison.baseline_label_id)} → ${labelName(profile, task, comparison.variant_label_id)}`
            : `Nhãn dẫn đầu không đổi: ${labelName(profile, task, comparison.baseline_label_id)}`}
        </Badge>
      </div>
      <div className="table-scroll sensitivity-table-scroll">
        <table className="sensitivity-table">
          <thead>
            <tr>
              <th>Nhãn</th>
              <th className="num">Gốc</th>
              <th className="num">Sau bỏ</th>
              <th className="num">Chênh lệch</th>
            </tr>
          </thead>
          <tbody>
            {renderRows(showAll ? comparison.scores : highlightedRows)}
          </tbody>
        </table>
      </div>
      {comparison.scores.length > highlightedRows.length && (
        <button
          type="button"
          className="quiet sensitivity-expand-btn"
          aria-expanded={showAll}
          onClick={() => setShowAll((prev) => !prev)}
        >
          {showAll
            ? "Thu gọn chỉ xem nhãn dẫn đầu"
            : `Xem tất cả ${comparison.scores.length} nhãn`}
        </button>
      )}
    </div>
  );
}
