import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "Günüm", end: true },
  { to: "/pdf", label: "PDF Otomasyonu", end: false },
  { to: "/manage", label: "Görevler", end: false },
  { to: "/workouts", label: "Antrenman", end: false },
  { to: "/ideas", label: "Fikir Defteri", end: false },
];

export default function Layout() {
  return (
    <div className="flex h-screen flex-col bg-zinc-950 text-zinc-100">
      <header className="flex items-center justify-between border-b border-zinc-800 bg-zinc-950/70 px-6 py-3 backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400 shadow-[0_0_10px] shadow-emerald-400/70" />
          <h1 className="text-base font-semibold tracking-tight text-emerald-400">
            Athena
          </h1>
        </div>
        <nav className="flex items-center gap-1">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                  isActive
                    ? "bg-emerald-500/15 text-emerald-300"
                    : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-100"
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="min-h-0 flex-1 overflow-hidden p-4">
        <Outlet />
      </main>
    </div>
  );
}
