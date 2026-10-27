import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth";

export function AuthScreen() {
  const { recoveryRequired, signIn, signUp, sendPasswordReset, updatePassword } = useAuth();
  const [view, setView] = useState<"sign-in" | "sign-up" | "reset" | "recovery">("sign-in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (recoveryRequired) setView("recovery");
  }, [recoveryRequired]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);
    try {
      if (view === "reset") {
        await sendPasswordReset(email);
        setNotice("If an account exists for this address, a password-reset link will arrive by email.");
      } else if (view === "recovery") {
        await updatePassword(password);
        setNotice("Your password has been updated.");
        setPassword("");
      } else if (view === "sign-up") {
        const requiresEmailConfirmation = await signUp(email, password);
        if (requiresEmailConfirmation) {
          setNotice("Check your email to confirm your account, then sign in.");
        } else {
          setNotice("Your account is ready.");
        }
      } else {
        await signIn(email, password);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Authentication failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 px-5 py-12">
      <section className="w-full max-w-md rounded-3xl bg-white p-8 shadow-2xl">
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-violet-600">StyleMate AI</p>
        <h1 className="mt-4 text-3xl font-bold text-slate-950">{view === "recovery" ? "Choose a new password" : view === "reset" ? "Reset your password" : view === "sign-up" ? "Create your account" : "Welcome back"}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">{view === "reset" ? "We’ll send a secure password-reset link if this email belongs to an account." : "Sign in securely to access your private wardrobe and plans."}</p>
        <form className="mt-7 space-y-4" onSubmit={(event) => void submit(event)}>
          {view !== "recovery" && <label className="block text-sm font-semibold text-slate-700">
            Email address
            <input autoComplete="email" className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </label>}
          {view !== "reset" && <label className="block text-sm font-semibold text-slate-700">
            {view === "recovery" ? "New password" : "Password"}
            <input autoComplete={view === "sign-up" || view === "recovery" ? "new-password" : "current-password"} className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" minLength={8} type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </label>}
          {error && <p role="alert" className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
          {notice && <p role="status" className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
          <button className="w-full rounded-xl bg-slate-950 px-4 py-3 font-semibold text-white disabled:opacity-50" disabled={submitting} type="submit">
            {submitting ? "Please wait..." : view === "recovery" ? "Update password" : view === "reset" ? "Send reset link" : view === "sign-up" ? "Create account" : "Sign in"}
          </button>
        </form>
        {view === "sign-in" && <button className="mt-4 w-full text-sm font-semibold text-slate-500" onClick={() => { setView("reset"); setError(""); setNotice(""); }} type="button">Forgot your password?</button>}
        {!recoveryRequired && view !== "reset" && <button className="mt-5 w-full text-sm font-semibold text-violet-700" onClick={() => { setView(view === "sign-up" ? "sign-in" : "sign-up"); setError(""); setNotice(""); }} type="button">
          {view === "sign-up" ? "Already have an account? Sign in" : "New to StyleMate? Create an account"}
        </button>}
        {(view === "reset" || view === "recovery") && <button className="mt-5 w-full text-sm font-semibold text-violet-700" onClick={() => { setView("sign-in"); setError(""); setNotice(""); }} type="button">Back to sign in</button>}
      </section>
    </main>
  );
}
