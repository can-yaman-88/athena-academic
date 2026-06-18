import { useEffect, useState } from "react";
import { getDashboard, type DashboardData } from "../api";
import { Badge, Card, Button } from "../ui";
import ChatTerminal from "../components/ChatTerminal";
import TaskCard from "../components/TaskCard";
import NotionEditor from "../components/NotionEditor";
import { upsertJournal, getJournals, type Journal } from "../api";

export default function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [timeFilter, setTimeFilter] = useState<"Tümü" | "Bugün" | "Bu hafta" | "Bu ay">("Tümü");
  const [statusFilter, setStatusFilter] = useState<"Tümü" | "Tamamlandı" | "Bekliyor">("Tümü");

  // Journal Modal
  const [showJournalModal, setShowJournalModal] = useState(false);
  const [todayJournal, setTodayJournal] = useState<Journal | null>(null);

  useEffect(() => {
    // Load today's journal on mount
    const loadJournal = async () => {
      try {
        const journals = await getJournals();
        const todayStr = new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD
        const todayJ = journals.find(j => j.date === todayStr);
        if (todayJ) setTodayJournal(todayJ);
      } catch (e) {
        console.error("Journal loading error:", e);
      }
    };
    void loadJournal();
  }, []);

  const handleSaveJournal = async (content: string) => {
    const todayStr = new Date().toLocaleDateString("sv-SE");
    try {
      const saved = await upsertJournal(todayStr, content);
      setTodayJournal(saved);
    } catch (e) {
      console.error("Failed to save journal:", e);
    }
  };

  useEffect(() => {
    const refresh = async () => {
      try {
        setData(await getDashboard());
        setError("");
      } catch (e) {
        setError((e as Error).message);
      }
    };
    void refresh();
    const id = setInterval(() => void refresh(), 15000);
    return () => clearInterval(id);
  }, []);

  const tasks = (data?.tasks ?? [])
    .slice()
    .sort((a, b) => a.deadline.localeCompare(b.deadline));
    
  const filteredTasks = tasks.filter(t => {
    // Tamamlanma filter
    if (statusFilter === "Tamamlandı" && t.status !== "completed") return false;
    if (statusFilter === "Bekliyor" && t.status !== "pending") return false;
    
    // Zaman filter
    if (timeFilter !== "Tümü") {
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
  });

  const load = data?.cognitive_load;

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-2">
      {/* Left: "Günüm" — today's tasks, deadlines, capacity */}
      <Card
        title="Günüm"
        right={
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => setShowJournalModal(true)}>
              Günlük/Fikir Ekle
            </Button>
            <Badge tone={data?.pending_count ? "amber" : "emerald"}>
              {data?.pending_count ?? 0} bekleyen
            </Badge>
          </div>
        }
        bodyClassName="flex flex-col gap-3 overflow-y-auto p-4"
      >
        {error && (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
            API offline: {error}
          </div>
        )}

        {load && (
          <div
            className={`rounded-lg border p-3 text-sm ${
              load.heavy_cognitive_blocked
                ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
            }`}
          >
            <div className="mb-1 text-[11px] uppercase tracking-wider opacity-70">
              Bilişsel kapasite · yük {load.calculated_load}
            </div>
            {load.directive}
          </div>
        )}

        <div className="text-[11px] uppercase tracking-wider text-zinc-500">
          Görevler & son tarihler
        </div>
        
        {/* Filters */}
        <div className="flex flex-col gap-2 rounded-lg bg-elevated/60 p-2 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 w-16">Zaman:</span>
            {["Bugün", "Bu hafta", "Bu ay", "Tümü"].map(f => (
              <button 
                key={f} 
                onClick={() => setTimeFilter(f as any)} 
                className={`rounded px-2 py-1 ${timeFilter === f ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:bg-zinc-800"}`}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 w-16">Durum:</span>
            {["Tamamlandı", "Bekliyor", "Tümü"].map(f => (
              <button 
                key={f} 
                onClick={() => setStatusFilter(f as any)} 
                className={`rounded px-2 py-1 ${statusFilter === f ? "bg-emerald-500/20 text-emerald-300" : "text-zinc-400 hover:bg-zinc-800"}`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {filteredTasks.length === 0 && (
          <p className="text-sm text-zinc-500">Henüz görev yok. Sohbetten ekleyebilirsin.</p>
        )}
        <ul className="flex flex-col gap-2">
          {filteredTasks.filter((t) => t.parent_id === null).map((t) => (
            <li key={t.id}>
              <TaskCard
                task={t}
                subtasks={tasks.filter((s) => s.parent_id === t.id)}
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

      {/* Journal Modal */}
      {showJournalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
          <div className="flex h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-line bg-surface-2 shadow-2xl">
            <div className="flex items-center justify-between border-b border-line p-4">
              <h2 className="text-lg font-semibold text-zinc-100">
                Günün Fikirleri ({new Date().toLocaleDateString("tr-TR")})
              </h2>
              <button 
                className="text-zinc-400 hover:text-white"
                onClick={() => setShowJournalModal(false)}
              >
                Kapat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <NotionEditor 
                initialContent={todayJournal?.content || ""}
                onChange={(html) => handleSaveJournal(html)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
