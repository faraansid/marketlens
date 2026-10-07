import clsx from "clsx";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Change, EmptyState, ErrorState, InfoTip, Skeleton, Sparkline, TrendBadge } from "../components/ui";
import { DASH, dateTime, isNum, mcap, price, timeAgo, toneOf, volume } from "../lib/format";
import { useEquities, useMarketOverview } from "../lib/queries";
import type { Equity, Instrument } from "../lib/types";

/* ---------------------------------------------------------------- Bento */

function fmtInstrument(i: Instrument) {
  if (!isNum(i.value)) return DASH;
  const digits = i.category === "fx" ? 3 : 2;
  const v = price(i.value, digits);
  return i.category === "commodity" ? `$${v}` : i.category === "fx" ? `₹${v}` : v;
}

function InstrumentCard({ i, hero }: { i: Instrument; hero?: boolean }) {
  const tone = toneOf(i.changePct);
  return (
    <div className={clsx("card group relative flex min-w-0 flex-col justify-between overflow-hidden p-3 sm:p-4", hero && "col-span-2 md:row-span-2 sm:p-5")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className={clsx("truncate font-semibold", hero ? "text-base" : "text-sm")}>{i.name}</p>
          <p className="num truncate text-[11px] text-muted">{i.symbol}{i.unit ? ` · ${i.unit}` : ""}</p>
        </div>
        <span className={clsx("num shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-semibold",
          tone === "up" ? "bg-up-soft text-up" : tone === "down" ? "bg-down-soft text-down" : "bg-surface-2 text-muted")}>
          {tone === "up" ? "▲" : tone === "down" ? "▼" : "•"} {isNum(i.changePct) ? `${Math.abs(i.changePct).toFixed(2)}%` : DASH}
        </span>
      </div>
      <div className={clsx("mt-3", hero && "sm:mt-6")}>
        <p className={clsx("num truncate font-semibold tracking-tight", hero ? "text-2xl sm:text-4xl" : "text-lg sm:text-xl")}>{fmtInstrument(i)}</p>
        <p className="num mt-0.5 text-xs">
          <span className={clsx(tone === "up" && "text-up", tone === "down" && "text-down", tone === "flat" && "text-muted")}>
            {isNum(i.change) ? `${i.change > 0 ? "+" : ""}${price(i.change, i.category === "fx" ? 3 : 2)}` : DASH}
          </span>
          <span className="text-muted"> today</span>
        </p>
      </div>
      <div className={clsx("mt-3", hero && "sm:mt-auto sm:pt-6")}>
        <Sparkline data={i.sparkline} width={hero ? 520 : 200} height={hero ? 110 : 34} className="w-full" />
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-muted">
          <span>{i.sparklineLabel ?? ""}</span>
          <span className="truncate pl-1" title={`Provider timestamp: ${dateTime(i.marketTime)}`}>
            {i.stale ? <span className="text-warn">Stale · </span> : null}{dateTime(i.marketTime)}
          </span>
        </div>
      </div>
    </div>
  );
}

function BreadthCard({ adv, dec, total, asOf }: { adv: number; dec: number; total: number; asOf: string | null }) {
  const unchanged = Math.max(0, total - adv - dec);
  const pA = total ? (adv / total) * 100 : 0, pD = total ? (dec / total) * 100 : 0;
  return (
    <div className="card col-span-2 flex flex-col justify-between p-4">
      <div className="flex items-center justify-between">
        <InfoTip text="Computed from MarketLens's eligible universe (listed companies above ₹1,000 Cr) using each stock's latest session change.">
          <p className="text-sm font-semibold">Market breadth</p>
        </InfoTip>
        <span className="text-[11px] text-muted">{total.toLocaleString("en-IN")} stocks</span>
      </div>
      <div className="mt-4 flex h-2.5 overflow-hidden rounded-full bg-surface-2" role="img" aria-label={`${adv} advancing, ${dec} declining`}>
        <div className="bg-up" style={{ width: `${pA}%` }} />
        <div className="bg-muted/40" style={{ width: `${100 - pA - pD}%` }} />
        <div className="bg-down" style={{ width: `${pD}%` }} />
      </div>
      <div className="num mt-3 grid grid-cols-3 text-xs">
        <div><p className="text-lg font-semibold text-up">{adv}</p><p className="text-muted">Advancing</p></div>
        <div className="text-center"><p className="text-lg font-semibold text-fg-2">{unchanged}</p><p className="text-muted">Unchanged</p></div>
        <div className="text-right"><p className="text-lg font-semibold text-down">{dec}</p><p className="text-muted">Declining</p></div>
      </div>
      <p className="mt-2 text-[10px] text-muted">As of {dateTime(asOf)}</p>
    </div>
  );
}

function MarketBento() {
  const { data, isLoading, error, refetch } = useMarketOverview();
  if (isLoading) {
    return (
      <div className="grid auto-rows-[150px] grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Skeleton className="col-span-2 row-span-2 h-full" />
        {Array.from({ length: 8 }).map((_, k) => <Skeleton key={k} className="h-full" />)}
      </div>
    );
  }
  if (error) return <div className="card"><ErrorState message={(error as Error).message} onRetry={() => refetch()} /></div>;
  if (!data || data.instruments.length === 0) {
    return <div className="card"><EmptyState title="Market overview not available yet" body="The first data refresh hasn't finished. This fills in automatically once the background job completes." /></div>;
  }
  const [hero, ...rest] = data.instruments;
  return (
    <div className="grid grid-cols-2 gap-2.5 sm:gap-3 md:grid-cols-4 xl:grid-cols-6">
      <InstrumentCard i={hero} hero />
      {rest.slice(0, 4).map((i) => <InstrumentCard key={i.key} i={i} />)}
      {data.breadth.total > 0 && <BreadthCard adv={data.breadth.advancers} dec={data.breadth.decliners} total={data.breadth.total} asOf={data.breadth.asOf} />}
      {rest.slice(4).map((i) => <InstrumentCard key={i.key} i={i} />)}
    </div>
  );
}

/* ---------------------------------------------------------------- Equity table */

type SortKey = "name" | "symbol" | "price" | "oneDayChange" | "oneWeekChange" | "volume" | "avgVolumeWeek" | "marketCap" | "trendScore";

const COLUMNS: { key: SortKey; label: string; align?: "right"; tip?: string; className?: string }[] = [
  { key: "name", label: "Company" },
  { key: "symbol", label: "Symbol" },
  { key: "price", label: "Price (₹)", align: "right" },
  { key: "oneDayChange", label: "1D %", align: "right", tip: "Change from the previous session's close to the latest price." },
  { key: "oneWeekChange", label: "1W %", align: "right", tip: "Change over the last 5 trading sessions." },
  { key: "volume", label: "Vol (1D)", align: "right", tip: "Shares traded in the latest session. During market hours this is the session so far." },
  { key: "avgVolumeWeek", label: "Avg Vol (1W)", align: "right", tip: "Average daily volume over the last 5 sessions." },
  { key: "marketCap", label: "Market Cap", align: "right", tip: "Shares outstanding × latest price, in ₹ crore." },
  { key: "trendScore", label: "Trend / Signal", tip: "Trend classification from a −100…+100 score (moving averages, MA slope, swing structure, momentum), plus active pattern signals." },
];

const SIGNAL_LABEL: Record<string, string> = {
  vcp: "VCP", falling_wedge: "Wedge", breakout: "Breakout",
};

function SignalChips({ signals }: { signals: string[] }) {
  if (!signals.length) return null;
  return (
    <>
      {signals.slice(0, 2).map((s) => {
        const [p, st] = s.split(":");
        return (
          <span key={s} className={clsx("rounded px-1.5 py-0.5 text-[10px] font-semibold",
            st === "confirmed" ? "bg-up-soft text-up" : st === "failed" ? "bg-down-soft text-down" : st === "potential" ? "bg-warn-soft text-warn" : "bg-accent-soft text-accent")}
            title={`${SIGNAL_LABEL[p] ?? p}${st ? ` · ${st}` : ""}`}>
            {SIGNAL_LABEL[p] ?? p}{st === "confirmed" ? " ✓" : st === "failed" ? " ✕" : ""}
          </span>
        );
      })}
    </>
  );
}

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function EquityTable() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const sort = (params.get("sort") as SortKey) || "marketCap";
  const order = (params.get("order") as "asc" | "desc") || "desc";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = Number(params.get("size")) || 50;
  const trend = params.get("trend") || "";
  const [search, setSearch] = useState(params.get("q") || "");
  const debounced = useDebounced(search.trim(), 300);

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) v === null || v === "" ? next.delete(k) : next.set(k, v);
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if ((params.get("q") || "") !== debounced) update({ q: debounced || null, page: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const query = useMemo(() => ({ search: debounced, sort, order, page, pageSize, trend: trend || undefined }), [debounced, sort, order, page, pageSize, trend]);
  const { data, isLoading, isFetching, error, refetch } = useEquities(query);

  const onSort = (key: SortKey) => {
    if (key === sort) update({ order: order === "desc" ? "asc" : "desc", page: null });
    else update({ sort: key, order: key === "name" || key === "symbol" ? "asc" : "desc", page: null });
  };

  return (
    <section className="card overflow-hidden" aria-labelledby="equities-heading">
      <div className="flex flex-col gap-3 border-b border-line p-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 id="equities-heading" className="font-semibold">Indian equities</h2>
          <p className="text-xs text-muted">
            NSE-listed companies above ₹1,000 Cr market cap · {data ? `${data.total.toLocaleString("en-IN")} companies` : "loading…"}
            {data?.lastUpdated && <> · updated {timeAgo(data.lastUpdated)}</>}
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search company or symbol…" className="input pl-9 pr-8" aria-label="Search equities by company name or symbol" />
            {search && <button onClick={() => setSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted hover:text-fg" aria-label="Clear search"><X className="h-4 w-4" /></button>}
          </div>
          <select value={trend} onChange={(e) => update({ trend: e.target.value || null, page: null })} className="input sm:w-44" aria-label="Filter by trend">
            <option value="">All trends</option>
            {["Strong Uptrend", "Uptrend", "Neutral", "Downtrend", "Strong Downtrend"].map((t) => <option key={t}>{t}</option>)}
          </select>
        </div>
      </div>

      {error ? (
        <ErrorState message={(error as Error).message} onRetry={() => refetch()} />
      ) : (
        <div className={clsx("overflow-x-auto transition-opacity", isFetching && !isLoading && "opacity-60")}>
          <table className="w-full min-w-[1080px] text-sm">
            <thead className="sticky top-0 z-10 border-b border-line bg-surface-2/70 backdrop-blur">
              <tr>
                {COLUMNS.map((c) => (
                  <th key={c.key} className={clsx("th", c.align === "right" && "text-right")} aria-sort={sort === c.key ? (order === "asc" ? "ascending" : "descending") : "none"}>
                    <span className={clsx("inline-flex items-center", c.align === "right" && "flex-row-reverse")}>
                      <button onClick={() => onSort(c.key)} className={clsx("inline-flex items-center gap-1 uppercase hover:text-fg", sort === c.key && "text-fg")}>
                        {c.label}
                        {sort === c.key ? (order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                      </button>
                      {c.tip && <InfoTip text={c.tip} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {isLoading &&
                Array.from({ length: 12 }).map((_, r) => (
                  <tr key={r}>{COLUMNS.map((c) => <td key={c.key} className="td"><Skeleton className="h-4 w-full max-w-[140px]" /></td>)}</tr>
                ))}
              {data?.items.map((e: Equity) => (
                <tr key={e.symbol} onClick={() => nav(`/app/stock/${e.symbol}`)} className="cursor-pointer transition-colors hover:bg-surface-2/70">
                  <td className="td max-w-[260px]">
                    <Link to={`/app/stock/${e.symbol}`} onClick={(ev) => ev.stopPropagation()} className="block truncate font-medium hover:text-accent">{e.name}</Link>
                  </td>
                  <td className="td num text-xs text-fg-2">{e.symbol}</td>
                  <td className="td num text-right font-medium">{price(e.price)}</td>
                  <td className="td text-right"><Change value={e.oneDayChange} arrow={false} /></td>
                  <td className="td text-right"><Change value={e.oneWeekChange} arrow={false} /></td>
                  <td className="td num text-right text-fg-2">{volume(e.volume)}</td>
                  <td className="td num text-right text-fg-2">{volume(e.avgVolumeWeek)}</td>
                  <td className="td num text-right text-fg-2">{mcap(e.marketCap)}</td>
                  <td className="td"><div className="flex items-center gap-1.5"><TrendBadge trend={e.trend} /><SignalChips signals={e.signals} /></div></td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 && (
            <EmptyState title={debounced ? `No companies match "${debounced}"` : "No equities yet"}
              body={debounced ? "Try a different company name or NSE symbol." : "Equity data appears after the first background refresh completes."}
              action={debounced ? <button className="btn-secondary" onClick={() => setSearch("")}>Clear search</button> : undefined} />
          )}
        </div>
      )}

      {data && data.total > 0 && (
        <div className="flex flex-col items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm sm:flex-row">
          <div className="flex items-center gap-2 text-muted">
            <span>Rows</span>
            <select value={pageSize} onChange={(e) => update({ size: e.target.value, page: null })} className="input w-auto py-1" aria-label="Rows per page">
              {[25, 50, 100].map((n) => <option key={n}>{n}</option>)}
            </select>
            <span className="num">{((page - 1) * pageSize + 1).toLocaleString("en-IN")}–{Math.min(page * pageSize, data.total).toLocaleString("en-IN")} of {data.total.toLocaleString("en-IN")}</span>
          </div>
          <div className="flex items-center gap-1">
            <button className="btn-secondary px-2.5 py-1.5" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })} aria-label="Previous page"><ChevronLeft className="h-4 w-4" /></button>
            <span className="num px-3 text-muted">Page {page} / {data.totalPages}</span>
            <button className="btn-secondary px-2.5 py-1.5" disabled={page >= data.totalPages} onClick={() => update({ page: String(page + 1) })} aria-label="Next page"><ChevronRight className="h-4 w-4" /></button>
          </div>
        </div>
      )}
    </section>
  );
}

export default function MarketPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Market</h1>
          <p className="text-sm text-muted">Indices, macro instruments and the full equity universe.</p>
        </div>
      </div>
      <MarketBento />
      <EquityTable />
    </div>
  );
}
