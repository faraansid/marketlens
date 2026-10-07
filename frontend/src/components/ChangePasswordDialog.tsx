import { Eye, EyeOff, KeyRound, Loader2, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { api } from "../lib/api";

function PwField({ id, label, value, onChange, autoComplete, autoFocus }: {
  id: string; label: string; value: string; onChange: (v: string) => void; autoComplete: string; autoFocus?: boolean;
}) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      <div className="relative">
        <input id={id} type={show ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)}
          className="input pr-10" autoComplete={autoComplete} autoFocus={autoFocus} />
        <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-fg"
          aria-label={show ? "Hide password" : "Show password"}>
          {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

/** Lets the signed-in user change their own password. */
export function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [err, setErr] = useState<string>();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!current) return setErr("Enter your current password.");
    if (!pw) return setErr("Enter a new password.");
    if (pw !== pw2) return setErr("New passwords don't match.");
    setErr(undefined);
    setBusy(true);
    try {
      await api("/api/auth/me/password", { method: "POST", json: { currentPassword: current, newPassword: pw } });
      toast.success("Password changed", { description: "Other devices have been signed out." });
      onClose();
    } catch (e2) {
      setErr((e2 as Error).message);
      setCurrent("");
    } finally {
      setBusy(false);
    }
  };

  // Portal to <body>: the sticky header uses backdrop-filter, which would
  // otherwise become the containing block for this fixed overlay.
  return createPortal(
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="cpw-title">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <form onSubmit={submit} noValidate className="card fade-in relative w-full max-w-md space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h2 id="cpw-title" className="flex items-center gap-2 font-semibold"><KeyRound className="h-4 w-4 text-accent" /> Change password</h2>
          <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        {err && <div role="alert" className="rounded-lg border border-down/30 bg-down-soft px-3 py-2 text-sm text-down">{err}</div>}
        <PwField id="cpw-current" label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" autoFocus />
        <PwField id="cpw-new" label="New password" value={pw} onChange={setPw} autoComplete="new-password" />
        <PwField id="cpw-new2" label="Confirm new password" value={pw2} onChange={setPw2} autoComplete="new-password" />
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="btn-secondary">Cancel</button>
          <button type="submit" disabled={busy} className="btn-primary">{busy && <Loader2 className="h-4 w-4 animate-spin" />} Change password</button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
