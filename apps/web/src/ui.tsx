import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";

/** Keep dialog focus restoration reliable when React removes it from the DOM. */
export function useDialogFocus() {
  const ref = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    const dialog = ref.current;
    const currentGeneration = ++generation.current;
    if (!opener.current && document.activeElement instanceof HTMLElement) {
      opener.current = document.activeElement;
    }
    dialog?.showModal();
    return () => {
      dialog?.close();
      queueMicrotask(() => {
        // StrictMode replays effects; an earlier cleanup must not steal focus
        // from the reopened dialog or a replacement item-detail dialog.
        if (
          generation.current === currentGeneration &&
          opener.current?.isConnected &&
          !document.querySelector("dialog[open]")
        ) {
          opener.current.focus({ preventScroll: true });
        }
      });
    };
  }, []);
  return ref;
}
export function ErrorNotice({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="notice error" role="alert">
      <strong>Không thể hoàn tất yêu cầu.</strong>
      <span>{error instanceof Error ? error.message : String(error)}</span>
      {error instanceof ApiError && error.details != null && (
        <details>
          <summary>Chi tiết lỗi dữ liệu</summary>
          <pre className="technical-reason">
            {JSON.stringify(error.details, null, 2)}
          </pre>
        </details>
      )}
      {retry && <button onClick={retry}>Thử lại</button>}
    </div>
  );
}
export function Loading({ text = "Đang tải dữ liệu…" }: { text?: string }) {
  return (
    <div role="status" className="loading">
      <span>{text}</span>
      <div />
      <div />
      <div />
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-symbol" aria-hidden="true">
        ▤
      </div>
      <h2>{title}</h2>
      {children}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useDialogFocus();
  return (
    <dialog
      ref={ref}
      className={wide ? "modal wide" : "modal"}
      aria-labelledby="modal-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2 id="modal-title">{title}</h2>
        <button className="icon-button" aria-label="Đóng" onClick={onClose}>
          ×
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "warning" | "success" | "accent";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
