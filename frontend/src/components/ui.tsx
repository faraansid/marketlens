import clsx from "clsx";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Info, Minus, Moon, SearchX, Sun } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { isNum, pct, toneOf } from "../lib/format";
import { useTheme } from "../lib/theme";

/** Light / dark mode switch (choice is remembered in the browser). */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button onClick={toggle} className={clsx("btn-ghost", className)} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} mode`}>
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
import type { PatternStatus, Trend } from "../lib/types";

export function Logo({ className }: { className?: string }) {
  return (
    <div className={clsx("flex items-center gap-2.5", className)}>
      <svg viewBox="0 0 32 32" className="h-8 w-8 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="9" className="fill-accent" />
        <path d="M7 21l5.5-5.5 4 4L25 11" fill="none" stroke="var(--accent-fg)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="25" cy="11" r="2.2" fill="var(--accent-fg)" />
      </svg>
      <span className="text-[17px] font-semibold tracking-tight">
        Market<span className="text-accent">Lens</span>
      </span>
    </div>
  );
}

export function Change({ value, className, arrow = true, digits = 2 }: { value: number | null | undefined; className?: string; arrow?: boolean; digits?: number }) {
  const tone = toneOf(value);
  const Icon = tone === "up" ? ArrowUpRight : tone === "down" ? ArrowDownRight : Minus;
  return (
    <span className={clsx("num inline-flex items-center gap-0.5 font-medium", tone === "up" && "text-up", tone === "down" && "text-down", tone === "flat" && "text-muted", className)}>
      {arrow && isNum(value) && <Icon className="h-3.5 w-3.5" aria-hidden />}
      {pct(value, digits)}
      <span className="sr-only">{tone === "up" ? "up" : tone === "down" ? "down" : "unchanged"}</span>
    </span>
  );
}

export function ChangePill({ value }: { value: number | null | undefined }) {
  const tone = toneOf(value);
  return (
    <span className={clsx("num inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold",
      tone === "up" && "bg-up-soft text-up", tone === "down" && "bg-down-soft text-down", tone === "flat" && "bg-surface-2 text-muted")}>
      {pct(value)}
    </span>
  );
}

export function Sparkline({ data, width = 120, height = 36, tone, className, fill = true }: {
  data: number[]; width?: number; height?: number; tone?: "up" | "down" | "flat"; className?: string; fill?: boolean;
}) {
  const gid = useId();
  if (!data || data.length < 2) {
    return <div className={clsx("flex items-center text-[11px] text-muted", className)} style={{ width, height }}>No chart data</div>;
  }
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((v, i) => [i * step, height - 2 - ((v - min) / span) * (height - 4)] as const);
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const t = tone ?? (data[data.length - 1] >= data[0] ? "up" : "down");
  const color = t === "up" ? "var(--up)" : t === "down" ? "var(--down)" : "var(--muted)";
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} className={className} preserveAspectRatio="none" aria-hidden>
      {fill && (
        <>
          <defs>
            <linearGradient id={gid} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor={color} stopOpacity="0.22" />
              <stop offset="1" stopColor={color} stopOpacity="0" />
            </linearGradient>
          </defs>
          <path d={`${d} L${width},${height} L0,${height} Z`} fill={`url(#${gid})`} />
        </>
      )}
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

/** Accessible tooltip explaining a metric (hover or keyboard focus). */
export function InfoTip({ text, children, className }: { text: string; children?: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className={clsx("relative inline-flex items-center", className)}
      onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      <button type="button" aria-describedby={id} aria-label="More info" onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        className="ml-1 inline-flex text-muted hover:text-fg-2">
        <Info className="h-3.5 w-3.5" />
      </button>
      <span id={id} role="tooltip"
        className={clsx("pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 w-64 -translate-x-1/2 rounded-lg border border-line bg-bg-elev px-3 py-2 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-fg-2 shadow-xl transition-opacity",
          open ? "opacity-100" : "opacity-0")}>
        {text}
      </span>
    </span>
  );
}

