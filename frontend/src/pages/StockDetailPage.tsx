import clsx from "clsx";
import { ArrowLeft, Database, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { METRIC_TIPS } from "../components/DetectionCard";
import { PriceChart, type Level, type TrendLine } from "../components/PriceChart";
import { Change, ConfidenceBar, Disclaimer, EmptyState, ErrorState, InfoTip, PatternTag, Segmented, Skeleton, StatusBadge, TrendBadge } from "../components/ui";
import { ApiError } from "../lib/api";
import { dateTime, isNum, mcap, num, pct, price, ratio, volume } from "../lib/format";
import { useChart, useEquity } from "../lib/queries";
import type { Detection, EquityDetail } from "../lib/types";

const TIMEFRAMES = [
  { value: "INTRADAY", label: "Intraday" },
  { value: "1D", label: "1D" },
  { value: "1W", label: "1W" },
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "6M", label: "6M" },
  { value: "1Y", label: "1Y" },
] as const;

const COMPONENT_LABELS: Record<string, { label: string; tip: string }> = {
  price_vs_ma: { label: "Price vs MAs", tip: "Close relative to the 50- and 200-day averages, measured in ATRs." },
  ma_alignment: { label: "MA alignment", tip: "Ordering of the 20 > 50 > 200-day averages (bullish) or the reverse (bearish)." },
  ma_slope: { label: "MA slope", tip: "Direction and steepness of the 50-day average over the last 20 sessions." },
  swing_structure: { label: "Swing structure", tip: "Higher highs and higher lows (+) vs lower highs and lower lows (−) among recent swing points." },
  momentum: { label: "Momentum", tip: "60-session return, scaled." },
};

function Stat({ label, value, tip, sub }: { label: string; value: React.ReactNode; tip?: string; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface px-3.5 py-3">
      <p className="flex items-center text-[10px] font-medium uppercase tracking-wider text-muted">{tip ? <InfoTip text={tip}>{label}</InfoTip> : label}</p>
      <p className="num mt-1 truncate text-[15px] font-semibold">{value}</p>
      {sub && <p className="num mt-0.5 truncate text-[11px] text-muted">{sub}</p>}
    </div>
  );
}

function SectionTitle({ icon: Icon, children, note }: { icon: typeof Database; children: React.ReactNode; note?: string }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold"><Icon className="h-4 w-4 text-accent" />{children}</h2>
      {note && <span className="text-[11px] text-muted">{note}</span>}
    </div>
  );
}

function ChartPanel({ symbol, detail, selected }: { symbol: string; detail: EquityDetail; selected: Detection | null }) {
  const [tf, setTf] = useState<string>("6M");
  const { data, isLoading, error, refetch, isFetching } = useChart(symbol, tf);
  const levels = useMemo<Level[]>(() => {
    if (!selected) return [];
    const out: Level[] = [];
    if (isNum(selected.support)) out.push({ price: selected.support, label: "Support", kind: "support" });
    if (isNum(selected.resistance) && selected.resistance !== selected.breakoutLevel) out.push({ price: selected.resistance, label: "Resistance", kind: "resistance" });
    if (isNum(selected.breakoutLevel)) out.push({ price: selected.breakoutLevel, label: "Breakout", kind: "breakout" });
    return out;
  }, [selected]);
  const lines = useMemo<TrendLine[]>(() => {
    const l = (selected?.metrics?.lines ?? null) as { upper?: [string, number][]; lower?: [string, number][] } | null;
    if (!l) return [];
    return [
      ...(l.upper ? [{ points: l.upper, kind: "resistance" as const }] : []),
      ...(l.lower ? [{ points: l.lower, kind: "support" as const }] : []),
    ];
  }, [selected]);

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Segmented label="Chart timeframe" size="sm" value={tf} onChange={setTf} options={TIMEFRAMES.map((t) => ({ value: t.value, label: t.label }))} />
        <span className="text-[11px] text-muted">
          {isFetching ? "Loading…" : data ? `${data.interval} bars · ${data.source === "live" ? "live from provider" : "stored history"}` : ""}
          {selected && !["uptrend", "downtrend"].includes(selected.pattern) && <> · overlay: {selected.patternLabel}</>}
        </span>
      </div>
      {isLoading ? <Skeleton className="h-[420px] w-full" /> :
        error ? <ErrorState message={(error as Error).message} onRetry={() => refetch()} /> :
        data && data.bars.length > 1 ? <PriceChart bars={data.bars} levels={levels} lines={lines} /> :
        <EmptyState title="No chart data for this timeframe" body={["INTRADAY", "1D"].includes(tf) ? "Intraday bars are only available while the provider has today's session." : "Price history for this company isn't available yet."} />}
      {!detail.snapshot && <p className="mt-2 text-xs text-warn">This company is outside the eligible universe ({detail.company.eligibilityNote ?? "not evaluated"}), so it has no pattern analysis.</p>}
    </div>
  );
}

