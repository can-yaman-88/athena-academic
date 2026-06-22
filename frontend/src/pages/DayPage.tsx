import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getTasks,
  getNotes,
  getIdeas,
  type Task,
  type NotePage,
  type Idea,
} from "../api";
import { useChat } from "../ChatContext";
import { Card } from "../ui";
import { CheckSquare, FileText, Lightbulb, MessageSquare, PencilLine } from "lucide-react";

const todayStr = () => {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().split("T")[0];
};

const plainPreview = (html: string): string => {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  return (tmp.textContent || tmp.innerText || "").trim();
};

export default function DayPage() {
  const [date, setDate] = useState(todayStr);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [notes, setNotes] = useState<NotePage[]>([]);
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { sessions } = useChat();

  useEffect(() => {
    (async () => {
      try {
        const [t, n, i] = await Promise.all([getTasks(), getNotes(), getIdeas()]);
        setTasks(t);
        setNotes(n);
        setIdeas(i);
        setError("");
      } catch (e) {
        setError(`Veriler yüklenemedi: ${(e as Error).message}`);
      }
    })();
  }, []);

  const onDay = (iso?: string | null) => !!iso && iso.slice(0, 10) === date;

  const dayTasks = tasks.filter(
    (t) => t.category === "academic" && t.parent_id === null && onDay(t.deadline)
  );
  const dayNotes = notes.filter((n) => onDay(n.created_at));
  // Notes touched on this day but created on a different one — i.e. edits, not
  // new notes (so a note created+edited the same day only shows under "Notlar").
  const editedNotes = notes.filter((n) => onDay(n.updated_at) && !onDay(n.created_at));
  const dayIdeas = ideas.filter((i) => onDay(i.created_at));

  // Find the first chat message on this day → deep-link target.
  const chatJump = useMemo(() => {
    const start = new Date(date + "T00:00:00").getTime();
    const end = start + 24 * 60 * 60 * 1000;
    let best: { session: string; ts: number } | null = null;
    for (const s of sessions) {
      for (const l of s.lines) {
        if (l.ts && l.ts >= start && l.ts < end) {
          if (!best || l.ts < best.ts) best = { session: s.id, ts: l.ts };
        }
      }
    }
    return best;
  }, [sessions, date]);

  const Section = ({
    icon,
    title,
    count,
    children,
  }: {
    icon: React.ReactNode;
    title: string;
    count: number;
    children: React.ReactNode;
  }) => (
    <Card
      title={
        <span className="flex items-center gap-2">
          {icon} {title} <span className="text-xs text-zinc-500">({count})</span>
        </span>
      }
      bodyClassName="flex flex-col gap-1 p-3"
    >
      {children}
    </Card>
  );

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto">
      <div className="flex items-center gap-3">
        <h2 className="text-lg font-semibold text-zinc-100">Günüm</h2>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="field px-3 py-1.5 text-sm"
        />
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
          {error}
        </div>
      )}

      <Section icon={<CheckSquare size={15} className="text-primary-300" />} title="Akademik Görevler" count={dayTasks.length}>
        {dayTasks.length === 0 && <p className="p-2 text-sm text-zinc-500">Bu güne ait görev yok.</p>}
        {dayTasks.map((t) => (
          <button
            key={t.id}
            onClick={() => navigate("/akademik")}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-200 hover:bg-white/[0.04]"
          >
            <span className={t.status === "completed" ? "text-accent-400" : "text-zinc-500"}>
              {t.status === "completed" ? "✓" : "○"}
            </span>
            <span className="flex-1 truncate">{t.title}</span>
            <span className="text-xs text-zinc-500">{t.discipline}</span>
          </button>
        ))}
      </Section>

      <Section icon={<FileText size={15} className="text-primary-300" />} title="Notlar" count={dayNotes.length}>
        {dayNotes.length === 0 && <p className="p-2 text-sm text-zinc-500">Bu güne ait not yok.</p>}
        {dayNotes.map((n) => (
          <button
            key={n.id}
            onClick={() => navigate(`/notlar/${n.id}`)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-200 hover:bg-white/[0.04]"
          >
            <FileText size={14} className="text-zinc-500" />
            <span className="flex-1 truncate">{n.title || "Başlıksız"}</span>
          </button>
        ))}
      </Section>

      <Section icon={<PencilLine size={15} className="text-primary-300" />} title="Düzenlenen Notlar" count={editedNotes.length}>
        {editedNotes.length === 0 && <p className="p-2 text-sm text-zinc-500">Bu gün düzenlenen not yok.</p>}
        {editedNotes.map((n) => (
          <button
            key={n.id}
            onClick={() => navigate(`/notlar/${n.id}`)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-200 hover:bg-white/[0.04]"
          >
            <PencilLine size={14} className="text-zinc-500" />
            <span className="flex-1 truncate">{n.title || "Başlıksız"}</span>
            <span className="text-xs text-zinc-500">{n.created_at.slice(0, 10)}'de oluşturuldu</span>
          </button>
        ))}
      </Section>

      <Section icon={<Lightbulb size={15} className="text-primary-300" />} title="Fikirler" count={dayIdeas.length}>
        {dayIdeas.length === 0 && <p className="p-2 text-sm text-zinc-500">Bu güne ait fikir yok.</p>}
        {dayIdeas.map((i) => (
          <button
            key={i.id}
            onClick={() => navigate("/ideas")}
            className="flex flex-col rounded-lg px-2 py-1.5 text-left hover:bg-white/[0.04]"
          >
            <span className="truncate text-sm text-zinc-200">{i.title || "Başlıksız fikir"}</span>
            <span className="truncate text-xs text-zinc-500">{plainPreview(i.content)}</span>
          </button>
        ))}
      </Section>

      <Card title={<span className="flex items-center gap-2"><MessageSquare size={15} className="text-primary-300" /> Yapay Zeka Konuşması</span>} bodyClassName="p-3">
        {chatJump ? (
          <button
            onClick={() => navigate("/", { state: { jumpSession: chatJump.session, jumpTs: chatJump.ts } })}
            className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-primary-300 hover:border-primary-500"
          >
            <MessageSquare size={14} /> Bu günkü konuşmaya git →
          </button>
        ) : (
          <p className="text-sm text-zinc-500">Bu güne ait kayıtlı konuşma yok.</p>
        )}
      </Card>
    </div>
  );
}
