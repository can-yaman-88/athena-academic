import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeWorkout,
  deleteWorkout,
  getWorkouts,
  streamChat,
  updateWorkout,
  uploadWorkoutFile,
  type Workout,
} from "../api";
import { Badge, Button, Card } from "../ui";
import Modal from "../components/Modal";
import NotionEditor from "../components/NotionEditor";
import { useSync } from "../SyncContext";

const inputCls =
  "rounded-lg border border-line-strong bg-surface-2 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500";

function Metrics({ w }: { w: Workout }) {
  const items: [string, string][] = [];
  if (w.distance_km != null) items.push(["Mesafe", `${w.distance_km} km`]);
  if (w.pace) items.push(["Tempo", `${w.pace}/km`]);
  if (w.avg_speed_kmh != null) items.push(["Hız", `${w.avg_speed_kmh} km/s`]);
  if (w.avg_hr != null) items.push(["Nabız", `${w.avg_hr} bpm`]);
  if (items.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-400">
      {items.map(([k, v]) => (
        <span key={k}>
          <span className="text-zinc-500">{k}:</span> {v}
        </span>
      ))}
    </div>
  );
}

function WorkoutCard({
  w,
  onChanged,
  onOpen,
}: {
  w: Workout;
  onChanged: () => void;
  onOpen: () => void;
}) {
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };
  return (
    <div
      onClick={onOpen}
      className="cursor-pointer rounded-lg border border-line bg-surface-2/50 p-3 transition-colors hover:border-line-strong"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-100">
              {w.title || "Antrenman"}
            </span>
            {w.note && <Badge tone="sky">not</Badge>}
          </div>
          <div className="mt-0.5 text-xs text-zinc-500">
            {w.date} · {w.duration_minutes} dk
            {w.rpe_score != null && ` · RPE ${w.rpe_score}`}
          </div>
          <Metrics w={w} />
        </div>
        <div className="flex shrink-0 gap-1.5">
          {w.status === "planned" && (
            <Button
              variant="ghost"
              onClick={stop(async () => {
                await completeWorkout(w.id);
                onChanged();
              })}
            >
              Tamamla
            </Button>
          )}
          <Button
            variant="danger"
            onClick={stop(async () => {
              await deleteWorkout(w.id);
              onChanged();
            })}
          >
            Sil
          </Button>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2/60 px-3 py-2">
      <div className="text-[10px] font-medium uppercase tracking-[0.1em] text-zinc-500">
        {label}
      </div>
      <div className="mt-0.5 text-sm text-zinc-100">{value}</div>
    </div>
  );
}

