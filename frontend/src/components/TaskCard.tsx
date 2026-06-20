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
import NotionEditor from "./NotionEditor";

const subtypeTone: Record<string, "sky" | "amber" | "emerald"> = {
  project: "sky",
  assignment: "amber",
  study_session: "emerald",
};

// The note editor emits HTML; treat content as empty when it has no visible text
// (e.g. "<p></p>") so we don't save blank notes.
function htmlHasText(html: string): boolean {
  return html.replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").trim().length > 0;
}

function toDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const off = d.getTimezoneOffset();
    return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16);
  } catch {
    return iso;
  }
}

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
  const [addingNote, setAddingNote] = useState(false);
  const [editingNote, setEditingNote] = useState<string | null>(null);
  const [editingNoteText, setEditingNoteText] = useState("");
  const [matName, setMatName] = useState("");
  const [matUrl, setMatUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [newSubtaskTitle, setNewSubtaskTitle] = useState("");
  const [showLinkInput, setShowLinkInput] = useState(false);
  const [editingTask, setEditingTask] = useState(false);
  const [editForm, setEditForm] = useState({
    title: task.title,
    deadline: toDatetimeLocal(task.deadline),
    discipline: task.discipline,
    estimated_hours: task.estimated_hours,
    category: task.category,
    subtype: task.subtype || "project" as "project" | "assignment" | "study_session",
    progress: task.progress,
  });
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
    <div className={`rounded-lg border transition-colors hover:border-line-strong ${isSubtask ? "border-line/50 bg-surface-2/40 p-2 mt-2" : "border-line bg-surface-2/50 p-3"}`}>
      {/* header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {!editingTask ? (
            <>
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
                {task.discipline}
                {task.estimated_hours != null && ` · ${task.estimated_hours}h`}
                {" · "}
                {fmtDeadline(task.deadline)}
              </div>
            </>
          ) : (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <input
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500 col-span-2"
                value={editForm.title}
                onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
              />
              <input
                type="datetime-local"
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                value={editForm.deadline}
                onChange={(e) => setEditForm({ ...editForm, deadline: e.target.value })}
              />
              <input
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                value={editForm.discipline}
                onChange={(e) => setEditForm({ ...editForm, discipline: e.target.value })}
              />
              <input
                type="number"
                min={0.5}
                step={0.5}
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                value={editForm.estimated_hours ?? ""}
                onChange={(e) => setEditForm({ ...editForm, estimated_hours: e.target.value === "" ? null : Number(e.target.value) })}
              />
              <select
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                value={editForm.category}
                onChange={(e) => setEditForm({ ...editForm, category: e.target.value as "academic" | "daily" })}
              >
                <option value="daily">Günlük</option>
                <option value="academic">Akademik</option>
              </select>
              {editForm.category === "academic" && (
                <select
                  className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                  value={editForm.subtype}
                  onChange={(e) => setEditForm({ ...editForm, subtype: e.target.value as "project" | "assignment" | "study_session" })}
                >
                  <option value="project">proje</option>
                  <option value="assignment">ödev</option>
                  <option value="study_session">seans</option>
                </select>
              )}
              <input
                type="number"
                min={0}
                max={100}
                className="rounded border border-line-strong bg-surface-2 px-2 py-1 text-zinc-100 outline-none focus:border-primary-500"
                value={editForm.progress}
                onChange={(e) => setEditForm({ ...editForm, progress: Number(e.target.value) })}
              />
              <div className="col-span-2 flex gap-2">
                <Button
                  size="sm"
                  onClick={() =>
                    run(async () => {
                      await updateTask(task.id, {
                        title: editForm.title,
                        // An empty datetime-local field means "no deadline" → null.
                        deadline: editForm.deadline ? editForm.deadline : null,
                        discipline: editForm.discipline,
                        estimated_hours: editForm.estimated_hours,
                        category: editForm.category,
                        subtype: editForm.category === "academic" ? editForm.subtype as "project" | "assignment" | "study_session" : null,
                        progress: editForm.progress,
                      });
                      setEditingTask(false);
                    })
                  }
                >
                  Kaydet
                </Button>
                <Button size="sm" variant="subtle" onClick={() => setEditingTask(false)}>
                  İptal
                </Button>
              </div>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-1.5">
          {task.status !== "completed" ? (
            <Button variant="ghost" disabled={busy} title="Tamamlandı işaretle" onClick={() => run(() => completeTask(task.id))}>✓</Button>
          ) : (
            <Button variant="ghost" disabled={busy} title="Tamamlamayı geri al" onClick={() => run(() => updateTask(task.id, { status: "pending" }))}>↩</Button>
          )}
          <Button variant="ghost" disabled={busy} onClick={() => setEditingTask((e) => !e)} title="Düzenle">✏️</Button>
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
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
            <div className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-400 transition-[width] duration-500" style={{ width: `${task.progress}%` }} />
          </div>
        </div>
      )}

      {open && (
        <div className="mt-3 space-y-3 border-t border-line pt-3">
          {/* notes */}
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wider text-zinc-500">Notlar</div>
            <ul className="space-y-2">
              {task.notes.map((n) => (
                <li key={n.id} className="rounded-lg border border-line bg-surface-2/50 p-2 text-sm">
                  {editingNote === n.id ? (
                    <div>
                      <div className="overflow-hidden rounded-lg border border-line-strong">
                        <NotionEditor key={`edit-${n.id}`} initialContent={editingNoteText} onChange={setEditingNoteText} />
                      </div>
                      <div className="mt-1 flex gap-2">
                        <Button size="sm" disabled={!htmlHasText(editingNoteText)} onClick={() => run(async () => { await editNote(task.id, n.id, editingNoteText); setEditingNote(null); })}>Kaydet</Button>
                        <Button size="sm" variant="subtle" onClick={() => setEditingNote(null)}>İptal</Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start justify-between gap-2">
                      <div
                        className="prose prose-invert prose-sm min-w-0 flex-1 break-words"
                        dangerouslySetInnerHTML={{ __html: n.text }}
                      />
                      <div className="flex shrink-0 gap-2">
                        <button className="text-xs text-zinc-500 hover:text-zinc-200" onClick={() => { setEditingNote(n.id); setEditingNoteText(n.text); }}>düzenle</button>
                        <button className="text-xs text-rose-400/70 hover:text-rose-300" onClick={() => run(() => deleteNote(task.id, n.id))}>sil</button>
                      </div>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            {addingNote ? (
              <div className="mt-2">
                <div className="overflow-hidden rounded-lg border border-line-strong">
                  <NotionEditor key="add-note" initialContent="" onChange={setNoteText} />
                </div>
                <div className="mt-1 flex gap-2">
                  <Button size="sm" disabled={!htmlHasText(noteText)} onClick={() => run(async () => { await addNote(task.id, noteText); setNoteText(""); setAddingNote(false); })}>Kaydet</Button>
                  <Button size="sm" variant="subtle" onClick={() => { setNoteText(""); setAddingNote(false); }}>İptal</Button>
                </div>
              </div>
            ) : (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setAddingNote(true)}>Not Ekle</Button>
            )}
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
                    <a href={m.source} target="_blank" rel="noreferrer" className="text-primary-300 hover:underline">🔗 {m.name}</a>
                  ) : (
                    <a href={taskFileUrl(task.id, m.id)} target="_blank" rel="noreferrer" className="text-zinc-200 hover:text-primary-300">📄 {m.name}</a>
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
                  <input value={matName} onChange={(e) => setMatName(e.target.value)} placeholder="ad" className="w-24 rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-primary-500" />
                  <input value={matUrl} onChange={(e) => setMatUrl(e.target.value)} placeholder="https://…" className="flex-1 rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-primary-500" />
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
                  className="flex-1 rounded border border-line-strong bg-surface-2 px-2 py-1 text-xs text-zinc-100 outline-none focus:border-primary-500"
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
