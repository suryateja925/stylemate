import { Plus, Save, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Plan } from "../types";
import { Button, Card, Field, Notice, PageIntro, SelectField } from "../components/Ui";

const activities = ["College or university", "Office or work", "Meeting or interview", "Casual outing", "Friends gathering", "Date", "Party or function", "Wedding or traditional event", "Gym or sports", "Travel", "Home or relaxation", "Custom activity"];
type EventDraft = { id?: string; event_name: string; activity_type: string; occasion_type: string; custom_activity: string; start_time: string; duration_minutes: string; setting: "indoor" | "outdoor" | "both"; location: string; dress_code: string; formality: "relaxed" | "smart_casual" | "formal" | "traditional"; budget: string; preferences: string; notes: string };
const blank = (): EventDraft => ({ event_name: "", activity_type: "College or university", occasion_type: "", custom_activity: "", start_time: "", duration_minutes: "", setting: "indoor", location: "", dress_code: "", formality: "smart_casual", budget: "", preferences: "", notes: "" });
const today = () => new Date().toLocaleDateString("en-CA");

export function Plans() {
  const navigate = useNavigate();
  const [planDate, setPlanDate] = useState(today);
  const [events, setEvents] = useState<EventDraft[]>([blank()]);
  const [existing, setExisting] = useState<Plan | null>(null);
  const [weekPlans, setWeekPlans] = useState<Plan[]>([]);
  const [message, setMessage] = useState<{ text: string; tone: "error" | "success" }>({ text: "", tone: "success" });
  const [busy, setBusy] = useState(false);

  const fromPlan = (event: Plan["events"][number]): EventDraft => ({
    ...blank(), id: event.id, event_name: event.event_name ?? "", activity_type: event.activity_type,
    occasion_type: event.occasion_type ?? "", setting: (event.setting as EventDraft["setting"]) || "indoor",
    formality: (event.formality as EventDraft["formality"]) || "smart_casual", duration_minutes: event.duration_minutes?.toString() ?? "",
    custom_activity: event.custom_activity ?? "", start_time: event.start_time ?? "", location: event.location ?? "",
    dress_code: event.dress_code ?? "", budget: event.budget?.toString() ?? "", preferences: event.preferences ?? "", notes: event.notes ?? "",
  });

  const selectPlan = (plan: Plan | null, date: string) => {
    setPlanDate(date);
    setExisting(plan);
    setEvents(plan ? plan.events.filter((event) => !event.cancelled).map(fromPlan) : [blank()]);
  };

  useEffect(() => {
    Promise.all([api.plans(today()), api.plans()]).then(([todayPlans, allPlans]) => {
      setWeekPlans(allPlans);
      const plan = todayPlans[0] ?? null;
      selectPlan(plan, plan?.plan_date ?? today());
    }).catch((error: Error) => setMessage({ text: error.message, tone: "error" }));
  }, []);

  const update = (index: number, field: keyof EventDraft, value: string) => setEvents((current) => current.map((event, i) => i === index ? { ...event, [field]: value } : event));

  async function save(generate: boolean) {
    setBusy(true);
    setMessage({ text: "", tone: "success" });
    try {
      const body = {
        plan_date: planDate,
        events: events.map(({ id: _id, ...event }) => ({
          ...event,
          duration_minutes: event.duration_minutes ? Number(event.duration_minutes) : null,
          budget: event.budget ? Number(event.budget) : null,
          custom_activity: event.activity_type === "Custom activity" ? event.custom_activity : null,
        })),
      };
      const plan = existing ? await api.updatePlan(existing.id, body) : await api.createPlan(body);
      setExisting(plan);
      setWeekPlans((current) => [...current.filter((item) => item.id !== plan.id), plan]);
      if (generate) navigate(`/recommendations?plan=${plan.id}`);
      else setMessage({ text: "Plan saved. Preparation tasks were scheduled from the event date.", tone: "success" });
    } catch (error) {
      setMessage({ text: (error as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function cancelEvent(event: EventDraft) {
    if (!existing || !event.id || !window.confirm("Cancel this event and its pending preparation tasks?")) return;
    setBusy(true);
    try {
      const plan = await api.cancelPlanEvent(existing.id, event.id);
      setExisting(plan);
      setEvents(plan.events.filter((item) => !item.cancelled).map(fromPlan));
      setWeekPlans((current) => current.map((item) => item.id === plan.id ? plan : item));
      setMessage({ text: "Event cancelled. Completed preparation history was preserved.", tone: "success" });
    } catch (error) {
      setMessage({ text: (error as Error).message, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  return <>
    <PageIntro eyebrow="Daily check-in" title="What's on your plan today?" description="Choose one or more activities. Optional details help with the fit, but you can keep this check-in quick." action={<Button onClick={() => setEvents((current) => [...current, blank()])} variant="secondary"><Plus size={17} />Add event</Button>} />
    {message.text && <Notice tone={message.tone}>{message.text}</Notice>}
    <Card className="mt-6 overflow-x-auto"><div className="flex min-w-[720px] gap-3">{Array.from({ length: 7 }, (_, index) => { const day = new Date(); day.setHours(12, 0, 0, 0); day.setDate(day.getDate() + index); const key = day.toLocaleDateString("en-CA"); const plan = weekPlans.find((item) => item.plan_date === key); return <button key={key} onClick={() => selectPlan(plan ?? null, key)} className={`focus-ring min-w-24 rounded-2xl border p-3 text-left ${key === planDate ? "border-violet-500 bg-violet-50" : "border-slate-200 bg-white hover:border-violet-300"}`}><p className="text-xs font-bold uppercase text-slate-400">{day.toLocaleDateString(undefined, { weekday: "short" })}</p><p className="mt-1 text-xl font-bold text-slate-900">{day.getDate()}</p><p className="mt-2 text-xs font-semibold text-violet-600">{plan ? `${plan.events.filter((event) => !event.cancelled).length} event${plan.events.length === 1 ? "" : "s"}` : "Plan day"}</p></button>; })}</div></Card>
    <Card className="mt-6"><div className="grid max-w-md gap-4"><Field label="Plan date" type="date" value={planDate} onChange={(event) => selectPlan(weekPlans.find((plan) => plan.plan_date === event.target.value) ?? null, event.target.value)} /></div><div className="mt-8 space-y-5">{events.map((event, index) => <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5" key={`${event.id ?? index}-${event.activity_type}`}><div className="flex items-center justify-between"><div><span className="text-xs font-bold uppercase tracking-wider text-violet-600">Event {index + 1}</span><h3 className="mt-1 font-bold text-slate-900">{event.event_name || "Dress for this moment"}</h3></div><div className="flex items-center gap-2">{event.id && <Button variant="quiet" onClick={() => void cancelEvent(event)} disabled={busy}><Trash2 size={16} />Cancel event</Button>}{events.length > 1 && !event.id && <button onClick={() => setEvents((current) => current.filter((_, i) => i !== index))} className="rounded-xl p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600" aria-label={`Remove event ${index + 1}`}><Trash2 size={17} /></button>}</div></div><div className="mt-5 grid gap-4 md:grid-cols-2 lg:grid-cols-4"><Field label="Event name" value={event.event_name} onChange={(e) => update(index, "event_name", e.target.value)} placeholder="Optional title" /><SelectField label="Activity" value={event.activity_type} onChange={(e) => update(index, "activity_type", e.target.value)}>{activities.map((activity) => <option key={activity}>{activity}</option>)}</SelectField>{event.activity_type === "Custom activity" && <Field label="Custom activity" value={event.custom_activity} onChange={(e) => update(index, "custom_activity", e.target.value)} placeholder="What are you doing?" />}<Field label="Occasion type" value={event.occasion_type} onChange={(e) => update(index, "occasion_type", e.target.value)} placeholder="Wedding, interview…" /></div><div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-4"><Field label="Start time" type="time" value={event.start_time} onChange={(e) => update(index, "start_time", e.target.value)} /><Field label="Duration (minutes)" type="number" min={1} value={event.duration_minutes} onChange={(e) => update(index, "duration_minutes", e.target.value)} /><SelectField label="Setting" value={event.setting} onChange={(e) => update(index, "setting", e.target.value)}><option value="indoor">Indoor</option><option value="outdoor">Outdoor</option><option value="both">Both</option></SelectField><SelectField label="Formality" value={event.formality} onChange={(e) => update(index, "formality", e.target.value)}><option value="relaxed">Relaxed</option><option value="smart_casual">Smart casual</option><option value="formal">Formal</option><option value="traditional">Traditional</option></SelectField></div><div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-4"><Field label="Location" value={event.location} onChange={(e) => update(index, "location", e.target.value)} placeholder="Optional" /><Field label="Dress code" value={event.dress_code} onChange={(e) => update(index, "dress_code", e.target.value)} placeholder="Optional" /><Field label="Budget (INR)" type="number" min={0} value={event.budget} onChange={(e) => update(index, "budget", e.target.value)} placeholder="Optional" /><Field label="Preferences" value={event.preferences} onChange={(e) => update(index, "preferences", e.target.value)} placeholder="Optional" /></div><label className="mt-4 block"><span className="text-xs font-bold uppercase tracking-wider text-slate-500">Notes</span><textarea value={event.notes} onChange={(e) => update(index, "notes", e.target.value)} className="focus-ring mt-2 min-h-20 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm outline-none focus:border-violet-400" placeholder="Anything StyleMate should know?" /></label></div>)}</div><div className="mt-6 flex flex-wrap justify-end gap-3"><Button variant="secondary" onClick={() => void save(false)} disabled={busy}><Save size={17} />{busy ? "Saving…" : "Save plan"}</Button><Button onClick={() => void save(true)} disabled={busy}><Sparkles size={17} />Save & style my day</Button></div>{existing && <p className="mt-4 text-sm text-slate-500">This date already has a saved plan. Saving again updates its active events; cancelled events stay in history.</p>}</Card>
  </>;
}
