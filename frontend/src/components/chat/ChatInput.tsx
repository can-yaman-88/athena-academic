import { useRef, useState } from "react";
import type { ChatAttachment } from "../../api";

const ACCEPT = ".pdf,image/*,.md,.markdown,.txt,.json";

export interface ChatInputProps {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  attachments: ChatAttachment[];
  onRemoveAttachment: (id: string) => void;
  onAttachFiles: (files: File[]) => void;
  onExpand: () => void;
}

export default function ChatInput({
  input,
  setInput,
  onSend,
  busy,
  attachments,
  onRemoveAttachment,
  onAttachFiles,
  onExpand,
}: ChatInputProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files || []);
    if (files.length) onAttachFiles(files);
  };

  return (
    <div
      className="relative"
      onDragOver={(e) => {
        e.preventDefault();
        if (!dragging) setDragging(true);
      }}
      onDragLeave={(e) => {
        // Only clear when leaving the wrapper, not its children.
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={handleDrop}
    >
      {/* Drag-and-drop overlay */}
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-lg border-2 border-dashed border-primary-400 bg-primary-500/15 text-sm font-medium text-primary-200">
          📎 Dosyaları bırak (PDF / görüntü / metin)
        </div>
      )}

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div className="border-t border-line bg-surface-2 px-3 py-2">
          <div className="mx-auto flex max-w-5xl flex-wrap gap-1.5">
            {attachments.map((a) => (
              <span
                key={a.id}
                className="inline-flex items-center gap-1 rounded border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-xs text-primary-300"
              >
                📎 {a.name}
                <button
                  onClick={() => onRemoveAttachment(a.id)}
                  className="text-primary-400/70 hover:text-primary-200"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="border-t border-line bg-surface-2/60 p-3">
        <div className="mx-auto flex max-w-5xl gap-2">
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onAttachFiles([f]);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            title="Dosya ekle (PDF/görüntü/.md/.json)"
            className="rounded-lg border border-line-strong bg-elevated px-3 py-2 text-sm text-zinc-300 hover:border-zinc-500"
          >
            📎
          </button>
          <textarea
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Mesaj yaz… ('/' ile komutlar, '@' ile bahset)"
            className="field max-h-[8rem] min-h-[2.5rem] flex-1 resize-none px-3 py-2 font-chat text-sm text-zinc-100"
          />
          <button
            onClick={onExpand}
            title="Mesajı genişlet"
            className="rounded-lg border border-line-strong bg-elevated px-3 py-2 text-sm text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
          >
            ⛶
          </button>
          <button
            onClick={onSend}
            disabled={busy}
            className="rounded-lg bg-primary-500/90 px-4 py-2 text-sm font-medium text-zinc-950 transition-colors hover:bg-primary-400 disabled:opacity-50"
          >
            Gönder
          </button>
        </div>
      </div>
    </div>
  );
}
