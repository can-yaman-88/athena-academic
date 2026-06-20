import { useEffect, useState, useCallback, useRef } from "react";
import { getDashboard, getDailyNotes, upsertDailyNote, type DashboardData, type DailyNote } from "../api";
import { Badge, Card } from "../ui";
import ChatTerminal from "../components/ChatTerminal";
import TaskCard from "../components/TaskCard";
import NotionEditor from "../components/NotionEditor";
import { NotebookPen, ListTodo, CheckCircle2 } from "lucide-react";

const getTodayDateStr = () => {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().split("T")[0];
};

export default function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [timeFilter, setTimeFilter] = useState<"Tümü" | "Bugün" | "Bu hafta" | "Bu ay">("Tümü");
  const [statusFilter, setStatusFilter] = useState<"Tümü" | "Tamamlandı" | "Bekliyor">("Tümü");

  const todayStr = getTodayDateStr();
  const todayKey = `jarvis_daily_note_${todayStr}`;

  // Daily note states
  const [dailyNote, setDailyNote] = useState<DailyNote | null>(null);
  const [noteContent, setNoteContent] = useState(() => {
    return localStorage.getItem(todayKey) || "";
  });
  const [savingNote, setSavingNote] = useState(false);
  const saveTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        setData(await getDashboard());
        setError("");
      } catch (e) {
        setError((e as Error).message);
      }
    };
    const loadNote = async () => {
      try {
        const notes = await getDailyNotes();
        const todayNote = notes.find(n => n.date === todayStr);
        if (todayNote) {
          setDailyNote(todayNote);
          const local = localStorage.getItem(todayKey) || "";
          if (!local || todayNote.content.length >= local.length) {
            setNoteContent(todayNote.content);
            localStorage.setItem(todayKey, todayNote.content);
          }
        }
      } catch (e) {
        // ignore
      }
    };
    void refresh();
    void loadNote();
    const id = setInterval(() => void refresh(), 15000);
    return () => clearInterval(id);
  }, []);

  const handleNoteChange = useCallback((html: string) => {
    setNoteContent(html);
    localStorage.setItem(todayKey, html);
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = window.setTimeout(async () => {
      setSavingNote(true);
      try {
        await upsertDailyNote(todayStr, html);
      } catch (e) {
        console.error("Failed to save daily note", e);
      } finally {
        setSavingNote(false);
      }
    }, 1000);
  }, []);

  const tasks = (data?.tasks ?? [])
    .slice()
    .sort((a, b) => (a.deadline ?? "9999").localeCompare(b.deadline ?? "9999"));
    
  // Does a single task pass the active time + status filters?
  const matches = (t: typeof tasks[number]) => {
    // Tamamlanma filter
    if (statusFilter === "Tamamlandı" && t.status !== "completed") return false;
    if (statusFilter === "Bekliyor" && t.status !== "pending") return false;

    // Zaman filter
    if (timeFilter !== "Tümü") {
      if (!t.deadline) return false; // no deadline → not part of any time window
      const deadline = new Date(t.deadline);
      const now = new Date();
      let limit = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
      if (timeFilter === "Bugün") {
        // limit is today's end
      } else if (timeFilter === "Bu hafta") {
        const daysUntilSunday = (7 - now.getDay()) % 7;
        limit.setDate(limit.getDate() + daysUntilSunday);
      } else if (timeFilter === "Bu ay") {
        limit = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);
      }
      if (deadline > limit) return false;
    }

    return true;
  };

  // A top-level task is visible when it matches OR any of its subtasks matches —
  // so filtering by "Bugün" still surfaces a parent whose subtask is due today.
  // When the parent itself matches, show all its subtasks (full task view);
  // otherwise show only the subtasks that matched the filter.
  const visibleTasks = tasks
    .filter((t) => t.parent_id === null)
    .map((parent) => {
      const subs = tasks.filter((s) => s.parent_id === parent.id);
      const parentMatches = matches(parent);
      const matchingSubs = subs.filter(matches);
      if (parentMatches) return { parent, subs };
      if (matchingSubs.length > 0) return { parent, subs: matchingSubs };
      return null;
    })
    .filter((x): x is { parent: typeof tasks[number]; subs: typeof tasks } => x !== null);

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Left: "Günüm" — today's tasks, deadlines, capacity */}
      <Card
        title="Günüm"
        right={
          <Badge tone={data?.pending_count ? "amber" : "emerald"}>
            {data?.pending_count ?? 0} bekleyen
          </Badge>
        }
        bodyClassName="flex flex-col gap-3 overflow-y-auto p-4"
      >
        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
            API offline: {error}
          </div>
        )}

        {/* Daily Note Editor */}
        <div className="relative flex flex-col rounded-xl border border-line bg-surface overflow-hidden shrink-0 min-h-[250px]">
          <div className="flex items-center justify-between border-b border-line bg-surface-2/50 px-3 py-2">
            <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-primary-300">
              <NotebookPen size={13} strokeWidth={2.25} /> Günüm Notu
            </span>
            <span className="flex items-center gap-1 text-[10px] text-zinc-500">
              {savingNote ? (
                <>Kaydediliyor…</>
              ) : (
                <><CheckCircle2 size={11} className="text-accent-400" /> Kaydedildi</>
              )}
            </span>
          </div>
          <div className="flex-1 overflow-y-auto">
            <NotionEditor initialContent={noteContent} onChange={handleNoteChange} />
          </div>
        </div>

        <div className="mt-2 flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-zinc-500">
          <ListTodo size={13} strokeWidth={2.25} /> Görevler &amp; son tarihler
        </div>
        
        {/* Filters */}
        <div className="flex flex-col gap-2 rounded-xl border border-line bg-elevated/60 p-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-16 text-zinc-500">Zaman:</span>
            {["Bugün", "Bu hafta", "Bu ay", "Tümü"].map(f => (
              <button
                key={f}
                onClick={() => setTimeFilter(f as any)}
                aria-pressed={timeFilter === f}
                className={`rounded-md px-2.5 py-1 font-medium transition-colors ${timeFilter === f ? "bg-primary-500/20 text-primary-200 ring-1 ring-inset ring-primary-500/30" : "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"}`}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-16 text-zinc-500">Durum:</span>
            {["Tamamlandı", "Bekliyor", "Tümü"].map(f => (
              <button
                key={f}
                onClick={() => setStatusFilter(f as any)}
                aria-pressed={statusFilter === f}
                className={`rounded-md px-2.5 py-1 font-medium transition-colors ${statusFilter === f ? "bg-primary-500/20 text-primary-200 ring-1 ring-inset ring-primary-500/30" : "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"}`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {visibleTasks.length === 0 && (
          <p className="text-sm text-zinc-500">Henüz görev yok. Sohbetten ekleyebilirsin.</p>
        )}
        <ul className="flex flex-col gap-2">
          {visibleTasks.map(({ parent: t, subs }) => (
            <li key={t.id}>
              <TaskCard
                task={t}
                subtasks={subs}
                onChanged={() => {
                  import("../api").then(({ getDashboard }) => {
                    getDashboard().then((d) => setData(d)).catch((e) => setError(e.message));
                  });
                }}
              />
            </li>
          ))}
        </ul>
      </Card>

      {/* Right: chat */}
      <div className="h-full min-h-0">
        <ChatTerminal />
      </div>
    </div>
  );
}
