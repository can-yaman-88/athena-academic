import { artifactUrl, type PdfJob } from "../api";
import { Badge, fmtDeadline, usd } from "../ui";

const tone: Record<PdfJob["status"], "emerald" | "amber" | "rose"> = {
  completed: "emerald",
  processing: "amber",
  failed: "rose",
};

const label: Record<PdfJob["status"], string> = {
  completed: "tamam",
  processing: "işleniyor",
  failed: "hata",
};

export default function PdfHistory({ jobs }: { jobs: PdfJob[] }) {
  if (jobs.length === 0) {
    return <p className="p-4 text-sm text-zinc-500">Henüz işlenmiş PDF yok.</p>;
  }
  return (
    <ul className="flex flex-col gap-2 overflow-y-auto p-4">
      {jobs.map((j) => (
        <li
          key={j.id}
          className="rounded-lg border border-line bg-surface-2/50 p-3"
        >
          <div className="flex items-start justify-between gap-2">
            <span className="min-w-0 truncate text-sm text-zinc-100" title={j.filename}>
              {j.filename}
            </span>
            <Badge tone={tone[j.status]}>{label[j.status]}</Badge>
          </div>
          <div className="mt-1 text-xs text-zinc-500">
            {fmtDeadline(j.created_at)} · {usd(j.cost_usd)} · {j.chunks_ingested} parça
          </div>
          {j.error && (
            <div className="mt-1 truncate text-xs text-rose-400" title={j.error}>
              {j.error}
            </div>
          )}
          {j.artifacts.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {j.artifacts.map((a) => {
                const name = a.split("/").pop() ?? a;
                const ext = name.split(".").pop()?.toUpperCase() ?? "FILE";
                return (
                  <a
                    key={a}
                    href={artifactUrl(j.id, a)}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border border-line-strong px-2 py-0.5 text-xs text-zinc-300 hover:border-emerald-500 hover:text-emerald-300"
                    title={name}
                  >
                    {ext}
                  </a>
                );
              })}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
