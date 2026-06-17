import { useEffect, useState } from "react";
import { getUsageLogs, UsageLog } from "../api";
import { Button } from "../ui";

function fmtDate(iso: string) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

export default function UsageLogsTable() {
  const [logs, setLogs] = useState<UsageLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!show) return;
    let mounted = true;
    setLoading(true);
    getUsageLogs(50)
      .then((data) => {
        if (mounted) {
          setLogs(data);
          setLoading(false);
        }
      })
      .catch((e) => {
        console.error(e);
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [show]);

  if (!show) {
    return (
      <div className="mt-4 flex justify-center">
        <Button variant="ghost" onClick={() => setShow(true)}>
          API İstekleri Loglarını Göster (Logs)
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-8 rounded-lg border border-zinc-800 bg-zinc-950/50 flex flex-col">
      <div className="flex items-center justify-between border-b border-zinc-800 p-4">
        <div>
          <h2 className="text-lg font-medium text-zinc-100">Logs</h2>
          <p className="text-sm text-zinc-400">Son 50 API isteği (API requests log)</p>
        </div>
        <Button variant="ghost" onClick={() => setShow(false)}>Gizle</Button>
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-4 text-sm text-zinc-500">Yükleniyor...</div>
        ) : (
          <table className="w-full text-left text-sm text-zinc-400">
            <thead className="bg-zinc-900/50 text-xs uppercase text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Model</th>
                <th className="px-4 py-3 font-medium">Category / Label</th>
                <th className="px-4 py-3 font-medium text-right">Input</th>
                <th className="px-4 py-3 font-medium text-right">Output</th>
                <th className="px-4 py-3 font-medium text-right">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {logs.map((log, i) => (
                <tr key={i} className="hover:bg-zinc-900/30 transition-colors">
                  <td className="px-4 py-3 whitespace-nowrap">{fmtDate(log.timestamp)}</td>
                  <td className="px-4 py-3 text-zinc-300 font-medium">{log.model}</td>
                  <td className="px-4 py-3">
                    <span className="text-zinc-500 mr-2">{log.category}</span>
                    {log.label && <span className="text-xs px-1.5 py-0.5 bg-zinc-800 text-zinc-300 rounded">{log.label}</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-zinc-300">{log.prompt_tokens}</span> <span className="text-zinc-600 text-xs">tok</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="text-zinc-300">{log.completion_tokens}</span> <span className="text-zinc-600 text-xs">tok</span>
                  </td>
                  <td className="px-4 py-3 text-right text-emerald-400">
                    ${parseFloat(log.cost_usd || "0").toFixed(5)}
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-4 text-center text-zinc-500">
                    Kayıt bulunamadı.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
