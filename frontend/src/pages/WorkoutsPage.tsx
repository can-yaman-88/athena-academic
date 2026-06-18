import { useCallback, useEffect, useRef, useState } from "react";
import {
  completeWorkout,
  deleteWorkout,
  getWorkouts,
  streamChat,
  uploadWorkoutFile,
  syncRunalyze,
  type Workout,
} from "../api";
import { Badge, Button, Card } from "../ui";

const inputCls =
  "rounded-lg border border-line-strong bg-surface-2 px-2.5 py-1.5 text-sm text-zinc-100 outline-none focus:border-emerald-500";

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
    <div className="rounded-lg border border-line bg-surface-2/50 p-3">
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
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncMsg, setSyncMsg] = useState("");

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

  async function handleSyncRunalyze() {
    setSyncBusy(true);
    setSyncMsg("");
    try {
      const res = await syncRunalyze();
      setSyncMsg(`✓ ${res.imported} aktivite senkronize edildi`);
      await refresh();
    } catch (e) {
      setSyncMsg(`✗ ${(e as Error).message}`);
    } finally {
      setSyncBusy(false);
    }
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
        <Card title="Runalyze Senkronizasyonu" bodyClassName="p-4">
          <p className="text-xs text-zinc-400 mb-3">
            Runalyze hesabınızdaki son aktiviteleri otomatik olarak Athena'ya çeker. (Sistem ayarlarına RUNALYZE_TOKEN eklenmiş olmalıdır.)
          </p>
          <div className="flex items-center gap-3">
            <Button disabled={syncBusy} onClick={() => void handleSyncRunalyze()}>
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
