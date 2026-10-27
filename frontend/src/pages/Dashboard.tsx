import { ArrowRight, CalendarCheck2, Shirt, Sparkles, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Plan, Progress } from "../types";
import { Button, Card, Empty, Loading, Notice, PageIntro } from "../components/Ui";
import { VoiceAssistant } from "../components/VoiceAssistant";

const today = new Date().toISOString().slice(0, 10);

export function Dashboard() {
  const [progress, setProgress] = useState<Progress | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { Promise.all([api.progress(), api.plans(today)]).then(([summary, plans]) => { setProgress(summary); setPlan(plans[0] ?? null); }).catch((err: Error) => setError(err.message)); }, []);
  return <>
    <PageIntro eyebrow="Good morning" title="What are you wearing today?" description="Tell StyleMate what your day looks like, then choose from clothes you have actually confirmed in your wardrobe." action={<Link to="/plans"><Button><CalendarCheck2 size={17} />Plan my day</Button></Link>} />
    <VoiceAssistant />
    {error && <Notice tone="error">{error}. Start the FastAPI server at port 8000 and refresh.</Notice>}
    {!progress ? <Loading label="Loading your wardrobe pulse…" /> : <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[{ label: "Confirmed pieces", value: progress.confirmed_wardrobe_items, icon: Shirt, tint: "bg-violet-100 text-violet-700" }, { label: "Today's events", value: plan?.events.length ?? 0, icon: CalendarCheck2, tint: "bg-amber-100 text-amber-700" }, { label: "Saved outfits", value: progress.saved_outfits, icon: Sparkles, tint: "bg-fuchsia-100 text-fuchsia-700" }, { label: "Wardrobe progress", value: `${progress.completion_percentage}%`, icon: UploadCloud, tint: "bg-emerald-100 text-emerald-700" }].map(({ label, value, icon: Icon, tint }) => <Card key={label} className="p-4"><div className="flex items-start justify-between"><span className={`grid h-10 w-10 place-items-center rounded-2xl ${tint}`}><Icon size={19} /></span><span className="text-xs font-semibold text-slate-400">Real data</span></div><p className="mt-5 text-3xl font-bold tracking-tight text-slate-950">{value}</p><p className="mt-1 text-sm text-slate-500">{label}</p></Card>)}</div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[1.25fr_.75fr]">
        <Card><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-violet-600">Today</p><h3 className="mt-1 text-xl font-bold text-slate-950">Your plan at a glance</h3></div><Link to="/recommendations" className="text-sm font-semibold text-violet-600 hover:text-violet-800">Open studio <ArrowRight className="inline" size={15} /></Link></div>{plan ? <div className="mt-6 space-y-3">{plan.events.map((event) => <div key={event.id} className="flex items-center justify-between rounded-2xl bg-slate-50 p-4"><div><p className="font-semibold text-slate-800">{event.custom_activity || event.activity_type}</p><p className="mt-1 text-xs text-slate-500">{event.start_time || "Any time"}{event.location ? ` · ${event.location}` : ""}</p></div><span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-500">{event.formality?.replace("_", " ") || "smart casual"}</span></div>)}</div> : <Empty title="No plans for today" description="A quick check-in gives your recommendations the context they need." action={<Link to="/plans"><Button variant="secondary">Add today's plans</Button></Link>} />}</Card>
        <Card className="overflow-hidden bg-slate-950 text-white"><p className="text-xs font-bold uppercase tracking-wider text-violet-300">Your next step</p><h3 className="mt-3 text-2xl font-bold leading-tight">Build a wardrobe that works harder.</h3><p className="mt-3 text-sm leading-6 text-slate-300">Scan a real bundle of clothes, review what is visible, and confirm only the pieces you want StyleMate to use.</p><Link to="/scanner" className="mt-6 inline-flex"><Button variant="secondary" className="border-white/20 bg-white/10 text-white hover:bg-white/20"><UploadCloud size={17} />Scan a bundle</Button></Link></Card>
      </div>
    </>}
  </>;
}
