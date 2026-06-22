import type { Line } from "../../ChatContext";
import AgentMarkdown from "./markdown";

// Friendly labels for the tools the LangGraph agent can surface.
const TOOL_LABELS: Record<string, string> = {
  add_task: "Görev oluşturma",
  process_pdf: "PDF işleme",
  extract_ideas: "Fikir çıkarma",
  add_session: "Seans ekleme",
  deep_research: "Derin araştırma",
};

/** A visually distinct card shown when the agent invokes a tool. */
function ToolCallBlock({ tool }: { tool: string }) {
  const label = TOOL_LABELS[tool] || tool;
  return (
    <div className="my-1 inline-flex items-center gap-2 rounded-lg border border-primary-500/40 bg-primary-500/10 px-3 py-1.5 text-xs text-primary-200">
      <span aria-hidden>🛠</span>
      <span className="text-zinc-400">Araç kullanıldı:</span>
      <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono text-primary-300">
        {tool}
      </code>
      <span className="text-zinc-500">({label})</span>
    </div>
  );
}

/** Live Deep Research progress panel (phases / rounds / sources). */
function ResearchProgressPanel({ text }: { text: string }) {
  return (
    <div className="my-1 flex w-full max-w-[85%] items-center gap-2.5 rounded-lg border border-accent-400/40 bg-accent-400/10 px-3 py-2 text-xs text-accent-300">
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400/70" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent-400" />
      </span>
      <span className="font-medium uppercase tracking-wider text-accent-300">
        Derin Araştırma
      </span>
      <span className="truncate text-zinc-300">{text}</span>
    </div>
  );
}

export interface ChatMessageProps {
  line: Line;
  index: number;
  showActions: boolean;
  onCopy: (text: string) => void;
  onEdit: (index: number) => void;
  onRegenerate: (index: number) => void;
}

export default function ChatMessage({
  line,
  index,
  showActions,
  onCopy,
  onEdit,
  onRegenerate,
}: ChatMessageProps) {
  // Distinct system blocks.
  if (line.role === "system" && line.kind === "tool") {
    return (
      <div className="flex flex-col items-start">
        <ToolCallBlock tool={line.text} />
      </div>
    );
  }
  if (line.role === "system" && line.kind === "research") {
    return (
      <div className="flex flex-col items-start">
        <ResearchProgressPanel text={line.text} />
      </div>
    );
  }

  return (
    <div
      className={`group flex flex-col ${
        line.role === "user" ? "items-end" : "items-start"
      }`}
    >
      <div
        className={`relative max-w-[85%] px-4 py-2.5 leading-relaxed ${
          line.role === "user"
            ? "rounded-[18px_18px_0_18px] bg-surface-2 text-primary-200"
            : line.role === "agent"
            ? "rounded-[18px_18px_18px_0] border border-line bg-elevated text-primary-200"
            : "bg-transparent text-zinc-500"
        }`}
      >
        {line.role === "system" && <span className="select-none mr-2">#</span>}
        {line.role === "agent" ? (
          <AgentMarkdown text={line.text} />
        ) : (
          <span className="whitespace-pre-wrap">{line.text}</span>
        )}

        {/* Hover actions */}
        {line.role !== "system" && showActions && (
          <div
            className={`absolute top-0 flex gap-1 rounded border border-line-strong bg-elevated p-0.5 opacity-0 transition-opacity group-hover:opacity-100 ${
              line.role === "user" ? "-left-16" : "-right-16"
            }`}
          >
            <button
              onClick={() => onCopy(line.text)}
              className="px-1 text-zinc-400 hover:text-zinc-200"
              title="Kopyala"
            >
              📋
            </button>
            {line.role === "user" && (
              <button
                onClick={() => onEdit(index)}
                className="px-1 text-zinc-400 hover:text-primary-300"
                title="Düzenle"
              >
                ✏️
              </button>
            )}
            {line.role === "agent" && (
              <button
                onClick={() => onRegenerate(index)}
                className="px-1 text-zinc-400 hover:text-primary-300"
                title="Yeniden Üret"
              >
                🔄
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
