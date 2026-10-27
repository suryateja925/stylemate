import { NavLink, Outlet, useLocation } from "react-router-dom";
import { CalendarDays, ChevronRight, History, LayoutDashboard, Settings, Shirt, Sparkles, SlidersHorizontal, UploadCloud, X } from "lucide-react";
import { useState } from "react";
import { useAuth } from "../auth";

const links = [
  { to: "/", label: "Today", icon: LayoutDashboard },
  { to: "/plans", label: "Daily plans", icon: CalendarDays },
  { to: "/recommendations", label: "Outfit studio", icon: Sparkles },
  { to: "/scanner", label: "Bundle scanner", icon: UploadCloud },
  { to: "/wardrobe", label: "My wardrobe", icon: Shirt },
  { to: "/history", label: "History", icon: History },
  { to: "/preferences", label: "Style profile", icon: SlidersHorizontal },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Layout() {
  const { mode, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [accountError, setAccountError] = useState("");
  const location = useLocation();
  const activeLabel = links.find((link) => link.to === location.pathname)?.label ?? "Today";
  async function handleSignOut() {
    setAccountError("");
    try {
      await signOut();
    } catch (reason) {
      setAccountError(reason instanceof Error ? reason.message : "Could not sign out. Please try again.");
    }
  }
  return (
    <div className="min-h-screen bg-[#f7f8fc]">
      <aside className={`fixed inset-y-0 left-0 z-40 w-72 border-r border-slate-200 bg-white p-6 transition-transform lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex items-center justify-between">
          <NavLink to="/" className="flex items-center gap-3" onClick={() => setOpen(false)}>
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-950 text-lg text-white shadow-lg shadow-slate-300">✦</span>
            <span><strong className="block text-lg tracking-tight">StyleMate</strong><span className="text-xs text-slate-500">Your daily stylist</span></span>
          </NavLink>
          <button className="rounded-lg p-2 text-slate-500 lg:hidden" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={18} /></button>
        </div>
        <div className="mt-10 rounded-3xl bg-gradient-to-br from-violet-600 to-fuchsia-500 p-5 text-white">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/75">Daily clarity</p>
          <p className="mt-3 text-xl font-semibold leading-tight">Dress for the day you actually have.</p>
          <NavLink to="/plans" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-white/15 px-3 py-2 text-sm font-semibold hover:bg-white/25" onClick={() => setOpen(false)}>Plan today <ChevronRight size={16} /></NavLink>
        </div>
        <nav className="mt-8 space-y-1" aria-label="Primary navigation">
          {links.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)} className={({ isActive }) => `focus-ring flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition ${isActive ? "bg-slate-950 text-white shadow-lg shadow-slate-200" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"}`}><Icon size={18} />{label}</NavLink>)}
        </nav>
        {mode === "local" ? <div className="absolute bottom-6 left-6 right-6 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-500">Local development mode is active. Production uses verified account sessions.</div> : <div className="absolute bottom-6 left-6 right-6"><button className="w-full rounded-2xl border border-slate-200 bg-slate-50 p-4 text-left text-sm font-semibold text-slate-600 hover:bg-slate-100" onClick={() => void handleSignOut()}>Sign out</button>{accountError && <p role="alert" className="mt-2 text-xs text-rose-700">{accountError}</p>}</div>}
      </aside>
      <div className="lg:pl-72">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200/80 bg-[#f7f8fc]/85 px-5 py-4 backdrop-blur-xl lg:px-10">
          <div className="flex items-center gap-3"><button onClick={() => setOpen(true)} className="rounded-xl bg-white p-2 text-slate-600 shadow-sm lg:hidden" aria-label="Open navigation"><SlidersHorizontal size={18} /></button><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">StyleMate AI</p><h1 className="text-xl font-bold text-slate-950">{activeLabel}</h1></div></div>
          <NavLink to="/preferences" className="focus-ring flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700"><span className="grid h-8 w-8 place-items-center rounded-xl bg-violet-100 text-violet-700">SM</span><span className="hidden sm:block">My style</span></NavLink>
        </header>
        <main className="mx-auto max-w-7xl p-5 lg:p-10"><Outlet /></main>
      </div>
    </div>
  );
}
