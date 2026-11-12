import { useCallback, useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { ApiError, cancelAttribution, createAttribution, getAttribution } from "./api";
import type { AttributionResponse, AttributionTarget } from "./types";
import { defaultAttributionTarget, validateAttribution } from "./attributionValidation";
import type { AttributionSource } from "./attributionValidation";

type Operation = {
  source: AttributionSource;
  target: AttributionTarget;
  generation: number;
  key: string;
  id?: string;
  abandoned: boolean;
  cancelled: boolean;
  terminal: boolean;
  stage: "post" | "get";
  sourceKey: string;
  inFlight: boolean;
  requestEpoch: number;
  timer?: ReturnType<typeof setTimeout>;
  wake?: () => void;
};
type State = { data: AttributionResponse | null; loading: boolean; error: string | null; status: string };
const empty: State = { data: null, loading: false, error: null, status: "empty" };
const terminal = new Set(["completed", "failed", "cancelled", "unsupported"]);
const cancelQuietly = (id?: string) => { if (id) void cancelAttribution(id).catch(() => {}); };
const recoverable = (error: unknown) => error instanceof ApiError && (!error.status || error.status >= 500);
const sourceKey = (source: AttributionSource | null) => source ? JSON.stringify([
  source.jobId, source.item.id, source.item.revision_id, source.item.text, source.profile.id,
  source.profile.schema_id, source.prediction.id, source.prediction.run_id,
  source.prediction.model_id, source.prediction.model_version, source.prediction.schema_id,
  source.prediction.execution_identity, source.prediction.sentiment, source.prediction.topic,
]) : "";
const message = (error: unknown) => {
  if (error instanceof ApiError && [404, 410].includes(error.status ?? 0)) return "Nguồn phân tích đã hết hạn hoặc không còn. Hãy phân tích lại câu.";
  return error instanceof Error ? error.message : "Không thể tính đóng góp từ ngữ.";
};

export function useAttribution(
  source: AttributionSource | null,
  generation: MutableRefObject<number>,
  mounted: MutableRefObject<boolean>,
) {
  const operation = useRef<Operation | null>(null);
  const [state, setState] = useState<State>(empty);
  const current = useCallback((op: Operation) => mounted.current && generation.current === op.generation &&
    operation.current === op && !op.abandoned, [generation, mounted]);
  const discard = useCallback(() => {
    const op = operation.current;
    if (op) {
      op.abandoned = true;
      clearTimeout(op.timer);
      op.wake?.();
      cancelQuietly(op.id);
    }
    operation.current = null;
  }, []);

  const consume = useCallback(async (op: Operation, result: AttributionResponse) => {
    if (!current(op) || op.cancelled) { cancelQuietly(result.attribution_id); return; }
    if (op.terminal) return;
    const requestEpoch = op.requestEpoch;
    if (!result.attribution_id || (op.id && result.attribution_id !== op.id) ||
        !["queued", "running", ...terminal].includes(result.status)) throw new Error("Trạng thái đóng góp không hợp lệ.");
    op.id = result.attribution_id;
    if (result.status === "completed") {
      await validateAttribution(result, op.source, op.target);
      if (!current(op) || op.cancelled || op.terminal || op.requestEpoch !== requestEpoch) return;
      op.terminal = true;
      setState({ data: result, loading: false, error: null, status: result.status });
    } else if (terminal.has(result.status)) {
      op.terminal = true;
      const detail = result.status === "cancelled" ? "Đã hủy tính đóng góp. Có thể thử lại." :
        result.error?.message || (result.status === "unsupported" ? "Chưa hỗ trợ ánh xạ từ ngữ của đầu vào này." : "Không thể tính đóng góp từ ngữ.");
      setState({ data: null, loading: false, error: detail, status: result.status });
    }
  }, [current]);

  const execute = useCallback(async (op: Operation) => {
    if (!current(op) || op.cancelled || op.terminal || op.inFlight) return;
    op.inFlight = true;
    try {
    let failures = 0;
    while (current(op) && !op.cancelled && !op.terminal) {
      const requestEpoch = op.requestEpoch;
      try {
        const result = op.stage === "post"
          ? await createAttribution(op.source.jobId, op.source.prediction.id!, op.target, op.key)
          : await getAttribution(op.id!);
        // A late POST must still yield its server handle so only that operation is cancelled.
        if (!current(op) || op.cancelled) { cancelQuietly(result.attribution_id); return; }
        if (op.terminal || op.requestEpoch !== requestEpoch) return;
        await consume(op, result);
        if (!current(op) || op.cancelled || op.terminal) return;
        op.stage = "get";
        failures = 0;
        await new Promise<void>((resolve) => { op.wake = resolve; op.timer = setTimeout(resolve, 700); });
      } catch (error) {
        if (!current(op) || op.cancelled || op.terminal || op.requestEpoch !== requestEpoch) return;
        if (recoverable(error) && failures++ < 2) {
          await new Promise<void>((resolve) => { op.wake = resolve; op.timer = setTimeout(resolve, 400 * failures); });
          continue;
        }
        // HTTP source errors and malformed payloads are final. A transport error can resume
        // the same GET/POST and idempotency key without creating another prediction.
        op.terminal = !recoverable(error);
        setState({ data: null, loading: false, error: message(error), status:
          error instanceof ApiError && [404, 410, 409, 422].includes(error.status ?? 0) ? "source_error" : "error" });
        return;
      }
    }
    } finally { op.inFlight = false; }
  }, [consume, current]);

  const start = useCallback((next: AttributionSource) => {
    discard();
    let target: AttributionTarget;
    try { target = defaultAttributionTarget(next.prediction, next.profile); }
    catch (error) { setState({ ...empty, error: message(error), status: "error" }); return; }
    const op: Operation = { source: next, target, generation: generation.current, key: crypto.randomUUID(),
      abandoned: false, cancelled: false, terminal: false, stage: "post", sourceKey: sourceKey(next), inFlight: false, requestEpoch: 0 };
    operation.current = op;
    setState({ data: null, loading: true, error: null, status: "queued" });
    // React StrictMode can replay setup/cleanup in this tick. Only the surviving owner sends POST.
    queueMicrotask(() => { if (current(op)) void execute(op); });
  }, [current, discard, execute, generation]);

  const signature = sourceKey(source);
  const sourceRef = useRef(source);
  sourceRef.current = source;
  useEffect(() => {
    if (sourceRef.current) start(sourceRef.current);
    else { discard(); setState(empty); }
    return discard;
  }, [signature, start, discard]);

  const retry = useCallback(() => {
    const op = operation.current;
    if (op && current(op) && !op.cancelled && !op.terminal) {
      setState({ data: null, loading: true, error: null, status: "running" });
      void execute(op);
    } else if (sourceRef.current) start(sourceRef.current);
  }, [current, execute, start]);
  const cancel = useCallback(async () => {
    const op = operation.current;
    if (!op || !current(op) || op.terminal) return;
    // Cancel recovery owns all later responses, including while its completed
    // payload is being validated. A prior poll cannot win that validation race.
    op.requestEpoch += 1;
    op.cancelled = true;
    clearTimeout(op.timer);
    op.wake?.();
    setState({ data: null, loading: false, error: "Đã hủy tính đóng góp. Có thể thử lại.", status: "cancelled" });
    if (!op.id) return;
    try {
      const result = await cancelAttribution(op.id);
      if (!current(op)) return;
      if (result.status === "completed") {
        const completed = await getAttribution(op.id);
        if (!current(op)) return;
        op.cancelled = false;
        await consume(op, completed);
      }
    } catch (error) {
      if (current(op) && !op.terminal) setState({ data: null, loading: false, error: message(error), status: "error" });
    }
  }, [consume, current]);
  // Effects run after render. Never expose the previous owner's state during that interval.
  const ownedState = operation.current && current(operation.current) && operation.current.sourceKey === signature ? state : empty;
  return { ...ownedState, retry, cancel, discard };
}
