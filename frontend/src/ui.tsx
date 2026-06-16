// Shared UI primitives — keep the dark minimalist zinc/emerald theme consistent
// across pages while adding a bit more polish (cards, buttons, badges).
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Card({
  title,
  right,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <div
      className={`flex flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50 shadow-card transition-shadow duration-200 hover:shadow-card-hover ${className}`}
    >
      {title !== undefined && (
        <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            {title}
          </h2>
          {right}
        </div>
      )}
      <div className={`min-h-0 flex-1 ${bodyClassName || "p-4"}`}>{children}</div>
    </div>
  );
}

type Variant = "primary" | "ghost" | "danger" | "subtle";

const variants: Record<Variant, string> = {
  primary:
    "bg-emerald-500/90 text-zinc-950 hover:bg-emerald-400 disabled:opacity-50",
  ghost:
    "border border-zinc-700 text-zinc-200 hover:border-zinc-500 hover:bg-zinc-800/50 disabled:opacity-50",
  danger:
    "border border-rose-500/40 text-rose-300 hover:bg-rose-500/10 disabled:opacity-50",
  subtle: "text-zinc-400 hover:text-zinc-100 disabled:opacity-50",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={`rounded-lg px-3 py-1.5 text-sm font-medium transition active:translate-y-px disabled:cursor-not-allowed ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

const tones: Record<string, string> = {
  emerald: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  rose: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  sky: "border-sky-500/40 bg-sky-500/10 text-sky-300",
  zinc: "border-zinc-700 bg-zinc-800/50 text-zinc-300",
};

export function Badge({
  tone = "zinc",
  children,
}: {
  tone?: keyof typeof tones;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  sub,
  tone = "zinc",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: keyof typeof tones;
}) {
  const accent: Record<string, string> = {
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    rose: "text-rose-400",
    sky: "text-sky-400",
    zinc: "text-zinc-100",
  };
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${accent[tone]}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export function fmtDeadline(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function usd(n: number): string {
  return `$${(n ?? 0).toFixed(4)}`;
}