const TREND_STYLE: Record<Trend, string> = {
  "Strong Uptrend": "bg-up-soft text-up ring-up/30",
  Uptrend: "bg-up-soft/60 text-up ring-up/20",
  Neutral: "bg-surface-2 text-muted ring-line",
  Downtrend: "bg-down-soft/60 text-down ring-down/20",
  "Strong Downtrend": "bg-down-soft text-down ring-down/30",
};

export function TrendBadge({ trend, className }: { trend: Trend | null | undefined; className?: string }) {
  if (!trend) return <span className="text-muted">—</span>;
  return (
    <span className={clsx("inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", TREND_STYLE[trend], className)}>
      {trend}
    </span>
  );
}

const STATUS_STYLE: Record<PatternStatus, { cls: string; label: string }> = {
  confirmed: { cls: "bg-up-soft text-up ring-up/30", label: "Confirmed breakout" },
  potential: { cls: "bg-warn-soft text-warn ring-warn/30", label: "Potential breakout" },
  failed: { cls: "bg-down-soft text-down ring-down/30", label: "Failed breakout" },
  forming: { cls: "bg-accent-soft text-accent ring-accent/30", label: "Forming" },
  active: { cls: "bg-surface-2 text-fg-2 ring-line", label: "Active" },
};

export function StatusBadge({ status, short }: { status: PatternStatus; short?: boolean }) {
  const s = STATUS_STYLE[status] ?? STATUS_STYLE.active;
  return (
    <span className={clsx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset", s.cls)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {short ? status[0].toUpperCase() + status.slice(1) : s.label}
    </span>
  );
}

export function PatternTag({ label }: { label: string }) {
  return <span className="inline-flex items-center whitespace-nowrap rounded-md bg-accent-soft px-2 py-0.5 text-xs font-semibold text-accent">{label}</span>;
}

export function ConfidenceBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  const color = v >= 75 ? "var(--up)" : v >= 55 ? "var(--accent)" : "var(--warn)";
  return (
    <div className="flex items-center gap-2" title={`Pattern strength score ${v.toFixed(0)}/100`}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuenow={v} aria-valuemin={0} aria-valuemax={100} aria-label="Confidence score">
        <div className="h-full rounded-full" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="num w-8 text-right text-xs font-semibold">{v.toFixed(0)}</span>
    </div>
  );
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-surface-2 p-3 text-muted"><SearchX className="h-5 w-5" /></div>
      <p className="font-medium">{title}</p>
      {body && <p className="mt-1 max-w-md text-sm text-muted">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center" role="alert">
      <div className="mb-3 rounded-full bg-down-soft p-3 text-down"><AlertTriangle className="h-5 w-5" /></div>
      <p className="font-medium">Couldn't load this data</p>
      <p className="mt-1 max-w-md text-sm text-muted">{message}</p>
      {onRetry && <button onClick={onRetry} className="btn-secondary mt-4">Try again</button>}
    </div>
  );
}

export function Disclaimer({ className }: { className?: string }) {
  return (
    <p className={clsx("flex items-start gap-2 text-xs leading-relaxed text-muted", className)}>
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
      Technical patterns and signals are analytical indicators, not guaranteed predictions or investment advice.
      Market data is sourced from third-party providers and may be delayed.
    </p>
  );
}

export function Segmented<T extends string>({ options, value, onChange, size = "md", label }: {
  options: { value: T; label: ReactNode; count?: number }[]; value: T; onChange: (v: T) => void; size?: "sm" | "md"; label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} onClick={() => onChange(o.value)}
          className={clsx("flex items-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-colors",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
            o.value === value ? "bg-surface text-fg shadow-sm ring-1 ring-line" : "text-muted hover:text-fg")}>
          {o.label}
          {o.count !== undefined && <span className="num rounded bg-bg/60 px-1 text-[10px] text-muted">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}
