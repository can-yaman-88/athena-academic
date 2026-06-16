import { useCallback, useEffect, useState } from "react";
import { analyzeNotes, createTask, getTasks, type Task } from "../api";
import { Button } from "../ui";
import TaskCard from "./TaskCard";

const inputCls =
  "rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500";

function defaultDeadline(): string {
  const d = new Date();
  d.setHours(23, 59, 0, 0);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
}

export default function TaskManager() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeMsg, setAnalyzeMsg] = useState("");
  const [form, setForm] = useState({
    title: "",
    deadline: defaultDeadline(),
    discipline: "General",
    estimated_hours: 1,
    category: "daily" as "daily" | "academic",
    subtype: "project" as "project" | "assignment" | "study_session",
  });

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

  async function add() {
    if (!form.title.trim()) return;
    await createTask({
      title: form.title.trim(),
      deadline: form.deadline,
      discipline: form.discipline || "General",
      estimated_hours: Number(form.estimated_hours) || 1,
      category: form.category,
      subtype: form.category === "academic" ? form.subtype : null,
    });
    setForm({ ...form, title: "" });
    await refresh();
  }

  async function analyze() {
    setAnalyzing(true);
    setAnalyzeMsg("");
    try {
      const r = await analyzeNotes();
      setAnalyzeMsg(
        r.message ??
          `+${r.added_load ?? 0} bilişsel yük, ${r.task_progress_updates} ilerleme güncellendi.`
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
      {/* create form */}
      <div className="grid grid-cols-2 gap-2 rounded-lg border border-zinc-800 bg-zinc-950/50 p-3 sm:grid-cols-12">
        <input className={`${inputCls} col-span-2 sm:col-span-3`} placeholder="Başlık" value={form.title}
          onChange={(e) => setForm({ ...form, title: e.target.value })}
          onKeyDown={(e) => e.key === "Enter" && void add()} />
        <select className={`${inputCls} sm:col-span-2`} value={form.category}
          onChange={(e) => setForm({ ...form, category: e.target.value as "daily" | "academic" })}>
          <option value="daily">Günlük</option>
          <option value="academic">Akademik</option>
        </select>
        {form.category === "academic" && (
          <select className={`${inputCls} sm:col-span-2`} value={form.subtype}
            onChange={(e) => setForm({ ...form, subtype: e.target.value as typeof form.subtype })}>
            <option value="project">proje</option>
            <option value="assignment">ödev</option>
            <option value="study_session">seans</option>
          </select>
        )}
        <input type="datetime-local" className={`${inputCls} sm:col-span-2`} value={form.deadline}
          onChange={(e) => setForm({ ...form, deadline: e.target.value })} />
        <input className={`${inputCls} sm:col-span-1`} placeholder="Alan" value={form.discipline}
          onChange={(e) => setForm({ ...form, discipline: e.target.value })} />
        <input type="number" min={0.5} step={0.5} className={`${inputCls} sm:col-span-1`} value={form.estimated_hours}
          onChange={(e) => setForm({ ...form, estimated_hours: Number(e.target.value) })} />
        <Button className="sm:col-span-1" onClick={() => void add()}>Ekle</Button>
      </div>

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
