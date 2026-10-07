import clsx from "clsx";
import { ChevronDown, KeyRound, LogOut, Menu, RefreshCw, X } from "lucide-react";
import { Suspense, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { ChangePasswordDialog } from "../components/ChangePasswordDialog";
import { Logo, Skeleton, ThemeToggle } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateTime, timeAgo } from "../lib/format";
import { useMarketStatus } from "../lib/queries";
import { modulesFor } from "./modules";

function MarketStatusPill() {
  const { data } = useMarketStatus();
  if (!data) return <Skeleton className="h-7 w-32" />;
  const state = data.market.state;
  return (
    <div className="flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium" title={data.market.label}>
      <span className="relative flex h-2 w-2">
        {state === "open" && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-up opacity-60" />}
        <span className={clsx("relative inline-flex h-2 w-2 rounded-full", state === "open" ? "bg-up" : state === "pre_open" ? "bg-warn" : "bg-muted")} />
      </span>
      <span className="hidden sm:inline">{data.market.label}</span>
      <span className="sm:hidden">{state === "open" ? "Open" : "Closed"}</span>
    </div>
  );
}

function LastUpdated() {
  const { data } = useMarketStatus();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!data) return null;
  const failed = data.lastRun && data.lastRun.status === "failed";

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api<{ message: string }>("/api/jobs/refresh", { method: "POST" });
      toast.success("Refresh started", { description: r.message });
      setTimeout(() => qc.invalidateQueries({ queryKey: ["market-status"] }), 1500);
    } catch (e) {
      toast.error("Couldn't start refresh", { description: (e as Error).message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="hidden items-center gap-2 text-xs text-muted md:flex">
      <span title={`Last successful update: ${dateTime(data.lastSuccessfulUpdate)}\nNext scheduled: ${dateTime(data.nextScheduledRun)}`}>
        {data.isRefreshing ? (
          <span className="inline-flex items-center gap-1.5 text-accent"><RefreshCw className="h-3 w-3 animate-spin" />Updating data…</span>
        ) : (
          <>Data updated <span className="font-medium text-fg-2">{timeAgo(data.lastSuccessfulUpdate)}</span></>
        )}
      </span>
      {failed && !data.isRefreshing && (
        <span className="rounded bg-warn-soft px-1.5 py-0.5 text-warn" title={data.lastRun?.error ?? undefined}>
          Latest update failed · showing last good data
        </span>
      )}
      {user?.isAdmin && (
        <button onClick={refresh} disabled={busy || data.isRefreshing} className="btn-ghost px-1.5 py-1" aria-label="Refresh market data now" title="Refresh market data now (owner)">
          <RefreshCw className={clsx("h-3.5 w-3.5", busy && "animate-spin")} />
        </button>
      )}
    </div>
  );
}

function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const [changingPw, setChangingPw] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  if (!user) return null;
  const name = user.fullName || user.username || "User";
  const initials = name.split(/[\s@._]/).filter(Boolean).slice(0, 2).map((s) => s[0]!.toUpperCase()).join("");
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="flex items-center gap-2 rounded-lg px-1.5 py-1 hover:bg-surface-2" aria-haspopup="menu" aria-expanded={open}>
        <span className="grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent">{initials}</span>
        <ChevronDown className="hidden h-4 w-4 text-muted sm:block" />
      </button>
      {open && (
        <div role="menu" className="fade-in absolute right-0 z-50 mt-2 w-60 rounded-xl border border-line bg-bg-elev p-1.5 shadow-2xl">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{name}</p>
            {user.username && <p className="truncate text-xs text-muted">@{user.username}</p>}
            {user.isAdmin && <span className="mt-1 inline-block rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold text-accent">OWNER</span>}
          </div>
          <div className="my-1 h-px bg-line" />
          <button role="menuitem" onClick={() => { setOpen(false); setChangingPw(true); }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-fg-2 hover:bg-surface-2">
            <KeyRound className="h-4 w-4" /> Change password
          </button>
          <button role="menuitem" onClick={async () => { await signOut(); toast("Signed out"); }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-fg-2 hover:bg-surface-2">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
      {changingPw && <ChangePasswordDialog onClose={() => setChangingPw(false)} />}
    </div>
  );
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-16 items-center px-5"><Logo /></div>
      <nav className="flex-1 space-y-1 px-3 py-2" aria-label="Main">
        {(["Analysis", "Administration"] as const).map((section) => {
          const items = modulesFor(!!user?.isAdmin).filter((m) => (m.section ?? "Analysis") === section);
          if (!items.length) return null;
          return (
            <div key={section} className="space-y-1 pb-3">
              <p className="px-3 pb-2 pt-1 text-[10px] font-semibold uppercase tracking-widest text-muted">{section}</p>
              {items.map((m) => (
                <NavLink key={m.path} to={`/app/${m.path}`} onClick={onNavigate}
                  className={({ isActive }) => clsx("group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive ? "bg-accent-soft text-accent" : "text-fg-2 hover:bg-surface-2 hover:text-fg")}>
                  <m.icon className="h-4.5 w-4.5 shrink-0" />
                  <span>{m.label}</span>
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
      <div className="space-y-3 border-t border-line p-4">
        {user && (
          <div className="flex items-center gap-2.5 rounded-lg bg-surface-2 p-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
              {(user.fullName || user.username || "U")[0]!.toUpperCase()}
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{user.fullName || user.username}</p>
              {user.username && <p className="truncate text-xs text-muted">@{user.username}</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setMobileOpen(false), [loc.pathname]);

  return (
    <div className="flex min-h-full">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-bg-elev lg:block">
        <SidebarContent />
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="fade-in absolute inset-y-0 left-0 w-72 border-r border-line bg-bg-elev">
            <button className="btn-ghost absolute right-2 top-3" onClick={() => setMobileOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur-md sm:px-6">
          <button className="btn-ghost -ml-2 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
          <div className="lg:hidden"><Logo className="[&_span]:hidden sm:[&_span]:inline" /></div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <LastUpdated />
            <MarketStatusPill />
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">
          <Suspense fallback={<div className="space-y-4"><Skeleton className="h-8 w-48" /><Skeleton className="h-64 w-full" /></div>}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
