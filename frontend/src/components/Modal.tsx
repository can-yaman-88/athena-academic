import { useEffect } from "react";
import type { ReactNode } from "react";

/**
 * A Notion-style centered modal: blurred backdrop + a card that scales/fades in
 * from the center. Closes on Esc or backdrop click. The entrance animation is the
 * `modal-pop` keyframe defined in index.css (respects prefers-reduced-motion).
 */
export default function Modal({
  open,
  onClose,
  title,
  children,
  widthClass = "max-w-5xl",
}: {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  widthClass?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`flex max-h-[85vh] w-full ${widthClass} flex-col overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-950 shadow-card-hover [animation:modal-pop_180ms_ease-out]`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-3">
          <h2 className="text-sm font-semibold tracking-wide text-zinc-200">{title}</h2>
          <button
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            aria-label="Kapat"
          >
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden p-4">{children}</div>
      </div>
    </div>
  );
}
