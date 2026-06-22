import { useCallback, useEffect, useState } from "react";
import { analyzeNotes, createTask, getTasks, type Task } from "../api";
import { Button } from "../ui";
import TaskCard from "./TaskCard";


export default function TaskManager({
  category,
}: {
  category?: "academic" | "daily";
}) {
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

  const analyzeBar = (
    <div className="flex items-center gap-3">
      <Button variant="ghost" disabled={analyzing} onClick={() => void analyze()}>
        {analyzing ? "Analiz ediliyor…" : "Notları analiz et"}
      </Button>
      {analyzeMsg && <span className="text-xs text-zinc-400">{analyzeMsg}</span>}
    </div>
  );

  const renderSection = (
    label: string,
    items: Task[],
    emptyText: string
  ) => (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-primary-400">{label}</h3>
      {items.length === 0 && <p className="text-sm text-zinc-500">{emptyText}</p>}
      {items.map((t) => (
        <TaskCard key={t.id} task={t} subtasks={subtasksOf(t.id)} onChanged={() => void refresh()} />
      ))}
    </section>
  );

  // Single-category view (used by the dedicated Akademik / Günlük pages).
  if (category === "academic" || category === "daily") {
    const items = category === "academic" ? academic : daily;
    const empty = category === "academic" ? "Akademik görev yok." : "Günlük görev yok.";
    return (
      <div className="flex h-full flex-col gap-3">
        {analyzeBar}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {renderSection(category === "academic" ? "Akademik" : "Günlük", items, empty)}
        </div>
      </div>
    );
  }

  // Combined view (kept for completeness / reuse).
  return (
    <div className="flex h-full flex-col gap-3">
      {analyzeBar}
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto lg:grid-cols-2">
        {renderSection("Akademik", academic, "Akademik görev yok.")}
        {renderSection("Günlük", daily, "Günlük görev yok.")}
      </div>
    </div>
  );
}
