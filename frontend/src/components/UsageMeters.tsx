import { useEffect, useState } from "react";
import { getUsage, type UsageSnapshot } from "../api";
import { Stat, usd } from "../ui";
import UsageLogsTable from "./UsageLogsTable";

function Meter({
  title,
  cat,
  tone,
}: {
  title: string;
  cat: UsageSnapshot["pdf"] | undefined;
  tone: "emerald" | "sky";
}) {
  return (
    <div className="rounded-lg border border-line bg-surface-2/50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-zinc-200">{title}</span>
        <span
          className={`text-sm font-semibold ${
            tone === "emerald" ? "text-emerald-400" : "text-sky-400"
          }`}
        >
          {usd(cat?.total_cost_usd ?? 0)}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div>
          <div className="text-zinc-500">çağrı</div>
          <div className="text-zinc-200">{cat?.calls ?? 0}</div>
        </div>
        <div>
          <div className="text-zinc-500">token</div>
          <div className="text-zinc-200">{(cat?.total_tokens ?? 0).toLocaleString()}</div>
        </div>
        <div>
          <div className="text-zinc-500">ort./çağrı</div>
          <div className="text-zinc-200">{usd(cat?.avg_cost_per_call_usd ?? 0)}</div>
        </div>
      </div>
    </div>
  );
}

export default function UsageMeters() {
  const [usage, setUsage] = useState<UsageSnapshot | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        setUsage(await getUsage());
      } catch {
        /* ignore */
      }
    };
    void refresh();
    const id = setInterval(() => void refresh(), 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <Stat
          label="Toplam maliyet"
          value={usd(usage?.total.total_cost_usd ?? 0)}
          tone="emerald"
        />
        <Stat
          label="Toplam token"
          value={(usage?.total.total_tokens ?? 0).toLocaleString()}
          tone="sky"
        />
      </div>
      <Meter title="PDF otomasyonu" cat={usage?.pdf} tone="emerald" />
      <Meter title="Diğer kullanım (ajan)" cat={usage?.agent} tone="sky" />
      <UsageLogsTable />
    </div>
  );
}
