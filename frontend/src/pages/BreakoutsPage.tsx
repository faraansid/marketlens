import clsx from "clsx";
import { ChevronLeft, ChevronRight, LayoutGrid, List, RotateCcw, Search, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { DetectionCard, METRIC_TIPS } from "../components/DetectionCard";
import { Change, ConfidenceBar, Disclaimer, EmptyState, ErrorState, InfoTip, PatternTag, Skeleton, Sparkline, StatusBadge, TrendBadge } from "../components/ui";
import { mcap, price, ratio, timeAgo } from "../lib/format";
import { usePatterns, usePatternSummary } from "../lib/queries";
import type { Detection } from "../lib/types";

const PATTERN_TABS = [
  { value: "", label: "All" },
  { value: "vcp", label: "VCP" },
  { value: "falling_wedge", label: "Falling Wedge" },
  { value: "breakout", label: "Breakout" },
  { value: "uptrend", label: "Uptrend" },
  { value: "downtrend", label: "Downtrend" },
] as const;

const STATUS_TABS = [
  { value: "", label: "Any status" },
  { value: "potential", label: "Potential" },
  { value: "confirmed", label: "Confirmed" },
  { value: "failed", label: "Failed" },
  { value: "forming", label: "Forming" },
];

const MCAP_BUCKETS = [
  { value: "", label: "Any market cap", min: undefined, max: undefined },
  { value: "large", label: "Large cap (≥ ₹1 L Cr)", min: 100000, max: undefined },
  { value: "mid", label: "Mid cap (₹20k–1 L Cr)", min: 20000, max: 100000 },
  { value: "small", label: "Small cap (₹5k–20k Cr)", min: 5000, max: 20000 },
  { value: "micro", label: "Micro cap (₹1k–5k Cr)", min: 1000, max: 5000 },
];

const SORTS = [
  { value: "confidence", label: "Confidence" },
  { value: "volumeRatio", label: "Volume expansion" },
  { value: "marketCap", label: "Market cap" },
  { value: "oneDayChange", label: "1D change" },
  { value: "price", label: "Price" },
];

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function DetectionTable({ items }: { items: Detection[] }) {
  const nav = useNavigate();
  return (
    <div className="card overflow-x-auto">
      <table className="w-full min-w-[1100px] text-sm">
        <thead className="border-b border-line bg-surface-2/70">
          <tr>
            <th className="th">Stock</th><th className="th">Pattern</th><th className="th">Status</th>
            <th className="th w-40"><InfoTip text={METRIC_TIPS.confidence}>Confidence</InfoTip></th>
            <th className="th text-right">Price</th><th className="th text-right">1D</th>
            <th className="th text-right">Support</th><th className="th text-right">Resistance</th><th className="th text-right">Breakout</th>
            <th className="th text-right"><InfoTip text={METRIC_TIPS.volumeRatio}>Vol ratio</InfoTip></th>
            <th className="th text-right">Mkt cap</th><th className="th">Chart</th><th className="th">Detected</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((d) => (
            <tr key={d.id} className="cursor-pointer hover:bg-surface-2/70" onClick={() => nav(`/app/stock/${d.symbol}`)}>
              <td className="td">
                <Link to={`/app/stock/${d.symbol}`} onClick={(e) => e.stopPropagation()} className="num font-semibold hover:text-accent">{d.symbol}</Link>
                <p className="max-w-[200px] truncate text-xs text-muted">{d.name}</p>
              </td>
              <td className="td"><PatternTag label={d.patternLabel} /></td>
              <td className="td">{d.status === "active" ? <TrendBadge trend={d.trend} /> : <StatusBadge status={d.status} short />}</td>
              <td className="td"><ConfidenceBar value={d.confidenceScore} /></td>
              <td className="td num text-right">{price(d.currentPrice)}</td>
              <td className="td text-right"><Change value={d.oneDayChange} arrow={false} /></td>
              <td className="td num text-right text-fg-2">{price(d.support)}</td>
              <td className="td num text-right text-fg-2">{price(d.resistance)}</td>
              <td className="td num text-right text-fg-2">{price(d.breakoutLevel)}</td>
              <td className={clsx("td num text-right", (d.volumeRatio ?? 0) >= 1.5 && "text-up")}>{ratio(d.volumeRatio)}</td>
              <td className="td num text-right text-fg-2">{mcap(d.marketCap)}</td>
              <td className="td"><Sparkline data={d.chart} width={110} height={30} fill={false} /></td>
              <td className="td text-xs text-muted">{timeAgo(d.detectedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BreakoutsPage() {
  const [params, setParams] = useSearchParams();
  const get = (k: string) => params.get(k) || "";
  const update = (patch: Record<string, string | null>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v === null || v === "" ? next.delete(k) : next.set(k, v);
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };

  const pattern = get("pattern");
  const status = get("status");
  const view = get("view") || "cards";
  const page = Math.max(1, Number(get("page")) || 1);
  const minConf = Number(get("minConf")) || 0;
  const minVr = Number(get("minVr")) || 0;
  const bucket = MCAP_BUCKETS.find((b) => b.value === get("mcap")) ?? MCAP_BUCKETS[0];
  const [search, setSearch] = useState(get("q"));
  const debounced = useDebounced(search.trim(), 300);
  const [showFilters, setShowFilters] = useState(false);
  const [minPrice, setMinPrice] = useState(get("minPrice"));
  const [maxPrice, setMaxPrice] = useState(get("maxPrice"));
  const dMin = useDebounced(minPrice, 400), dMax = useDebounced(maxPrice, 400);

  useEffect(() => {
    if (get("q") !== debounced || get("minPrice") !== dMin || get("maxPrice") !== dMax) {
      update({ q: debounced || null, minPrice: dMin || null, maxPrice: dMax || null });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, dMin, dMax]);

  const isTrendTab = pattern === "uptrend" || pattern === "downtrend";
  const query = useMemo(() => ({
    pattern: pattern || undefined,
    status: isTrendTab ? undefined : status || undefined,
    minConfidence: minConf || undefined,
    minVolumeRatio: minVr || undefined,
    trend: get("trend") || undefined,
    minMarketCapCr: bucket.min,
    maxMarketCapCr: bucket.max,
    minPrice: Number(get("minPrice")) || undefined,
    maxPrice: Number(get("maxPrice")) || undefined,
    search: get("q") || undefined,
    sort: get("sort") || "confidence",
    order: "desc" as const,
    page,
    pageSize: 24,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [params]);

  const { data, isLoading, isFetching, error, refetch } = usePatterns(query);
  const summary = usePatternSummary();
  const counts = summary.data ?? {};
  const allCount = Object.values(counts).reduce((a, c) => a + c.total, 0);
  const activeFilters = [minConf, minVr, get("trend"), bucket.value, get("minPrice"), get("maxPrice"), get("q")].filter(Boolean).length;

  const reset = () => {
    setSearch(""); setMinPrice(""); setMaxPrice("");
    setParams(new URLSearchParams(pattern ? { pattern } : {}), { replace: true });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Breakouts</h1>
          <p className="text-sm text-muted">Stocks matching technical patterns and breakout setups across the eligible universe.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden text-xs text-muted sm:inline">Analytical signals · scanned server-side every 30 min</span>
          <div className="inline-flex rounded-lg border border-line bg-surface-2 p-0.5" role="group" aria-label="View mode">
            <button onClick={() => update({ view: null }, false)} className={clsx("rounded-md p-1.5", view === "cards" ? "bg-surface text-fg shadow-sm" : "text-muted")} aria-label="Card view" aria-pressed={view === "cards"}><LayoutGrid className="h-4 w-4" /></button>
            <button onClick={() => update({ view: "table" }, false)} className={clsx("rounded-md p-1.5", view === "table" ? "bg-surface text-fg shadow-sm" : "text-muted")} aria-label="Table view" aria-pressed={view === "table"}><List className="h-4 w-4" /></button>
          </div>
        </div>
      </div>

      {/* Pattern tabs */}
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Pattern type">
        {PATTERN_TABS.map((t) => {
          const n = t.value ? counts[t.value]?.total : allCount;
          const active = pattern === t.value;
          return (
            <button key={t.value || "all"} role="tab" aria-selected={active} onClick={() => update({ pattern: t.value || null, status: null })}
              className={clsx("flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm font-medium transition",
                active ? "border-accent bg-accent text-accent-fg" : "border-line bg-surface text-fg-2 hover:border-line-strong hover:text-fg")}>
              {t.label}
              <span className={clsx("num rounded-full px-1.5 text-[11px]", active ? "bg-black/15" : "bg-surface-2 text-muted")}>{summary.isLoading ? "…" : n ?? 0}</span>
            </button>
          );
        })}
      </div>

      {/* Filter bar */}
      <div className="card p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          {!isTrendTab && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Breakout status">
              {STATUS_TABS.map((s) => (
                <button key={s.value || "any"} onClick={() => update({ status: s.value || null })} aria-pressed={status === s.value}
                  className={clsx("rounded-md px-2.5 py-1 text-xs font-medium transition",
                    status === s.value ? "bg-fg text-bg" : "bg-surface-2 text-fg-2 hover:text-fg")}>
                  {s.label}
                </button>
              ))}
            </div>
          )}
          <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center lg:justify-end">
            <div className="relative sm:w-60">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} className="input py-1.5 pl-9" placeholder="Filter by symbol or name" aria-label="Filter by symbol or name" />
            </div>
            <select value={get("sort") || "confidence"} onChange={(e) => update({ sort: e.target.value === "confidence" ? null : e.target.value })} className="input py-1.5 sm:w-48" aria-label="Sort by">
              {SORTS.map((s) => <option key={s.value} value={s.value}>Sort: {s.label}</option>)}
            </select>
            <button onClick={() => setShowFilters((s) => !s)} className={clsx("btn-secondary py-1.5", showFilters && "border-accent text-accent")} aria-expanded={showFilters}>
              <SlidersHorizontal className="h-4 w-4" /> Filters{activeFilters ? ` (${activeFilters})` : ""}
            </button>
          </div>
        </div>

        {showFilters && (
          <div className="fade-in mt-3 grid gap-4 border-t border-line pt-3 sm:grid-cols-2 lg:grid-cols-5">
            <div>
              <label className="label flex items-center justify-between" htmlFor="f-conf">
                <InfoTip text={METRIC_TIPS.confidence}>Min confidence</InfoTip><span className="num text-accent">{minConf}</span>
              </label>
              <input id="f-conf" type="range" min={0} max={90} step={5} value={minConf} onChange={(e) => update({ minConf: e.target.value === "0" ? null : e.target.value })} className="w-full accent-[var(--accent)]" />
            </div>
            <div>
              <label className="label flex items-center justify-between" htmlFor="f-vr">
                <InfoTip text={METRIC_TIPS.volumeRatio}>Min volume expansion</InfoTip><span className="num text-accent">{minVr ? `${minVr}×` : "any"}</span>
              </label>
              <input id="f-vr" type="range" min={0} max={5} step={0.25} value={minVr} onChange={(e) => update({ minVr: e.target.value === "0" ? null : e.target.value })} className="w-full accent-[var(--accent)]" />
            </div>
            <div>
              <label className="label" htmlFor="f-trend">Trend</label>
              <select id="f-trend" value={get("trend")} onChange={(e) => update({ trend: e.target.value || null })} className="input py-1.5">
                <option value="">Any trend</option>
                {["Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"].map((t) => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="f-mcap">Market cap</label>
              <select id="f-mcap" value={bucket.value} onChange={(e) => update({ mcap: e.target.value || null })} className="input py-1.5">
                {MCAP_BUCKETS.map((b) => <option key={b.value} value={b.value}>{b.label}</option>)}
              </select>
            </div>
            <div>
              <span className="label">Price range (₹)</span>
              <div className="flex items-center gap-2">
                <input inputMode="decimal" value={minPrice} onChange={(e) => setMinPrice(e.target.value.replace(/[^\d.]/g, ""))} className="input py-1.5" placeholder="Min" aria-label="Minimum price" />
                <span className="text-muted">–</span>
                <input inputMode="decimal" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value.replace(/[^\d.]/g, ""))} className="input py-1.5" placeholder="Max" aria-label="Maximum price" />
              </div>
            </div>
            <div className="sm:col-span-2 lg:col-span-5">
              <button onClick={reset} className="btn-ghost px-2 py-1 text-xs"><RotateCcw className="h-3.5 w-3.5" /> Reset filters</button>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-muted">
        <span>{data ? `${data.total.toLocaleString("en-IN")} matches` : " "}{data?.lastUpdated ? ` · scan ${timeAgo(data.lastUpdated)}` : ""}</span>
        {isFetching && !isLoading && <span>Updating…</span>}
      </div>

      {error ? (
        <div className="card"><ErrorState message={(error as Error).message} onRetry={() => refetch()} /></div>
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[380px]" />)}
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="card">
          <EmptyState title="No stocks match these filters"
            body={allCount === 0 ? "The pattern scan hasn't produced results yet. It runs automatically in the background." : "Try relaxing the confidence, volume or market-cap filters, or pick a different pattern."}
            action={activeFilters || status ? <button className="btn-secondary" onClick={reset}>Reset filters</button> : undefined} />
        </div>
      ) : data ? (
        <div className={clsx("transition-opacity", isFetching && "opacity-60")}>
          {view === "table" ? <DetectionTable items={data.items} /> : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
              {data.items.map((d) => <DetectionCard key={d.id} d={d} />)}
            </div>
          )}
        </div>
      ) : null}

      {data && data.totalPages > 1 && (
        <div className="flex items-center justify-center gap-1">
          <button className="btn-secondary px-2.5 py-1.5" disabled={page <= 1} onClick={() => update({ page: String(page - 1) }, false)} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
          <span className="num px-3 text-sm text-muted">Page {page} / {data.totalPages}</span>
          <button className="btn-secondary px-2.5 py-1.5" disabled={page >= data.totalPages} onClick={() => update({ page: String(page + 1) }, false)} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
        </div>
      )}

      <Disclaimer className="pt-2" />
    </div>
  );
}