function PatternItem({ d, active, onSelect }: { d: Detection; active: boolean; onSelect: () => void }) {
  const isTrend = d.pattern === "uptrend" || d.pattern === "downtrend";
  const m = d.metrics as Record<string, unknown>;
  const extra: [string, string][] = [];
  if (d.pattern === "vcp") {
    const cs = (m.contractions as { depthPct: number }[] | undefined) ?? [];
    extra.push(["Contractions", cs.map((c) => `${c.depthPct.toFixed(1)}%`).join(" → ") || "—"],
      ["Volume dry-up", ratio(m.volumeDryUp as number)], ["Trend template", String(m.trendTemplate ?? "—")],
      ["10-day tightness", pct(m.tightness10dPct as number, 1, false)], ["Base length", `${m.baseLengthBars ?? "—"} bars`]);
  } else if (d.pattern === "falling_wedge") {
    extra.push(["Lookback", `${m.lookbackBars ?? "—"} bars`], ["Touches (upper/lower)", `${m.touchesUpper ?? "—"}/${m.touchesLower ?? "—"}`],
      ["Width ratio", num(m.widthRatio as number, 2)], ["Fit R²", num(m.fitR2 as number, 2)],
      ["Bars to apex", num(m.barsToApex as number, 0)], ["Volume contraction", ratio(m.volumeContraction as number)]);
  } else if (d.pattern === "breakout") {
    extra.push(["Distance to level", pct(m.distanceToLevelPct as number)], ["Resistance age", `${m.resistanceAgeBars ?? "—"} bars`],
      ["Breakout bar volume", ratio(m.breakoutVolumeRatio as number)], ["Close location", num(m.closeLocation as number, 2)]);
  }
  return (
    <button onClick={onSelect} className={clsx("w-full rounded-xl border p-3.5 text-left transition", active ? "border-accent bg-accent-soft/40" : "border-line hover:border-line-strong")} aria-pressed={active}>
      <div className="flex items-center justify-between gap-2">
        <PatternTag label={d.patternLabel} />
        {isTrend ? <TrendBadge trend={d.trend} /> : <StatusBadge status={d.status} />}
      </div>
      <div className="mt-3"><ConfidenceBar value={d.confidenceScore} /></div>
      <dl className="num mt-3 grid grid-cols-3 gap-2 text-xs">
        <div><dt className="text-muted">Support</dt><dd className="font-medium">{price(d.support)}</dd></div>
        <div><dt className="text-muted">Resistance</dt><dd className="font-medium">{price(d.resistance)}</dd></div>
        <div><dt className="text-muted">Breakout</dt><dd className="font-medium">{price(d.breakoutLevel)}</dd></div>
      </dl>
      {extra.length > 0 && (
        <dl className="mt-3 space-y-1 border-t border-line pt-2.5 text-xs">
          {extra.map(([k, v]) => <div key={k} className="flex justify-between gap-2"><dt className="text-muted">{k}</dt><dd className="num text-fg-2">{v}</dd></div>)}
        </dl>
      )}
      <p className="mt-2 text-[10px] text-muted">Detected {dateTime(d.detectedAt)}</p>
    </button>
  );
}

