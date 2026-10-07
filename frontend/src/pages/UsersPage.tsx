import clsx from "clsx";
import { Eye, EyeOff, Loader2, Trash2, UserPlus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { EmptyState, ErrorState, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { dateTime } from "../lib/format";
import type { ManagedUser } from "../lib/types";

function AddUserForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ username: "", fullName: "", password: "" });
  const [show, setShow] = useState(false);
  const [err, setErr] = useState<string>();
  const create = useMutation({
    mutationFn: () => api<ManagedUser>("/api/users", { method: "POST", json: form }),
    onSuccess: (u) => {
      toast.success("User added", { description: `${u.username} can now sign in.` });
      qc.invalidateQueries({ queryKey: ["users"] });
      onDone();
    },
    onError: (e) => setErr((e as Error).message),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!/^[A-Za-z0-9._-]{3,32}$/.test(form.username)) return setErr("Username: 3–32 characters, letters, numbers, . _ -");
    if (!form.password) return setErr("Enter a password.");
    setErr(undefined);
    create.mutate();
  };
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <form onSubmit={submit} noValidate className="card fade-in space-y-4 p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Add a user</h2>
        <button type="button" onClick={onDone} className="btn-ghost p-1.5" aria-label="Close"><X className="h-4 w-4" /></button>
      </div>
      {err && <div role="alert" className="rounded-lg border border-down/30 bg-down-soft px-3 py-2 text-sm text-down">{err}</div>}
      <div className="grid gap-4 sm:grid-cols-2">
        <div><label htmlFor="u-username" className="label">Username</label><input id="u-username" className="input" value={form.username} onChange={set("username")} autoComplete="off" autoFocus /></div>
        <div><label htmlFor="u-name" className="label">Full name <span className="text-muted">(optional)</span></label><input id="u-name" className="input" value={form.fullName} onChange={set("fullName")} autoComplete="off" /></div>
        <div>
          <label htmlFor="u-pw" className="label">Initial password</label>
          <div className="relative">
            <input id="u-pw" type={show ? "text" : "password"} className="input pr-10" value={form.password} onChange={set("password")} autoComplete="new-password" />
            <button type="button" onClick={() => setShow((s) => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted hover:text-fg" aria-label={show ? "Hide password" : "Show password"}>
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>
      <p className="text-xs text-muted">Share the initial password with the user privately. It can be changed any time from “Change password” on the sign-in page using the master password.</p>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onDone} className="btn-secondary">Cancel</button>
        <button type="submit" disabled={create.isPending} className="btn-primary">{create.isPending && <Loader2 className="h-4 w-4 animate-spin" />} Add user</button>
      </div>
    </form>
  );
}

export default function UsersPage() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["users"], queryFn: () => api<ManagedUser[]>("/api/users") });

  const toggle = useMutation({
    mutationFn: (u: ManagedUser) => api<ManagedUser>(`/api/users/${u.id}`, { method: "PATCH", json: { isActive: !u.isActive } }),
    onSuccess: (u) => { toast.success(u.isActive ? `${u.username} reactivated` : `${u.username} deactivated and signed out`); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: (u: ManagedUser) => api(`/api/users/${u.id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("User removed"); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted">Only the owner can add or remove people who can sign in.</p>
        </div>
        {!adding && <button onClick={() => setAdding(true)} className="btn-primary"><UserPlus className="h-4 w-4" /> Add user</button>}
      </div>

      {adding && <AddUserForm onDone={() => setAdding(false)} />}

      <div className="card overflow-x-auto">
        {error ? <ErrorState message={(error as Error).message} onRetry={() => refetch()} /> : (
          <table className="w-full min-w-[720px] text-sm">
            <thead className="border-b border-line bg-surface-2/70">
              <tr><th className="th">User</th><th className="th">Role</th><th className="th">Status</th><th className="th">Last sign-in</th><th className="th text-right">Actions</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {isLoading && Array.from({ length: 3 }).map((_, i) => <tr key={i}><td className="td" colSpan={5}><Skeleton className="h-5 w-full" /></td></tr>)}
              {data?.map((u) => (
                <tr key={u.id} className={clsx(!u.isActive && "opacity-60")}>
                  <td className="td"><p className="font-medium">{u.username}</p>{u.fullName && <p className="text-xs text-muted">{u.fullName}</p>}</td>
                  <td className="td">{u.isOwner
                    ? <span className="rounded bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">Owner</span>
                    : <span className="rounded bg-surface-2 px-2 py-0.5 text-xs font-medium text-fg-2">Member</span>}</td>
                  <td className="td">{u.isActive
                    ? <span className="text-xs font-medium text-up">Active</span>
                    : <span className="text-xs font-medium text-muted">Deactivated</span>}</td>
                  <td className="td text-xs text-muted">{u.lastLoginAt ? dateTime(u.lastLoginAt) : "Never"}</td>
                  <td className="td text-right">
                    {!u.isOwner && (
                      <div className="inline-flex gap-1.5">
                        <button className="btn-secondary px-2.5 py-1 text-xs" disabled={toggle.isPending} onClick={() => toggle.mutate(u)}>
                          {u.isActive ? "Deactivate" : "Reactivate"}
                        </button>
                        <button className="btn-ghost px-2 py-1 text-down hover:bg-down-soft hover:text-down" aria-label={`Remove ${u.username}`} disabled={remove.isPending}
                          onClick={() => { if (window.confirm(`Remove ${u.username}? They will no longer be able to sign in.`)) remove.mutate(u); }}>
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data && data.length <= 1 && !adding && (
          <EmptyState title="No other users yet" body="Add people who should be able to sign in to MarketLens." />
        )}
      </div>
    </div>
  );
}
