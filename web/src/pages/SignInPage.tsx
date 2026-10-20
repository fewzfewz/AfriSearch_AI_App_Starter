// Sign in, create an account, reset a password (Supabase Auth).
import { ArrowLeft, MailCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Logo } from "../components/ui";
import { useAuth } from "../lib/auth";

type Mode = "signin" | "signup" | "reset";

const inputClass = "mt-1.5 w-full rounded-lg border border-ink-300 bg-white px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/10 dark:border-ink-700 dark:bg-ink-900";

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5a5.6 5.6 0 0 1-2.4 3.6v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8Z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3c-1.1.7-2.5 1.2-4.1 1.2-3.1 0-5.8-2.1-6.7-5H1.3v3.1A12 12 0 0 0 12 24Z" />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6H1.3a12 12 0 0 0 0 10.8l4-3.1Z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.3.6 4.6 1.8l3.4-3.4A11.6 11.6 0 0 0 12 0 12 12 0 0 0 1.3 6.6l4 3.1c.9-2.9 3.6-4.9 6.7-4.9Z" />
    </svg>
  );
}

function NewPasswordForm() {
  const { supabase, finishRecovery } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    const { error: failed } = await supabase!.auth.updateUser({ password });
    setBusy(false);
    if (failed) return setError(failed.message);
    finishRecovery();
    navigate("/app");
  };
  return (
    <form onSubmit={submit} className="space-y-4">
      <h1 className="font-display text-2xl font-semibold">Choose a new password</h1>
      {error && <Alert tone="red">{error}</Alert>}
      <label className="block text-sm font-medium">New password
        <input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
      </label>
      <Button type="submit" variant="primary" className="w-full" loading={busy}>Save password</Button>
    </form>
  );
}

export function SignInPage() {
  const { config, signedIn, supabase, recovering } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>(params.get("mode") === "signup" ? "signup" : "signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError(null);
    setSent(null);
  }, [mode]);

  if (config?.auth === "none") return <Navigate to="/app" replace />;
  if (signedIn && !recovering) return <Navigate to="/app" replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "signin") {
        const { error: failed } = await supabase.auth.signInWithPassword({ email, password });
        if (failed) throw failed;
        navigate("/app");
      } else if (mode === "signup") {
        const { data, error: failed } = await supabase.auth.signUp({
          email, password,
          options: {
            data: { full_name: name.trim(), accepted_terms_at: new Date().toISOString() },  // record of consent
            emailRedirectTo: `${window.location.origin}/app`,
          },
        });
        if (failed) throw failed;
        if (data.session) navigate("/app");
        else setSent(`We sent a confirmation link to ${email}. Open it to finish creating your account.`);
      } else {
        const { error: failed } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${window.location.origin}/signin` });
        if (failed) throw failed;
        setSent(`If an account uses ${email}, we sent it a link to reset the password.`);
      }
    } catch (failed) {
      setError((failed as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const titles: Record<Mode, [string, string]> = {
    signin: ["Welcome back", "Sign in to your AfriSearch account."],
    signup: ["Create your account", "Start asking questions about your documents."],
    reset: ["Reset your password", "We'll email you a link to choose a new one."],
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="flex flex-col px-6 py-8 sm:px-12">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-ink-500 hover:text-ink-900 dark:hover:text-white"><ArrowLeft className="h-4 w-4" /> Home</Link>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-10">
          <Logo className="mb-8" />
          {recovering ? <NewPasswordForm /> : sent ? (
            <div className="text-center">
              <MailCheck className="mx-auto h-10 w-10 text-brand-700" />
              <h1 className="mt-4 font-display text-2xl font-semibold">Check your email</h1>
              <p className="mt-2 text-ink-600 dark:text-ink-400">{sent}</p>
              <Button variant="ghost" className="mt-6" onClick={() => setMode("signin")}>Back to sign in</Button>
            </div>
          ) : (
            <>
              <h1 className="font-display text-2xl font-semibold">{titles[mode][0]}</h1>
              <p className="mt-1.5 text-sm text-ink-500">{titles[mode][1]}</p>
              {!supabase && <div className="mt-6"><Alert tone="red">Sign-in isn't configured on this server (SUPABASE_URL / SUPABASE_ANON_KEY).</Alert></div>}

              {mode !== "reset" && config?.auth_providers.includes("google") && (
                <>
                  <Button className="mt-6 w-full" icon={<GoogleIcon />} onClick={() => supabase?.auth.signInWithOAuth({ provider: "google", options: { redirectTo: `${window.location.origin}/app` } })}>
                    Continue with Google
                  </Button>
                  <div className="my-6 flex items-center gap-3 text-xs text-ink-400"><span className="h-px flex-1 bg-ink-200 dark:bg-ink-800" />or<span className="h-px flex-1 bg-ink-200 dark:bg-ink-800" /></div>
                </>
              )}

              <form onSubmit={submit} className="mt-6 space-y-4">
                {error && <Alert tone="red">{error}</Alert>}
                {mode === "signup" && (
                  <label className="block text-sm font-medium">Your name
                    <input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} className={inputClass} />
                  </label>
                )}
                <label className="block text-sm font-medium">Email
                  <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
                </label>
                {mode !== "reset" && (
                  <label className="block text-sm font-medium">
                    <span className="flex justify-between">
                      Password
                      {mode === "signin" && <button type="button" onClick={() => setMode("reset")} className="font-normal text-brand-700 hover:underline dark:text-brand-400">Forgot password?</button>}
                    </span>
                    <input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} minLength={mode === "signup" ? 8 : undefined}
                      required value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
                    {mode === "signup" && <span className="mt-1 block text-xs font-normal text-ink-500">At least 8 characters.</span>}
                  </label>
                )}
                {mode === "signup" && (
                  <label className="flex items-start gap-2.5 text-sm text-ink-600 dark:text-ink-400">
                    <input type="checkbox" required checked={agreed} onChange={(e) => setAgreed(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-ink-300 accent-brand-700" />
                    <span>
                      I agree to the <Link to="/terms" target="_blank" className="font-medium text-brand-700 underline dark:text-brand-400">Terms of use</Link> and
                      the <Link to="/privacy" target="_blank" className="font-medium text-brand-700 underline dark:text-brand-400">Privacy notice</Link>.
                    </span>
                  </label>
                )}
                <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy} disabled={!supabase || (mode === "signup" && !agreed)}>
                  {mode === "signin" ? "Sign in" : mode === "signup" ? "Create account" : "Send reset link"}
                </Button>
              </form>
              <p className="mt-6 text-center text-sm text-ink-500">
                {mode === "signin" ? (
                  <>New to AfriSearch? <button type="button" onClick={() => setMode("signup")} className="font-medium text-brand-700 hover:underline dark:text-brand-400">Create an account</button></>
                ) : (
                  <>Already have an account? <button type="button" onClick={() => setMode("signin")} className="font-medium text-brand-700 hover:underline dark:text-brand-400">Sign in</button></>
                )}
              </p>
            </>
          )}
        </div>
      </div>
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-800 via-brand-700 to-amber-700 lg:block">
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <p className="text-3xl font-semibold leading-snug">Ask in Amharic, find the answer in an English report, and see the exact page it came from.</p>
          <p className="mt-4 text-white/75">AfriSearch reads PDFs, text files and scans in 94 languages.</p>
        </div>
      </div>
    </div>
  );
}
