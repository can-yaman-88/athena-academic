// Shared UI primitives — "Aurora Indigo" language: layered elevated surfaces,
// hairline translucent borders, soft shadows, iris/violet primary + crisp focus.
// These carry most of the restyle since every page composes them.
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
      className={`card-elevated flex flex-col overflow-hidden rounded-xl transition-[box-shadow,border-color] duration-200 ${className}`}
    >
      {title !== undefined && (
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-zinc-400">
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
type Size = "sm" | "md";

const variants: Record<Variant, string> = {
  primary:
    "bg-primary-500 text-white shadow-sm hover:brightness-110 hover:shadow-glow disabled:opacity-50",
  ghost:
    "border border-line-strong bg-white/[0.02] text-zinc-200 hover:border-zinc-500 hover:bg-white/[0.05] disabled:opacity-50",
  danger:
    "border border-rose-500/40 bg-rose-500/5 text-rose-300 hover:bg-rose-500/15 disabled:opacity-50",
  subtle: "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100 disabled:opacity-50",
};

const sizes: Record<Size, string> = {
  sm: "px-2.5 py-1 text-xs",
  md: "px-3.5 py-1.5 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
}) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition active:translate-y-px disabled:cursor-not-allowed disabled:active:translate-y-0 ${sizes[size]} ${variants[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

const tones: Record<string, string> = {
  emerald: "border-primary-500/30 bg-primary-500/10 text-primary-300",
  amber: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  rose: "border-rose-500/30 bg-rose-500/10 text-rose-300",
  sky: "border-primary-500/30 bg-primary-500/10 text-primary-300",
  zinc: "border-line-strong bg-white/[0.04] text-zinc-300",
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
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${tones[tone]}`}
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
    emerald: "text-primary-400",
    amber: "text-amber-400",
    rose: "text-rose-400",
    sky: "text-primary-400",
    zinc: "text-zinc-100",
  };
  return (
    <div className="rounded-xl border border-line bg-surface-2/60 p-3.5 transition-colors hover:border-line-strong">
      <div className="text-[10px] font-medium uppercase tracking-[0.1em] text-zinc-500">
        {label}
      </div>
      <div className={`mt-1.5 text-2xl font-semibold tracking-tight ${accent[tone]}`}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-zinc-500">{sub}</div>}
    </div>
  );
}

export function fmtDeadline(iso: string | null | undefined): string {
  if (!iso) return "tarihsiz";
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
