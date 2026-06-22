import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import {
  MessageSquare,
  FileText,
  GraduationCap,
  NotebookText,
  CalendarDays,
  Lightbulb,
  Sparkles,
  Brain,
  type LucideIcon,
} from "lucide-react";
import { useTheme, THEMES } from "../ThemeContext";
import CyberpunkCanvasBackground from "./backgrounds/CyberpunkCanvasBackground";
import TerminalCanvasBackground from "./backgrounds/TerminalCanvasBackground";
import BrainModal from "./BrainModal";

const links: { to: string; label: string; end: boolean; icon: LucideIcon }[] = [
  { to: "/", label: "Sohbet", end: true, icon: MessageSquare },
  { to: "/akademik", label: "Akademik", end: false, icon: GraduationCap },
  { to: "/notlar", label: "Notlar", end: false, icon: NotebookText },
  { to: "/gunum", label: "Günüm", end: false, icon: CalendarDays },
  { to: "/ideas", label: "Fikir Defteri", end: false, icon: Lightbulb },
  { to: "/pdf", label: "PDF Otomasyonu", end: false, icon: FileText },
];

function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  return (
    <div
      className="flex items-center gap-0.5 rounded-xl border border-line bg-white/[0.02] p-1"
      role="group"
      aria-label="Tema"
    >
      {THEMES.map((t) => (
        <button
          key={t.id}
          onClick={() => setTheme(t.id)}
          aria-pressed={theme === t.id}
          title={`${t.label} teması`}
          className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
            theme === t.id
              ? "bg-primary-500/15 text-primary-200 shadow-[inset_0_0_0_1px_rgb(var(--primary)/0.3)]"
              : "text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export default function Layout() {
  const { theme } = useTheme();
  const [brainOpen, setBrainOpen] = useState(false);
  return (
    <div className="relative flex h-screen flex-col text-zinc-100">
      {theme === "cyberpunk" && <CyberpunkCanvasBackground />}
      {theme === "terminal" && <TerminalCanvasBackground />}

      <header className="z-20 flex items-center justify-between gap-4 border-b border-line bg-[rgb(var(--bg)/0.8)] px-6 py-3 backdrop-blur-xl">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-primary-500/15 text-primary-300 shadow-[inset_0_0_0_1px_rgb(var(--primary)/0.3)]">
            <Sparkles size={16} strokeWidth={2.25} />
          </span>
          <h1 className="text-base font-semibold tracking-tight text-zinc-50">
            Athena
          </h1>
        </div>
        <div className="flex items-center gap-2">
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
                        ? "bg-primary-500/15 text-primary-200 shadow-[inset_0_0_0_1px_rgb(var(--primary)/0.3)]"
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
          <button
            onClick={() => setBrainOpen(true)}
            title="Brain — Uzun Vadeli Hafıza"
            className="flex items-center gap-1.5 rounded-xl border border-line bg-white/[0.02] px-2.5 py-1.5 text-sm font-medium text-zinc-400 transition-colors hover:bg-white/[0.05] hover:text-primary-300"
          >
            <Brain size={15} strokeWidth={2} />
            <span className="hidden md:inline">Brain</span>
          </button>
          <ThemeSwitcher />
        </div>
      </header>
      <main className="relative z-10 min-h-0 flex-1 overflow-hidden p-4">
        <Outlet />
      </main>
      <BrainModal open={brainOpen} onClose={() => setBrainOpen(false)} />
    </div>
  );
}
