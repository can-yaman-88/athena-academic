import { useEffect, useRef, useState } from "react";
import { API_URL, type LogRecord } from "../api";

const levelColor: Record<string, string> = {
  ERROR: "text-rose-400",
  WARNING: "text-amber-300",
  INFO: "text-zinc-300",
  DEBUG: "text-zinc-500",
};

export default function LogStream({
  large = false,
  right,
}: {
  large?: boolean;
  right?: React.ReactNode;
}) {
  const [lines, setLines] = useState<LogRecord[]>([]);
  const [connected, setConnected] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource(`${API_URL}/logs/stream`);
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (ev) => {
      try {
        const rec = JSON.parse(ev.data) as LogRecord;
        if (!rec.message) return;
        setLines((prev) => [...prev.slice(-400), rec]);
        requestAnimationFrame(() =>
          scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
        );
      } catch {
        /* keep-alive / malformed frame */
      }
    };
    return () => es.close();
  }, []);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-zinc-800 bg-black/60 shadow-lg shadow-black/20">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
          Canlı Sistem Logları
        </h2>
        <div className="flex items-center gap-3">
          {right}
          <span className="flex items-center gap-1.5 text-xs text-zinc-500">
            <span
              className={`h-2 w-2 rounded-full ${
                connected ? "bg-emerald-400" : "bg-zinc-600"
              }`}
            />
            {connected ? "bağlı" : "bağlanıyor…"}
          </span>
        </div>
      </div>
      <div
        ref={scrollRef}
        className={`min-h-0 flex-1 overflow-y-auto p-3 font-mono leading-relaxed ${
          large ? "space-y-1 text-base" : "space-y-0.5 text-sm"
        }`}
      >
        {lines.length === 0 && (
          <p className="text-zinc-600">Log bekleniyor… (bir PDF yükleyince akmaya başlar)</p>
        )}
        {lines.map((l, i) => (
          <div key={i} className="flex gap-2">
            <span className="shrink-0 text-zinc-600">
              {new Date(l.ts * 1000).toLocaleTimeString()}
            </span>
            <span className={`shrink-0 ${levelColor[l.level] ?? "text-zinc-400"}`}>
              {l.level}
            </span>
            <span className="shrink-0 text-zinc-500">[{l.stage}]</span>
            <span className="break-all text-zinc-300">{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
