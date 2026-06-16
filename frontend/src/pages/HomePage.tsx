import { useEffect, useState } from "react";
import { getDashboard, type DashboardData } from "../api";
import { Badge, Card, fmtDeadline } from "../ui";
import ChatTerminal from "../components/ChatTerminal";

export default function HomePage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

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
        {tasks.length === 0 && (
          <p className="text-sm text-zinc-500">Henüz görev yok. Sohbetten ekleyebilirsin.</p>
        )}
        <ul className="flex flex-col gap-2">
          {tasks.map((t) => (
            <li
              key={t.id}
              className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950/50 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="truncate text-sm text-zinc-100">{t.title}</div>
                <div className="mt-0.5 text-xs text-zinc-500">
                  {t.discipline} · {t.estimated_hours}h · {fmtDeadline(t.deadline)}
                </div>
              </div>
              <Badge tone={t.status === "completed" ? "emerald" : "amber"}>
                {t.status === "completed" ? "tamam" : "bekliyor"}
              </Badge>
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