function WorkoutDetailModal({
  w,
  onClose,
  onChanged,
}: {
  w: Workout;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [note, setNote] = useState(w.note || "");
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  async function saveNote() {
    setSaving(true);
    setSavedMsg("");
    try {
      await updateWorkout(w.id, { note });
      setSavedMsg("✓ Not kaydedildi");
      onChanged();
    } catch (e) {
      setSavedMsg(`✗ ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={true} onClose={onClose} title={w.title || "Antrenman"} widthClass="max-w-2xl">
      <div className="flex h-full flex-col gap-4 overflow-y-auto">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <DetailRow label="Tarih" value={w.date} />
          <DetailRow label="Süre" value={`${w.duration_minutes} dk`} />
          <DetailRow
            label="Durum"
            value={w.status === "completed" ? "Tamamlandı" : "Planlı"}
          />
          {w.rpe_score != null && <DetailRow label="RPE" value={w.rpe_score} />}
          {w.distance_km != null && (
            <DetailRow label="Mesafe" value={`${w.distance_km} km`} />
          )}
          {w.pace && <DetailRow label="Tempo" value={`${w.pace}/km`} />}
          {w.avg_speed_kmh != null && (
            <DetailRow label="Hız" value={`${w.avg_speed_kmh} km/s`} />
          )}
          {w.avg_hr != null && <DetailRow label="Nabız" value={`${w.avg_hr} bpm`} />}
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wider text-zinc-500">
              Not
            </span>
            <div className="flex items-center gap-2">
              {savedMsg && <span className="text-xs text-zinc-400">{savedMsg}</span>}
              <Button size="sm" disabled={saving} onClick={() => void saveNote()}>
                {saving ? "Kaydediliyor…" : "Notu Kaydet"}
              </Button>
            </div>
          </div>
          <div className="min-h-[220px] overflow-hidden rounded-lg border border-line-strong">
            {/* keyed by id so the editor remounts (and reloads content) per workout */}
            <NotionEditor key={w.id} initialContent={w.note || ""} onChange={setNote} />
          </div>
        </div>
      </div>
    </Modal>
  );
}

export default function WorkoutsPage() {
  const [workouts, setWorkouts] = useState<Workout[]>([]);
  const [uploadMsg, setUploadMsg] = useState("");
  const [planText, setPlanText] = useState(() => {
    return localStorage.getItem("jarvis_workout_plan") || "";
  });
  useEffect(() => {
    localStorage.setItem("jarvis_workout_plan", planText);
  }, [planText]);
  const [planMsg, setPlanMsg] = useState("");
  const [planBusy, setPlanBusy] = useState(false);
  const [selected, setSelected] = useState<Workout | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { syncBusy, syncMsg, runSync } = useSync();

  const refresh = useCallback(async () => {
    try {
      const list = await getWorkouts();
      list.sort((a, b) => b.date.localeCompare(a.date));
      setWorkouts(list);
      // keep an open detail modal in sync with refreshed data
      setSelected((cur) => (cur ? list.find((w) => w.id === cur.id) ?? null : null));
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function upload(file: File) {
    setUploadMsg(`${file.name} içe aktarılıyor…`);
    try {
      const r = await uploadWorkoutFile(file);
      setUploadMsg(`✓ ${r.imported} antrenman içe aktarıldı`);
      await refresh();
    } catch (e) {
      setUploadMsg(`✗ ${(e as Error).message}`);
    }
  }

  async function importPlan() {
    if (!planText.trim()) return;
    setPlanBusy(true);
    setPlanMsg("");
    try {
      await streamChat(`/wplan\n${planText.trim()}`, (evt) => {
        if (evt.type === "message") setPlanMsg(String(evt.content));
        else if (evt.type === "error") setPlanMsg(`hata: ${String(evt.error)}`);
      });
      setPlanText("");
      localStorage.removeItem("jarvis_workout_plan");
      await refresh();
    } catch (e) {
      setPlanMsg(`hata: ${(e as Error).message}`);
    } finally {
      setPlanBusy(false);
    }
  }

  const planned = workouts.filter((w) => w.status === "planned");
  const completed = workouts.filter((w) => w.status === "completed");

  return (
    <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[22rem_1fr]">
      {/* Left: add + upload + plan import */}
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto">
        <Card title="Runalyze Senkronizasyonu" bodyClassName="p-4">
          <p className="text-xs text-zinc-400 mb-3">
            Runalyze hesabınızdaki son aktiviteleri otomatik olarak Athena'ya çeker. (Sistem ayarlarına RUNALYZE_TOKEN eklenmiş olmalıdır.)
          </p>
          <div className="flex items-center gap-3">
            <Button disabled={syncBusy} onClick={() => void runSync(refresh)}>
              {syncBusy ? "Senkronize ediliyor..." : "Runalyze ile Senkronize Et"}
            </Button>
            {syncMsg && <span className="text-xs text-zinc-400">{syncMsg}</span>}
          </div>
        </Card>

        <Card title="Veri Dosyası İçe Aktar (JSON / CSV / .FIT)" bodyClassName="p-4">
          <input ref={fileRef} type="file" accept=".json,.csv,.fit" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
          <div
            onClick={() => fileRef.current?.click()}
            className="flex h-24 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-line-strong text-center hover:border-zinc-500"
          >
            <p className="text-sm text-zinc-300">Garmin/TrainingPeaks dosyası bırak/seç</p>
            <p className="mt-1 text-xs text-zinc-500">İçe aktarılanlar tamamlanmış sayılır</p>
          </div>
          {uploadMsg && <p className="mt-2 text-xs text-zinc-400">{uploadMsg}</p>}
        </Card>

        <Card title="Çoklu Gün Plan İçe Aktar" bodyClassName="p-4">
          <textarea value={planText} onChange={(e) => setPlanText(e.target.value)} rows={4}
            placeholder="Örn: Pzt 45dk tempo, Çar 60dk interval… (planlı eklenir)"
            className={`${inputCls} w-full`} />
          <div className="mt-2 flex items-center gap-3">
            <Button disabled={planBusy || !planText.trim()} onClick={() => void importPlan()}>
              {planBusy ? "İçe aktarılıyor…" : "Planı içe aktar"}
            </Button>
            {planMsg && <span className="text-xs text-zinc-400">{planMsg}</span>}
          </div>
        </Card>
      </div>

      {/* Right: planned + completed */}
      <div className="grid min-h-0 grid-rows-2 gap-4">
        <Card title={`Planlı (${planned.length})`} bodyClassName="space-y-2 overflow-y-auto p-4">
          {planned.length === 0 && <p className="text-sm text-zinc-500">Planlı antrenman yok.</p>}
          {planned.map((w) => (
            <WorkoutCard key={w.id} w={w} onChanged={() => void refresh()} onOpen={() => setSelected(w)} />
          ))}
        </Card>
        <Card title={`Tamamlanan (${completed.length})`} bodyClassName="space-y-2 overflow-y-auto p-4">
          {completed.length === 0 && <p className="text-sm text-zinc-500">Tamamlanan antrenman yok.</p>}
          {completed.map((w) => (
            <WorkoutCard key={w.id} w={w} onChanged={() => void refresh()} onOpen={() => setSelected(w)} />
          ))}
        </Card>
      </div>

      {selected && (
        <WorkoutDetailModal
          w={selected}
          onClose={() => setSelected(null)}
          onChanged={() => void refresh()}
        />
      )}
    </div>
  );
}