function TrendPanel({ trend }: { trend: EquityDetail["trend"] }) {
  if (!trend) return <p className="text-sm text-muted">Not enough history to classify the trend.</p>;
  const pos = (trend.score + 100) / 2;
  return (
    <div>
      <div className="flex items-center justify-between">
        <TrendBadge trend={trend.label} className="text-sm" />
        <span className="num text-sm font-semibold">{trend.score > 0 ? "+" : ""}{trend.score.toFixed(0)}</span>
      </div>
      <div className="relative mt-3 h-2 rounded-full bg-gradient-to-r from-down via-surface-2 to-up" role="meter" aria-valuemin={-100} aria-valuemax={100} aria-valuenow={trend.score} aria-label="Trend score">
        <span className="absolute top-1/2 h-4 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-fg ring-2 ring-surface" style={{ left: `${pos}%` }} />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted"><span>−100</span><span>Neutral</span><span>+100</span></div>
      <dl className="mt-4 space-y-2.5">
        {Object.entries(COMPONENT_LABELS).map(([k, meta]) => {
          const v = trend.components[k];
          return (
            <div key={k}>
              <dt className="flex items-center justify-between text-xs">
                <InfoTip text={meta.tip}><span className="text-fg-2">{meta.label}</span></InfoTip>
                <span className="num text-muted">{isNum(v) ? v.toFixed(2) : "n/a"}</span>
              </dt>
              <dd className="relative mt-1 h-1.5 rounded-full bg-surface-2">
                {isNum(v) && (
                  <span className={clsx("absolute top-0 h-full rounded-full", v >= 0 ? "bg-up" : "bg-down")}
                    style={v >= 0 ? { left: "50%", width: `${v * 50}%` } : { right: "50%", width: `${-v * 50}%` }} />
                )}
                <span className="absolute left-1/2 top-[-2px] h-[10px] w-px bg-line-strong" />
              </dd>
            </div>
          );
        })}
      </dl>
    </div>
  );
}

