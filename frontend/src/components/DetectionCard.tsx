import clsx from "clsx";
import { Link } from "react-router-dom";
import { dateTime, isNum, mcap, pct, price, ratio, volume } from "../lib/format";
import type { Detection } from "../lib/types";
import { Change, ConfidenceBar, InfoTip, PatternTag, Sparkline, StatusBadge, TrendBadge } from "./ui";

export const METRIC_TIPS = {
  confidence: "Pattern strength score (0–100) combining the detector's quality checks. Higher means the structure more closely matches the textbook definition. It is not a probability of success.",
  support: "Price level where buying interest has held: the lower trendline for wedges, the final contraction low for VCP, or the nearest swing low.",
  resistance: "Price level where selling has capped advances: the upper trendline, the VCP pivot or the prior high.",
  breakout: "Level a close must clear to count as a breakout. For wedges it slopes with the upper trendline.",
  volumeRatio: "Latest session volume ÷ the 50-session average. Above 1.5× is usually read as expansion. During market hours the session is still in progress.",
  rs: "Relative-strength rating 1–99: the stock's weighted 3/6/9/12-month performance vs NIFTY 50, ranked across the universe.",
};

function Metric({ label, value, tip, className }: { label: string; value: React.ReactNode; tip?: string; className?: string }) {
  return (
    <div className={className}>
      <dt className="flex items-center text-[10px] font-medium uppercase tracking-wider text-muted">
        {tip ? <InfoTip text={tip}>{label}</InfoTip> : label}
      </dt>
      <dd className="num mt-0.5 text-sm font-medium">{value}</dd>
    </div>
  );
}

function PatternSpecific({ d }: { d: Detection }) {
  const m = d.metrics as Record<string, unknown>;
  const n = (k: string) => (isNum(m[k]) ? (m[k] as number) : null);
  if (d.pattern === "vcp") {
    const cs = (m.contractions as { depthPct: number }[] | undefined) ?? [];
    return (
      <p className="text-xs text-muted">
        Contractions <span className="num text-fg-2">{cs.map((c) => `${c.depthPct.toFixed(1)}%`).join(" → ") || "—"}</span>
        {" · "}Vol dry-up <span className="num text-fg-2">{ratio(n("volumeDryUp"))}</span>
        {" · "}Template <span className="num text-fg-2">{String(m.trendTemplate ?? "—")}</span>
      </p>
    );
  }
  if (d.pattern === "falling_wedge") {
    return (
      <p className="text-xs text-muted">
        Touches <span className="num text-fg-2">{String(m.touchesUpper ?? "—")}/{String(m.touchesLower ?? "—")}</span>
        {" · "}Width ratio <span className="num text-fg-2">{isNum(n("widthRatio")) ? n("widthRatio")!.toFixed(2) : "—"}</span>
        {" · "}Fit R² <span className="num text-fg-2">{isNum(n("fitR2")) ? n("fitR2")!.toFixed(2) : "—"}</span>
      </p>
    );
  }
  if (d.pattern === "breakout") {
    return (
      <p className="text-xs text-muted">
        vs level <span className="num text-fg-2">{pct(n("distanceToLevelPct"))}</span>
        {" · "}Resistance age <span className="num text-fg-2">{String(m.resistanceAgeBars ?? "—")} bars</span>
        {isNum(n("breakoutBarsAgo")) && <> · Broke out <span className="num text-fg-2">{n("breakoutBarsAgo")}d ago</span></>}
      </p>
    );
  }
  return (
    <p className="text-xs text-muted">
      Trend score <span className="num text-fg-2">{isNum(n("trendScore")) ? n("trendScore")!.toFixed(0) : "—"}</span>
      {" · "}RS <span className="num text-fg-2">{isNum(n("rsRating")) ? n("rsRating")!.toFixed(0) : "—"}</span>
    </p>
  );
}

export function DetectionCard({ d }: { d: Detection }) {
  const isTrend = d.pattern === "uptrend" || d.pattern === "downtrend";
  return (
    <Link to={`/app/stock/${d.symbol}`} className="card group flex flex-col gap-3 p-4 transition hover:border-line-strong focus-visible:border-accent">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="num text-sm font-semibold group-hover:text-accent">{d.symbol}</span>
            <PatternTag label={d.patternLabel} />
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{d.name ?? "—"}</p>
        </div>
        <div className="text-right">
          <p className="num text-sm font-semibold">₹{price(d.currentPrice)}</p>
          <Change value={d.oneDayChange} className="text-xs" />
        </div>
      </div>

      <div className="flex items-center justify-between gap-2">
        {isTrend ? <TrendBadge trend={d.trend} /> : <StatusBadge status={d.status} />}
        <span className="text-[11px] text-muted">{mcap(d.marketCap)}</span>
      </div>

      <Sparkline data={d.chart} width={320} height={56} className="w-full" />

      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] font-medium uppercase tracking-wider text-muted">
          <InfoTip text={METRIC_TIPS.confidence}>Confidence</InfoTip>
        </div>
        <ConfidenceBar value={d.confidenceScore} />
      </div>

      <dl className="grid grid-cols-3 gap-x-3 gap-y-2">
        <Metric label="Support" value={price(d.support)} tip={METRIC_TIPS.support} />
        <Metric label="Resist." value={price(d.resistance)} tip={METRIC_TIPS.resistance} />
        <Metric label="Breakout" value={price(d.breakoutLevel)} tip={METRIC_TIPS.breakout} />
        <Metric label="Volume" value={volume(d.volumeCurrent)} />
        <Metric label="Avg vol" value={volume(d.volumeAvg)} />
        <Metric label="Vol ratio" tip={METRIC_TIPS.volumeRatio}
          value={<span className={clsx(isNum(d.volumeRatio) && d.volumeRatio >= 1.5 && "text-up")}>{ratio(d.volumeRatio)}</span>} />
      </dl>

      <div className="mt-auto space-y-1 border-t border-line pt-2.5">
        <PatternSpecific d={d} />
        <p className="text-[10px] text-muted">Detected {dateTime(d.detectedAt)}</p>
      </div>
    </Link>
  );
}
