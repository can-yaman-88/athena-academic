import { useEffect, useState } from "react";
import { getDashboard, type DashboardData } from "../api";
import { Badge, Card, Button } from "../ui";
import ChatTerminal from "../components/ChatTerminal";
import TaskCard from "../components/TaskCard";

export default function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [timeFilter, setTimeFilter] = useState<"Tümü" | "Bugün" | "Bu hafta" | "Bu ay">("Tümü");
  const [statusFilter, setStatusFilter] = useState<"Tümü" | "Tamamlandı" | "Bekliyor">("Tümü");

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
        <div className="flex flex-col gap-2 rounded-lg bg-zinc-900/50 p-2 text-xs">
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
    </div>
  );
}
