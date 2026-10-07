import { ArrowLeft, Eye, EyeOff, Loader2, Lock, User as UserIcon } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Logo, ThemeToggle } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden px-4 py-12">
      <div className="grid-backdrop pointer-events-none absolute inset-0 opacity-50" aria-hidden />
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="relative w-full max-w-[420px]">
        <Link to="/" className="mb-8 flex justify-center"><Logo /></Link>
        <div className="card fade-in p-6 sm:p-8">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}

function FieldError({ id, msg }: { id: string; msg?: string }) {
  if (!msg) return null;
  return <p id={id} className="mt-1.5 text-xs text-down">{msg}</p>;
}

function PasswordInput({ id, value, onChange, invalid, describedBy, autoComplete }: {
  id: string; value: string; onChange: (v: string) => void; invalid?: boolean; describedBy?: string; autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      <input id={id} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)}
        className="input pl-9 pr-10" autoComplete={autoComplete} aria-invalid={invalid || undefined} aria-describedby={describedBy} />
      <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-fg"
        aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}>
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export function SignInPage() {
  const { user, signIn } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from || "/app/market";
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [errors, setErrors] = useState<{ identifier?: string; password?: string; form?: string }>({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs: typeof errors = {};
    if (!identifier.trim()) errs.identifier = "Enter your username.";
    if (!password) errs.password = "Enter your password.";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    try {
      const u = await signIn(identifier.trim(), password, remember);
      toast.success(`Welcome back${u.fullName ? `, ${u.fullName.split(" ")[0]}` : ""}`);
      nav(from, { replace: true });
    } catch (err) {
      setErrors({ form: err instanceof ApiError ? err.message : "Sign in failed. Please try again." });
      setPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in to MarketLens" subtitle="Analyse Indian equities and technical setups.">
      <form onSubmit={submit} noValidate className="space-y-4">
        {errors.form && <div role="alert" className="rounded-lg border border-down/30 bg-down-soft px-3 py-2.5 text-sm text-down">{errors.form}</div>}
        <div>
          <label htmlFor="identifier" className="label">Username</label>
          <div className="relative">
            <UserIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input id="identifier" value={identifier} onChange={(e) => setIdentifier(e.target.value)} className="input pl-9"
              autoComplete="username" autoFocus aria-invalid={!!errors.identifier || undefined} aria-describedby="identifier-err" />
          </div>
          <FieldError id="identifier-err" msg={errors.identifier} />
        </div>
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="password" className="label mb-0">Password</label>
            <Link to="/change-password" className="text-xs font-medium text-accent hover:underline">Change password</Link>
          </div>
          <PasswordInput id="password" value={password} onChange={setPassword} invalid={!!errors.password} describedBy="password-err" autoComplete="current-password" />
          <FieldError id="password-err" msg={errors.password} />
        </div>
        <label className="flex cursor-pointer select-none items-center gap-2 text-sm text-fg-2">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 rounded border-line accent-[var(--accent)]" />
          Remember me for 30 days
        </label>
        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Sign In
        </button>
      </form>
    </AuthShell>
  );
}

/** Change any account's password by entering the master password. */
export function ChangePasswordPage() {
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [master, setMaster] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim()) return setErr("Enter the username whose password you want to change.");
    if (!master) return setErr("Enter the master password.");
    if (!pw) return setErr("Enter a new password.");
    if (pw !== pw2) return setErr("New passwords don't match.");
    setErr(undefined);
    setBusy(true);
    try {
      await api("/api/auth/change-password", { method: "POST", json: { username: username.trim(), masterPassword: master, newPassword: pw } });
      toast.success("Password changed", { description: "Sign in with your new password." });
      nav("/signin", { replace: true });
    } catch (e2) {
      setErr((e2 as Error).message);
      setMaster("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Change password" subtitle="Use the master password to set a new password for an account.">
      <form onSubmit={submit} noValidate className="space-y-4">
        {err && <div role="alert" className="rounded-lg border border-down/30 bg-down-soft px-3 py-2.5 text-sm text-down">{err}</div>}
        <div>
          <label htmlFor="cp-username" className="label">Username</label>
          <div className="relative">
            <UserIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input id="cp-username" value={username} onChange={(e) => setUsername(e.target.value)} className="input pl-9" autoComplete="username" autoFocus />
          </div>
        </div>
        <div>
          <label htmlFor="cp-master" className="label">Master password</label>
          <PasswordInput id="cp-master" value={master} onChange={setMaster} autoComplete="off" />
        </div>
        <div>
          <label htmlFor="cp-pw" className="label">New password</label>
          <PasswordInput id="cp-pw" value={pw} onChange={setPw} autoComplete="new-password" />
        </div>
        <div>
          <label htmlFor="cp-pw2" className="label">Confirm new password</label>
          <PasswordInput id="cp-pw2" value={pw2} onChange={setPw2} autoComplete="new-password" />
        </div>
        <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} Change password
        </button>
        <Link to="/signin" className="flex items-center justify-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Back to sign in</Link>
      </form>
    </AuthShell>
  );
}

