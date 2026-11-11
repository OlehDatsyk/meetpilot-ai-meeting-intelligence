import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, FileAudio, ListChecks, ShieldCheck } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { Logo } from "../components/Logo";
import { Button, ErrorBox, Field, Notice } from "../components/ui";
import { get, post } from "../lib/api";
import { useSession } from "../lib/session";
import type { User } from "../lib/types";

interface TokenOut { access_token: string; user: User }

function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="grid min-h-full lg:grid-cols-[1fr_1.1fr]">
      <div className="hidden flex-col justify-between bg-navy-950 p-10 text-slate-300 lg:flex">
        <Logo dark />
        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight tracking-tight text-white">From recording to decisions and owners, in one place.</h2>
          <ul className="mt-8 space-y-4 text-sm">
            {[
              [FileAudio, "Upload MP3, WAV, M4A, AAC, OGG or FLAC and get a timestamped transcript."],
              [ListChecks, "Summaries, decisions and action items, each linked to the lines that support it."],
              [ShieldCheck, "Owners and deadlines are only filled in when the conversation actually states them."],
            ].map(([Icon, text], i) => {
              const I = Icon as typeof FileAudio;
              return <li key={i} className="flex gap-3"><I className="mt-0.5 size-4 shrink-0 text-indigo-300" />{text as string}</li>;
            })}
          </ul>
        </div>
        <p className="text-xs text-slate-500">Only record and upload meetings you have permission to record and process.</p>
      </div>
      <div className="flex items-center justify-center px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden"><Logo /></div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
          <div className="mt-6">{children}</div>
          {footer && <div className="mt-6 text-sm text-muted">{footer}</div>}
        </div>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<TokenOut>("/api/v1/auth/login", { email, password });
      signIn(r.access_token, r.user);
      navigate((location.state as { from?: string } | null)?.from || "/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Sign in" subtitle="Welcome back to MeetPilot AI."
      footer={<>
        <p>No account? <Link className="font-medium text-accent hover:underline" to="/register">Create one</Link></p>
        <p className="mt-2">Just looking? <Link className="font-medium text-accent hover:underline" to="/demo">Explore the demo meeting</Link> (no account needed).</p>
      </>}>
      <TemporaryServerNotice />
      <form onSubmit={submit} className="space-y-4">
        <ErrorBox error={error} />
        <Field label="Email" htmlFor="email"><input id="email" type="email" autoComplete="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password" htmlFor="password">
          <input id="password" type="password" autoComplete="current-password" required className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <div className="flex justify-end text-sm"><Link to="/forgot-password" className="text-accent hover:underline">Forgot password?</Link></div>
        <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
      </form>
    </AuthShell>
  );
}

function TemporaryServerNotice() {
  const config = useQuery({ queryKey: ["public-config"], queryFn: () => get<{ database_persistent: boolean; password_reset_email: boolean }>("/api/v1/system/config") });
  if (!config.data || config.data.database_persistent) return null;
  return <div className="mb-4"><Notice tone="amber">This is a demo server with temporary storage. Accounts and all data are deleted whenever it restarts or sleeps (after about 15 minutes without visitors).</Notice></div>;
}

export function RegisterPage() {
  const { signIn } = useSession();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<TokenOut>("/api/v1/auth/register", form);
      signIn(r.access_token, r.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Create your account" subtitle="A private workspace is created for you."
      footer={<p>Already have an account? <Link className="font-medium text-accent hover:underline" to="/login">Sign in</Link></p>}>
      <TemporaryServerNotice />
      <form onSubmit={submit} className="space-y-4">
        <ErrorBox error={error} />
        <Field label="Name" htmlFor="name"><input id="name" required maxLength={120} autoComplete="name" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Email" htmlFor="remail"><input id="remail" type="email" required autoComplete="email" className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Password" htmlFor="rpass" hint="At least 10 characters.">
          <input id="rpass" type="password" required minLength={10} autoComplete="new-password" className="input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        <label className="flex items-start gap-2 text-sm text-slate-700">
          <input type="checkbox" className="mt-1" checked={agree} onChange={(e) => setAgree(e.target.checked)} required />
          <span>I have read the <Link to="/privacy" target="_blank" className="text-accent hover:underline">privacy notice</Link> and will only upload recordings I have permission to process.</span>
        </label>
        <Button type="submit" className="w-full" loading={busy} disabled={!agree}>Create account</Button>
      </form>
    </AuthShell>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const config = useQuery({ queryKey: ["public-config"], queryFn: () => get<{ password_reset_email: boolean }>("/api/v1/system/config") });
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await post<{ message: string }>("/api/v1/auth/password-reset/request", { email });
      setDone(r.message);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Reset your password" footer={<Link className="text-accent hover:underline" to="/login">Back to sign in</Link>}>
      {config.data && !config.data.password_reset_email && (
        <div className="mb-4"><Notice tone="amber">This server has no email service configured, so reset links cannot be emailed. Ask the administrator of this MeetPilot AI installation for help.</Notice></div>
      )}
      {done ? (
        <Notice icon={<CheckCircle2 className="mt-0.5 size-4" />}>{done}</Notice>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <ErrorBox error={error} />
          <Field label="Email" htmlFor="femail"><input id="femail" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <Button type="submit" className="w-full" loading={busy}>Send reset link</Button>
        </form>
      )}
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/api/v1/auth/password-reset/confirm", { token, new_password: password });
      setDone(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell title="Choose a new password" footer={<Link className="text-accent hover:underline" to="/login">Back to sign in</Link>}>
      {done ? <Notice icon={<CheckCircle2 className="mt-0.5 size-4" />}>Your password was changed. You can sign in now.</Notice> : (
        <form onSubmit={submit} className="space-y-4">
          {!token && <ErrorBox error="This page needs the link from your reset email." />}
          <ErrorBox error={error} />
          <Field label="New password" htmlFor="npass" hint="At least 10 characters."><input id="npass" type="password" minLength={10} required autoComplete="new-password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>Change password</Button>
        </form>
      )}
    </AuthShell>
  );
}
