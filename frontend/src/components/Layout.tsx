import { NavLink, Outlet } from "react-router-dom";
import {
  LayoutDashboard,
  FileText,
  ListChecks,
  Dumbbell,
  Lightbulb,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

const links: { to: string; label: string; end: boolean; icon: LucideIcon }[] = [
  { to: "/", label: "Günüm", end: true, icon: LayoutDashboard },
  { to: "/pdf", label: "PDF Otomasyonu", end: false, icon: FileText },
  { to: "/manage", label: "Görevler", end: false, icon: ListChecks },
  { to: "/workouts", label: "Antrenman", end: false, icon: Dumbbell },
  { to: "/ideas", label: "Fikir Defteri", end: false, icon: Lightbulb },
];

export default function Layout() {
  return (
    <div className="flex h-screen flex-col text-zinc-100">
      <header className="z-20 flex items-center justify-between gap-4 border-b border-line bg-[var(--bg)]/80 px-6 py-3 backdrop-blur-xl">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-primary-500/15 text-primary-300 shadow-[inset_0_0_0_1px_rgba(139,124,246,0.3)]">
            <Sparkles size={16} strokeWidth={2.25} />
          </span>
          <h1 className="text-base font-semibold tracking-tight text-zinc-50">
            Athena
          </h1>
        </div>
        <nav className="flex items-center gap-0.5 rounded-xl border border-line bg-white/[0.02] p-1">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                className={({ isActive }) =>
                  `flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-primary-500/15 text-primary-200 shadow-[inset_0_0_0_1px_rgba(139,124,246,0.3)]"
                      : "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
                  }`
                }
              >
                <Icon size={15} strokeWidth={2} />
                <span className="hidden sm:inline">{l.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden p-4">
        <Outlet />
      </main>
    </div>
  );
}
