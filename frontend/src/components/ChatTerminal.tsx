import { useRef, useState } from "react";
import { streamChat, uploadChatFile, type ChatAttachment } from "../api";

interface Line {
  role: "user" | "agent" | "system";
  text: string;
}

const COMMANDS = [
  ["/akademik", "akademik görev"],
  ["/proje", "proje (+dosya)"],
  ["/odev", "ödev"],
  ["/seans", "çalışma seansı"],
  ["/gunluk", "günlük görev"],
  ["/duzenle", "görev düzenle"],
  ["/antrenman", "tek antrenman"],
  ["/plan", "plan içe aktar"],
  ["/not", "<ipucu>: not"],
  ["/yardim", "komutlar"],
];

export default function ChatTerminal() {
  const [lines, setLines] = useState<Line[]>([
    { role: "system", text: "Jarvis-Academic hazır. Soru sor, görev/PDF/antrenman iste, ya da /yardim yaz." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  function push(line: Line) {
    setLines((prev) => [...prev, line]);
    requestAnimationFrame(() =>
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
    );
  }

  async function attach(file: File) {
    push({ role: "system", text: `↑ ${file.name} yükleniyor…` });
    try {
      const a = await uploadChatFile(file);
      setAttachments((prev) => [...prev, a]);
      push({ role: "system", text: `✓ ${a.name} eklendi (${a.chars} karakter)` });
    } catch (e) {
      push({ role: "system", text: `dosya hatası: ${(e as Error).message}` });
    }
  }

  async function send() {
    const message = input.trim();
    if ((!message && attachments.length === 0) || busy) return;
    setInput("");
    const ids = attachments.map((a) => a.id);
    push({ role: "user", text: message + (ids.length ? ` 📎${ids.length}` : "") });
    setAttachments([]);
    setBusy(true);
    try {
      await streamChat(
        message,
        (evt) => {
          if (evt.type === "message") push({ role: "agent", text: String(evt.content) });
          else if (evt.type === "tool") push({ role: "system", text: `→ tool: ${String(evt.active_tool)}` });
          else if (evt.type === "error") push({ role: "system", text: `error: ${String(evt.error)}` });
        },
        ids
      );
    } catch (e) {
      push({ role: "system", text: `error: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  }

  const color = {
    user: "text-sky-300",
    agent: "text-emerald-300",
    system: "text-zinc-500",
  } as const;

  const showHint = input.startsWith("/");

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-zinc-800 bg-black/60 shadow-lg shadow-black/20">
      <div className="border-b border-zinc-800 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-zinc-400">
        Agent Terminal
      </div>
      <div ref={scrollRef} className="min-h-0 flex-1 space-y-1 overflow-y-auto p-4 font-mono text-sm">
        {lines.map((l, i) => (
          <div key={i} className={color[l.role]}>
            <span className="select-none text-zinc-600">
              {l.role === "user" ? "$ " : l.role === "agent" ? "» " : "# "}
            </span>
            {l.text}
          </div>
        ))}
        {busy && <div className="text-zinc-600">…düşünüyor</div>}
      </div>

      {showHint && (
        <div className="flex flex-wrap gap-1.5 border-t border-zinc-800 px-3 py-2 text-xs">
          {COMMANDS.filter(([c]) => c.startsWith(input.split(" ")[0])).map(([c, d]) => (
            <button
              key={c}
              onClick={() => setInput(c + " ")}
              className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-400 hover:border-emerald-500 hover:text-emerald-300"
            >
              {c} <span className="text-zinc-600">{d}</span>
            </button>
          ))}
        </div>
      )}

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-zinc-800 px-3 py-2">
          {attachments.map((a) => (
            <span key={a.id} className="inline-flex items-center gap-1 rounded border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300">
              📎 {a.name}
              <button onClick={() => setAttachments((p) => p.filter((x) => x.id !== a.id))} className="text-emerald-400/70 hover:text-emerald-200">×</button>
            </span>
          ))}
        </div>
      )}

      <div className="flex gap-2 border-t border-zinc-800 p-3">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,image/*,.md,.markdown,.txt,.json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void attach(f);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          title="Dosya ekle (PDF/görüntü/.md/.json)"
          className="rounded-lg border border-zinc-700 px-3 py-2 text-sm text-zinc-300 hover:border-zinc-500"
        >
          📎
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void send()}
          placeholder="Mesaj yaz… ('/' ile komutlar)"
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 font-mono text-sm text-zinc-100 outline-none focus:border-emerald-500"
        />
        <button
          onClick={() => void send()}
          disabled={busy}
          className="rounded-lg bg-emerald-500/90 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-emerald-400 disabled:opacity-50"
        >
          Gönder
        </button>
      </div>
    </div>
  );
}
