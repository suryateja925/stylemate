import { Database, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { api, getLocalUserId } from "../api";
import { useAuth } from "../auth";
import { Button, Card, Field, Notice, PageIntro } from "../components/Ui";

type Profile = { id: string; display_name: string; wardrobe_target: number };

export function Settings() {
  const { deleteAccount, mode, user } = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [wardrobeTarget, setWardrobeTarget] = useState(20);

  useEffect(() => {
    let active = true;
    api.profile().then((result) => {
      if (active) {
        setProfile(result);
        setDisplayName(result.display_name);
        setWardrobeTarget(result.wardrobe_target);
      }
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : "Could not load account settings.");
    });
    return () => { active = false; };
  }, []);

  const accountId = profile?.id ?? (mode === "local" ? getLocalUserId() : user?.id ?? "Loading account");
  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSaved(false);
    setSaving(true);
    try {
      const updated = await api.updateProfile({
        display_name: displayName.trim(),
        wardrobe_target: wardrobeTarget,
      });
      setProfile(updated);
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save account settings.");
    } finally {
      setSaving(false);
    }
  }

  async function removeAccount() {
    if (!window.confirm("Permanently delete your StyleMate account, wardrobe, plans, and uploaded images? This cannot be undone.")) return;
    setError("");
    setDeleting(true);
    try {
      await deleteAccount();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Account deletion failed. Please try again.");
    } finally {
      setDeleting(false);
    }
  }
  return <>
    <PageIntro eyebrow="Settings & privacy" title="Control your StyleMate workspace." description="Manage your account and understand how your wardrobe data is protected." />
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <div className="flex gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-emerald-100 text-emerald-700"><ShieldCheck size={19} /></span>
          <div>
            <h3 className="font-bold text-slate-950">Privacy boundaries</h3>
            <p className="mt-2 text-sm leading-6 text-slate-500">{mode === "supabase" ? "Your account is authenticated by Supabase. Wardrobe records are scoped to your account, database row-level security blocks direct browser data access, and private garment photos use short-lived signed links." : "Local development uses an isolated profile on this device. Production uses verified Supabase sessions, row-level security, and short-lived private image links."}</p>
          </div>
        </div>
        <Notice tone="info">The app does not access a calendar by default, does not infer sensitive attributes, and only records an outfit as worn after you choose that action.</Notice>
      </Card>
      <Card>
        <div className="flex gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-2xl bg-violet-100 text-violet-700"><Database size={19} /></span>
          <div>
            <h3 className="font-bold text-slate-950">Account</h3>
            <p className="mt-2 break-all text-xs leading-5 text-slate-500">{accountId}</p>
            {mode === "local" && <p className="mt-2 text-xs text-slate-500">Local development profile</p>}
          </div>
        </div>
        <form className="mt-6 space-y-4" onSubmit={(event) => void saveProfile(event)}>
          <Field label="Display name" value={displayName} onChange={(event) => setDisplayName(event.target.value)} minLength={1} maxLength={120} required />
          <Field label="Wardrobe goal" type="number" value={wardrobeTarget} onChange={(event) => setWardrobeTarget(Number(event.target.value))} min={1} max={10000} required />
          <Button disabled={!profile || saving} type="submit">{saving ? "Saving..." : "Save account settings"}</Button>
          {saved && <p role="status" className="text-sm text-emerald-700">Settings saved.</p>}
        </form>
        {error && <p role="alert" className="mt-5 text-sm text-rose-700">{error}</p>}
        <p className="mt-6 text-xs leading-5 text-slate-400">Images and account data are stored separately from this device in production.</p>
        {mode === "supabase" && <button className="mt-5 rounded-xl bg-rose-50 px-4 py-2.5 text-sm font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-50" disabled={deleting} onClick={() => void removeAccount()} type="button">{deleting ? "Deleting account..." : "Delete account and data"}</button>}
      </Card>
    </div>
  </>;
}
