import { useRef, useState } from "react";
import {
  addMaterial,
  addNote,
  completeTask,
  deleteNote,
  deleteTask,
  editNote,
  generateSubtasks,
  taskFileUrl,
  updateTask,
  uploadTaskFile,
  type Task,
} from "../api";
import { Badge, Button, fmtDeadline } from "../ui";

const subtypeTone: Record<string, "sky" | "amber" | "emerald"> = {
  project: "sky",
  assignment: "amber",
  study_session: "emerald",
};

export default function TaskCard({
  task,
  subtasks,
  onChanged,
  isSubtask = false,
}: {
  task: Task;
  subtasks: Task[];
  onChanged: () => void;
  isSubtask?: boolean;
}) {
  const [noteText, setNoteText] = useState("");
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const [editingNoteText, setEditingNoteText] = useState("");
  const [matName, setMatName] = useState("");
  const [matUrl, setMatUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [newSubtaskTitle, setNewSubtaskTitle] = useState("");
  const [showLinkInput, setShowLinkInput] = useState(false);
  const academic = task.category === "academic";

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`rounded-lg border ${isSubtask ? "border-zinc-800/50 bg-zinc-900/30 p-2 mt-2" : "border-zinc-800 bg-zinc-950/50 p-3"}`}>
      {/* header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium text-zinc-100">{task.title}</span>
            {academic && task.subtype && (
              <Badge tone={subtypeTone[task.subtype] ?? "zinc"}>{task.subtype}</Badge>
            )}
            {task.tags && task.tags.map(t => (
              <Badge key={t} tone="sky">#{t}</Badge>
            ))}
            <Badge tone={task.status === "completed" ? "emerald" : "amber"}>
              {task.status === "completed" ? "tamam" : "bekliyor"}
            </Badge>
          </div>
          <div className="mt-0.5 text-xs text-zinc-500">
            {task.discipline} · {task.estimated_hours}h · {fmtDeadline(task.deadline)}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          {task.status !== "completed" && (
            <Button variant="ghost" disabled={busy} onClick={() => run(() => completeTask(task.id))}>✓</Button>
          )}
          <Button variant="subtle" onClick={() => setOpen((o) => !o)}>{open ? "▲" : "▼"}</Button>
          <Button variant="danger" disabled={busy} onClick={() => run(() => deleteTask(task.id))}>Sil</Button>
        </div>
      </div>

      {/* progress (academic) */}
      {academic && (
        <div className="mt-2">
          <div className="mb-1 flex justify-between text-[11px] text-zinc-500">
            <span>İlerleme</span>
            <span>{task.progress}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${task.progress}%` }} />
          </div>
        </div>
      )}

      {open && (
        <div className="mt-3 space-y-3 border-t border-zinc-800 pt-3">
          {/* notes */}
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wider text-zinc-500">Notlar</div>
            <ul className="space-y-1">
              {task.notes.map((n) => (
                <li key={n.id} className="flex items-start justify-between gap-2 text-sm">
                  {editingNote === n.id ? (
                    <>
                      <input
                        value={editingNoteText}
                        onChange={(e) => setEditingNoteText(e.target.value)}
                        className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                      />
                      <Button variant="ghost" onClick={() => run(async () => { await editNote(task.id, n.id, editingNoteText); setEditingNote(null); })}>Kaydet</Button>
                    </>
                  ) : (
                    <>
                      <span className="flex-1 text-zinc-300">{n.text}</span>
                      <button className="text-xs text-zinc-500 hover:text-zinc-200" onClick={() => { setEditingNote(n.id); setEditingNoteText(n.text); }}>düzenle</button>
                      <button className="text-xs text-rose-400/70 hover:text-rose-300" onClick={() => run(() => deleteNote(task.id, n.id))}>sil</button>
                    </>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-1 flex gap-2">
              <input
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                placeholder="Not ekle…"
                className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                onKeyDown={(e) => e.key === "Enter" && noteText.trim() && run(async () => { await addNote(task.id, noteText.trim()); setNoteText(""); })}
              />
              <Button variant="ghost" disabled={!noteText.trim()} onClick={() => run(async () => { await addNote(task.id, noteText.trim()); setNoteText(""); })}>Not +</Button>
            </div>
          </div>

          {/* materials */}
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wider text-zinc-500">
              Materyaller <span className="text-zinc-600">(dosyalar yapay zekâya gönderilmez)</span>
            </div>
            <ul className="space-y-1 text-sm">
              {task.materials.map((m) => (
                <li key={m.id} className="text-zinc-300">
                  {m.kind === "link" ? (
                    <a href={m.source} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline">🔗 {m.name}</a>
                  ) : (
                    <a href={taskFileUrl(task.id, m.id)} target="_blank" rel="noreferrer" className="text-zinc-200 hover:text-emerald-300">📄 {m.name}</a>
                  )}
                </li>
              ))}
            </ul>
            <div className="mt-1 flex flex-wrap gap-2">
              <Button variant="ghost" onClick={() => fileRef.current?.click()}>Dosya +</Button>
              <input ref={fileRef} type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => uploadTaskFile(task.id, f)); if (e.target) e.target.value = ""; }} />
              
              <Button variant="ghost" onClick={() => setShowLinkInput(!showLinkInput)}>Bağlantı +</Button>
              
              {showLinkInput && (
                <>
                  <input value={matName} onChange={(e) => setMatName(e.target.value)} placeholder="ad" className="w-24 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500" />
                  <input value={matUrl} onChange={(e) => setMatUrl(e.target.value)} placeholder="https://…" className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500" />
                  <Button variant="ghost" disabled={!matName.trim() || !matUrl.trim()} onClick={() => run(async () => { await addMaterial(task.id, { kind: "link", name: matName.trim(), source: matUrl.trim() }); setMatName(""); setMatUrl(""); setShowLinkInput(false); })}>Ekle</Button>
                </>
              )}
            </div>
          </div>

          {/* subtasks */}
          {!isSubtask && (
            <div>
              <div className="mb-1 flex items-center justify-between mt-4">
                <span className="text-[11px] uppercase tracking-wider text-zinc-500">Alt görevler</span>
                {academic && (
                  <Button variant="ghost" disabled={busy} onClick={() => run(() => generateSubtasks(task.id))}>AI alt görev üret</Button>
                )}
              </div>
              <div className="flex flex-col gap-2 mb-3">
                {subtasks.map((s) => (
                  <TaskCard key={s.id} task={s} subtasks={[]} onChanged={onChanged} isSubtask={true} />
                ))}
                {subtasks.length === 0 && <div className="text-xs text-zinc-600">Alt görev yok.</div>}
              </div>
              <div className="flex gap-2">
                <input
                  value={newSubtaskTitle}
                  onChange={(e) => setNewSubtaskTitle(e.target.value)}
                  placeholder="Alt görev başlığı..."
                  className="flex-1 rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-emerald-500"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newSubtaskTitle.trim()) {
                      import("../api").then(({ createTask }) => {
                        run(async () => {
                          await createTask({
                            title: newSubtaskTitle.trim(),
                            deadline: task.deadline,
                            category: task.category,
                            discipline: task.discipline,
                            parent_id: task.id,
                          });
                          setNewSubtaskTitle("");
                        });
                      });
                    }
                  }}
                />
                <Button
                  variant="ghost"
                  disabled={!newSubtaskTitle.trim()}
                  onClick={() => {
                    import("../api").then(({ createTask }) => {
                      run(async () => {
                        await createTask({
                          title: newSubtaskTitle.trim(),
                          deadline: task.deadline,
                          category: task.category,
                          discipline: task.discipline,
                          parent_id: task.id,
                        });
                        setNewSubtaskTitle("");
                      });
                    });
                  }}
                >Ekle</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