export default function StockDetailPage() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();
  const { data, isLoading, error, refetch } = useEquity(sym);
  const nav = useNavigate();
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const patterns = data?.patterns ?? [];
  const selected = patterns.find((p) => p.id === selectedId)
    ?? patterns.find((p) => !["uptrend", "downtrend"].includes(p.pattern)) ?? patterns[0] ?? null;

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-5 w-24" /><Skeleton className="h-12 w-80" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16" />)}</div>
        <Skeleton className="h-[480px]" />
      </div>
    );
  }
  if (error) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <div className="card">
        {notFound ? <EmptyState title={`No listed company "${sym}"`} body="Check the NSE symbol and try again." action={<Link to="/app/market" className="btn-secondary">Back to market</Link>} />
          : <ErrorState message={(error as Error).message} onRetry={() => refetch()} />}
      </div>
    );
  }
  if (!data) return null;
  const s = data.snapshot;
  const t = data.technicals;
  const vsMa = (ma: number | null) => (isNum(s?.price) && isNum(ma) ? ((s!.price! / ma - 1) * 100) : null);

  return (
    <div className="space-y-5">
      <button onClick={() => (window.history.length > 1 ? nav(-1) : nav("/app/market"))}
        className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" /> Back</button>

      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight">{data.company.name}</h1>
            {s?.trend && <TrendBadge trend={s.trend} />}
          </div>
          <p className="num mt-1 text-sm text-muted">NSE: {data.company.symbol}{data.company.isin ? ` · ${data.company.isin}` : ""}{data.company.series ? ` · ${data.company.series}` : ""}</p>
        </div>
        <div className="md:text-right">
          <p className="num text-3xl font-semibold tracking-tight">₹{price(s?.price)}</p>
          <div className="mt-1 flex items-center gap-3 text-sm md:justify-end">
            <span className="flex items-center gap-1"><Change value={s?.oneDayChange} /><span className="text-xs text-muted">1D</span></span>
            <span className="flex items-center gap-1"><Change value={s?.oneWeekChange} /><span className="text-xs text-muted">1W</span></span>
          </div>
          <p className="mt-0.5 text-[11px] text-muted">As of {dateTime(s?.asOf)}</p>
        </div>
      </div>

      <section aria-label="Market data">
        <SectionTitle icon={Database} note="Market data · provider-sourced, may be delayed">Market data</SectionTitle>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Market cap" value={mcap(s?.marketCap)} tip="Shares outstanding × latest price." />
          <Stat label="Volume (1D)" value={volume(s?.volume)} sub={isNum(s?.volumeRatio) ? `${ratio(s?.volumeRatio)} of 50D avg` : undefined} tip={METRIC_TIPS.volumeRatio} />
          <Stat label="Avg volume (1W)" value={volume(s?.avgVolumeWeek)} />
          <Stat label="Avg volume (50D)" value={volume(s?.avgVolume50d)} />
          <Stat label="52W range" value={`${price(s?.low52w, 0)} – ${price(s?.high52w, 0)}`} sub={isNum(s?.price) && isNum(s?.high52w) ? `${pct(((s!.price! / s!.high52w!) - 1) * 100)} from high` : undefined} />
          <Stat label="1M change" value={<Change value={s?.oneMonthChange} arrow={false} />} />
        </div>
      </section>

      <div className="grid gap-5 2xl:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-5">
          <ChartPanel symbol={sym} detail={data} selected={selected} />
          <section className="card p-4" aria-label="Technical metrics">
            <SectionTitle icon={Sparkles} note="Analytical signal">Technical metrics</SectionTitle>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <Stat label="SMA 20" value={price(t.sma20)} sub={isNum(vsMa(t.sma20)) ? `${pct(vsMa(t.sma20))} vs price` : undefined} />
              <Stat label="SMA 50" value={price(t.sma50)} sub={isNum(vsMa(t.sma50)) ? `${pct(vsMa(t.sma50))} vs price` : undefined} />
              <Stat label="SMA 200" value={price(t.sma200)} sub={isNum(vsMa(t.sma200)) ? `${pct(vsMa(t.sma200))} vs price` : undefined} />
              <Stat label="ATR 14" value={pct(t.atr14Pct, 2, false)} tip="Average true range over 14 sessions as a % of price: typical daily movement." />
              <Stat label="RS rating" value={num(t.rsRating, 0)} tip={METRIC_TIPS.rs} />
              <Stat label="Trend score" value={isNum(data.trend?.score) ? data.trend!.score.toFixed(0) : "—"} tip="−100 (strong downtrend) to +100 (strong uptrend)." />
            </div>
          </section>
        </div>

        <aside className="grid content-start gap-5 lg:grid-cols-2 2xl:grid-cols-1">
          <section className="card p-4" aria-label="Trend classification">
            <SectionTitle icon={Sparkles} note="Analytical signal">Trend classification</SectionTitle>
            <TrendPanel trend={data.trend} />
          </section>
          <section className="card p-4" aria-label="Detected patterns">
            <SectionTitle icon={Sparkles} note={patterns.length ? "Select one to overlay on the chart" : undefined}>Detected patterns</SectionTitle>
            {patterns.length === 0 ? (
              <p className="text-sm text-muted">No patterns detected in the latest scan.</p>
            ) : (
              <div className="space-y-3">
                {patterns.map((p) => <PatternItem key={p.id} d={p} active={selected?.id === p.id} onSelect={() => setSelectedId(p.id)} />)}
              </div>
            )}
          </section>
          <Disclaimer className="lg:col-span-2 2xl:col-span-1" />
        </aside>
      </div>
    </div>
  );
}
