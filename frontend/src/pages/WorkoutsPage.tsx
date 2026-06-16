import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeWorkout,
  createWorkout,
  deleteWorkout,
  getWorkouts,
  streamChat,
  uploadWorkoutFile,
  type Workout,
} from "../api";
import { Badge, Button, Card, fmtDeadline } from "../ui";

const inputCls =
  "rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

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
}: {
  w: Workout;
  onChanged: () => void;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-100">
              {w.title || "Antrenman"}
            </span>
            <Badge tone={w.calculated_load > 400 ? "rose" : "zinc"}>
              yük {w.calculated_load}
            </Badge>
          </div>
          <div className="mt-0.5 text-xs text-zinc-500">
            {w.date} · {w.duration_minutes} dk · RPE {w.rpe_score}
          </div>
          <Metrics w={w} />
        </div>
        <div className="flex shrink-0 gap-1.5">
          {w.status === "planned" && (
            <Button
              variant="ghost"
              onClick={async () => {
                await completeWorkout(w.id);
                onChanged();
              }}
            >
              Tamamla
            </Button>
          )}
          <Button
            variant="danger"
            onClick={async () => {
              await deleteWorkout(w.id);
              onChanged();
            }}
          >
            Sil
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function WorkoutsPage() {
  const [workouts, setWorkouts] = useState<Workout[]>([]);
  const [uploadMsg, setUploadMsg] = useState("");
  const [planText, setPlanText] = useState("");
  const [planMsg, setPlanMsg] = useState("");
  const [planBusy, setPlanBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({
    duration_minutes: 60,
    rpe_score: 5,
    date: today(),
    status: "completed" as "planned" | "completed",
    title: "",
    distance_km: "",
    pace: "",
    avg_hr: "",
  });

  const refresh = useCallback(async () => {
    try {
      setWorkouts(await getWorkouts());
    } catch {
      /* ignore */
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function add() {
    await createWorkout({
      duration_minutes: Number(form.duration_minutes) || 1,
      rpe_score: Number(form.rpe_score) || 1,
      date: form.date,
      status: form.status,
      title: form.title || undefined,
      distance_km: form.distance_km ? Number(form.distance_km) : undefined,
      pace: form.pace || undefined,
      avg_hr: form.avg_hr ? Number(form.avg_hr) : undefined,
    });
    setForm({ ...form, title: "", distance_km: "", pace: "", avg_hr: "" });
    await refresh();
  }

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
      await streamChat(`/plan\n${planText.trim()}`, (evt) => {
        if (evt.type === "message") setPlanMsg(String(evt.content));
        else if (evt.type === "error") setPlanMsg(`hata: ${String(evt.error)}`);
      });
      setPlanText("");
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
        <Card title="Antrenman Ekle" bodyClassName="p-4">
          <div className="grid grid-cols-2 gap-2">
            <input className={inputCls} placeholder="Başlık (ops.)" value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <select className={inputCls} value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as "planned" | "completed" })}>
              <option value="completed">Tamamlandı</option>
              <option value="planned">Planlı</option>
            </select>
            <label className="text-xs text-zinc-500">Süre (dk)
              <input type="number" min={1} className={`${inputCls} w-full`} value={form.duration_minutes}
                onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) })} />
            </label>
            <label className="text-xs text-zinc-500">RPE
              <input type="number" min={1} max={10} className={`${inputCls} w-full`} value={form.rpe_score}
                onChange={(e) => setForm({ ...form, rpe_score: Number(e.target.value) })} />
            </label>
            <label className="text-xs text-zinc-500">Tarih
              <input type="date" className={`${inputCls} w-full`} value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })} />
            </label>
            <label className="text-xs text-zinc-500">Mesafe (km)
              <input type="number" step="0.1" className={`${inputCls} w-full`} value={form.distance_km}
                onChange={(e) => setForm({ ...form, distance_km: e.target.value })} />
            </label>
            <label className="text-xs text-zinc-500">Tempo (/km)
              <input className={`${inputCls} w-full`} placeholder="5:30" value={form.pace}
                onChange={(e) => setForm({ ...form, pace: e.target.value })} />
            </label>
            <label className="text-xs text-zinc-500">Ort. nabız
              <input type="number" className={`${inputCls} w-full`} value={form.avg_hr}
                onChange={(e) => setForm({ ...form, avg_hr: e.target.value })} />
            </label>
          </div>
          <Button className="mt-3 w-full" onClick={() => void add()}>Ekle</Button>
        </Card>

        <Card title="Veri Dosyası İçe Aktar (JSON / CSV / .FIT)" bodyClassName="p-4">
          <input ref={fileRef} type="file" accept=".json,.csv,.fit" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); e.target.value = ""; }} />
          <div
            onClick={() => fileRef.current?.click()}
            className="flex h-24 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-zinc-700 text-center hover:border-zinc-500"
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
          {planned.map((w) => <WorkoutCard key={w.id} w={w} onChanged={() => void refresh()} />)}
        </Card>
        <Card title={`Tamamlanan (${completed.length})`} bodyClassName="space-y-2 overflow-y-auto p-4">
          {completed.length === 0 && <p className="text-sm text-zinc-500">Tamamlanan antrenman yok.</p>}
          {completed.map((w) => <WorkoutCard key={w.id} w={w} onChanged={() => void refresh()} />)}
        </Card>
      </div>
    </div>
  );
}
