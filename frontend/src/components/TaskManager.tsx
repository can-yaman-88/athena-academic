import { useCallback, useEffect, useState } from "react";
import { analyzeNotes, createTask, getTasks, type Task } from "../api";
import { Button } from "../ui";
import TaskCard from "./TaskCard";


export default function TaskManager() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState("");

  const refresh = useCallback(async () => {
    try {
      setTasks(await getTasks());
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);


  async function analyze() {
    setAnalyzing(true);
    setAnalyzeMsg("");
    try {
      const r = await analyzeNotes();
      setAnalyzeMsg(
        r.message ?? `${r.task_progress_updates} ilerleme güncellendi.`
      );
      await refresh();
    } catch (e) {
      setAnalyzeMsg(`hata: ${(e as Error).message}`);
    } finally {
      setAnalyzing(false);
    }
  }

  const parents = tasks.filter((t) => t.parent_id === null);
  const subtasksOf = (id: string) => tasks.filter((t) => t.parent_id === id);
  const academic = parents.filter((t) => t.category === "academic");
  const daily = parents.filter((t) => t.category === "daily");

  return (
    <div className="flex h-full flex-col gap-3">

      {/* analyze notes */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" disabled={analyzing} onClick={() => void analyze()}>
          {analyzing ? "Analiz ediliyor…" : "Notları analiz et"}
        </Button>
        {analyzeMsg && <span className="text-xs text-zinc-400">{analyzeMsg}</span>}
      </div>

      {/* two sections */}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto lg:grid-cols-2">
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Akademik</h3>
          {academic.length === 0 && <p className="text-sm text-zinc-500">Akademik görev yok.</p>}
          {academic.map((t) => (
            <TaskCard key={t.id} task={t} subtasks={subtasksOf(t.id)} onChanged={() => void refresh()} />
          ))}
        </section>
        <section className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-sky-400">Günlük</h3>
          {daily.length === 0 && <p className="text-sm text-zinc-500">Günlük görev yok.</p>}
          {daily.map((t) => (
            <TaskCard key={t.id} task={t} subtasks={subtasksOf(t.id)} onChanged={() => void refresh()} />
          ))}
        </section>
      </div>
    </div>
  );
}
