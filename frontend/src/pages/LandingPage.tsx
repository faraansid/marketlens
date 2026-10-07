import { ArrowRight, Activity, BarChart3, Clock, Database, Filter, LineChart, Shield, TrendingUp, Triangle, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Disclaimer, Logo, ThemeToggle } from "../components/ui";
import { useAuth } from "../lib/auth";

/** Illustrative chart in the hero. Clearly labelled as an illustration, not market data. */
function HeroIllustration() {
  // A stylised VCP: advance, three tightening pullbacks, breakout.
  const pts = [8, 14, 20, 30, 42, 55, 70, 82, 90, 66, 74, 85, 89, 76, 82, 88, 83, 87, 89, 104, 116];
  const w = 520, h = 220, max = 120;
  const step = w / (pts.length - 1);
  const xy = pts.map((v, i) => [i * step, h - (v / max) * h] as const);
  const path = xy.map(([x, y], i) => `${i ? "L" : "M"}${x},${y}`).join(" ");
  const pivotY = h - (90 / max) * h;
  return (
    <div className="card relative overflow-hidden p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">Pattern illustration</p>
          <p className="mt-1 font-semibold">Volatility Contraction → Breakout</p>
        </div>
        <span className="rounded-md bg-up-soft px-2 py-1 text-xs font-semibold text-up">Confirmed · 2.4× vol</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h + 40}`} className="h-auto w-full" role="img" aria-label="Illustrative chart of a volatility contraction pattern followed by a breakout">
        <defs>
          <linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1="0" x2={w} y1={pivotY} y2={pivotY} stroke="var(--warn)" strokeDasharray="6 5" strokeWidth="1.2" />
        <text x={w - 4} y={pivotY - 6} textAnchor="end" fontSize="11" fill="var(--warn)">pivot</text>
        <path d={`${path} L${w},${h} L0,${h} Z`} fill="url(#hero-fill)" />
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeLinejoin="round" />
        {[[9, "-27%"], [13, "-15%"], [16, "-7%"]].map(([i, l]) => (
          <text key={i} x={xy[i as number][0]} y={xy[i as number][1] + 18} textAnchor="middle" fontSize="11" fill="var(--muted)">{l}</text>
        ))}
        {pts.map((v, i) => {
          const vh = i >= 19 ? 34 : Math.max(6, 22 - (i > 8 ? (i - 8) * 1.6 : 0));
          return <rect key={i} x={i * step - 6} y={h + 40 - vh} width="12" height={vh} rx="2" fill={i >= 19 ? "var(--up)" : "var(--line-strong)"} opacity={v ? 0.9 : 0} />;
        })}
      </svg>
      <p className="mt-2 text-[11px] text-muted">Illustration only — not real market data.</p>
    </div>
  );
}

const FEATURES = [
  { icon: BarChart3, title: "Market overview", body: "NIFTY 50, SENSEX, Bank & IT indices, India VIX, USD/INR, crude, gold and silver in a single glance." },
  { icon: Database, title: "Every eligible listed company", body: "The universe comes straight from NSE's list of listed equities and is filtered to companies above ₹1,000 Cr market cap. No ETFs, REITs, InvITs or funds." },
  { icon: Filter, title: "Fast screener", body: "Search, sort and page through the whole universe by 1-day and 1-week returns, volume, market cap and trend." },
  { icon: Clock, title: "Server-side refresh every 30 min", body: "A background pipeline ingests, validates and analyses the market on a schedule, so you open the dashboard to results that are already processed." },
];

const PATTERNS = [
  { icon: Triangle, name: "VCP", body: "Successive, shrinking pullbacks with drying volume inside a Stage-2 uptrend, with the pivot identified." },
  { icon: TrendingUp, name: "Falling Wedge", body: "Converging, downward-sloping trendlines fitted to swing points, with the breakout level tracked as it slopes." },
  { icon: Zap, name: "Breakouts", body: "Closes through established resistance, labelled Potential, Confirmed (on volume) or Failed." },
  { icon: Activity, name: "Trend", body: "A five-factor trend score: moving averages, MA slope, swing structure and momentum." },
];

export default function LandingPage() {
  const { user } = useAuth();
  const cta = user ? "/app/market" : "/signin";
  return (
    <div className="min-h-full bg-bg">
      <header className="sticky top-0 z-30 border-b border-line/60 bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <Logo />
          <nav className="flex items-center gap-2">
            <a href="#patterns" className="btn-ghost hidden sm:inline-flex">Patterns</a>
            <a href="#features" className="btn-ghost hidden sm:inline-flex">Features</a>
            <ThemeToggle />
            <Link to={cta} className="btn-primary">{user ? "Open dashboard" : "Sign In"}</Link>
          </nav>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="grid-backdrop pointer-events-none absolute inset-0 opacity-60" aria-hidden />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 pb-20 pt-16 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-24">
          <div className="fade-in">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-fg-2">
              <span className="h-1.5 w-1.5 rounded-full bg-up" /> NSE equities · pattern intelligence
            </span>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">
              See the setups<br />
              <span className="text-accent">before the crowd does.</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-fg-2 sm:text-lg">
              MarketLens scans every Indian listed company above ₹1,000 Cr for volatility contractions, falling wedges,
              breakouts and trend strength, then puts the market's state on one fast dashboard.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link to={cta} className="btn-primary px-5 py-2.5 text-[15px]">
                Start Analyzing the Market <ArrowRight className="h-4 w-4" />
              </Link>
              <a href="#patterns" className="btn-secondary px-5 py-2.5 text-[15px]">How detection works</a>
            </div>
            <dl className="mt-10 grid max-w-lg grid-cols-3 gap-6 border-t border-line pt-6">
              {[["5", "pattern detectors"], ["30 min", "server refresh cycle"], ["₹1,000 Cr+", "market-cap universe"]].map(([k, v]) => (
                <div key={v}>
                  <dt className="num text-xl font-semibold">{k}</dt>
                  <dd className="mt-1 text-xs text-muted">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="fade-in [animation-delay:120ms]"><HeroIllustration /></div>
        </div>
      </section>

      <section id="patterns" className="border-t border-line bg-bg-elev py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold text-accent">Technical-pattern detection</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Rules you can read, scores you can check.</h2>
            <p className="mt-3 text-fg-2">
              Every detector uses documented, configurable rules, not a black box. Each signal comes with its support,
              resistance, breakout level, volume expansion and a 0–100 strength score.
            </p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {PATTERNS.map((p) => (
              <div key={p.name} className="card p-5 transition hover:border-line-strong">
                <div className="grid h-10 w-10 place-items-center rounded-lg bg-accent-soft text-accent"><p.icon className="h-5 w-5" /></div>
                <h3 className="mt-4 font-semibold">{p.name}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="py-20">
        <div className="mx-auto grid max-w-7xl gap-12 px-4 sm:px-6 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <p className="text-sm font-semibold text-accent">Market data & screening</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Built for serious market analysis.</h2>
            <p className="mt-3 text-fg-2">Dense where it matters, quiet everywhere else. Market data and analytical signals are always kept visibly separate.</p>
            <div className="mt-6 flex items-center gap-3 text-sm text-fg-2">
              <Shield className="h-5 w-5 text-up" /> Secure sign-in with server-side sessions
            </div>
            <div className="mt-3 flex items-center gap-3 text-sm text-fg-2">
              <LineChart className="h-5 w-5 text-accent" /> Intraday to 1-year charts with pattern overlays
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.title} className="card p-5">
                <f.icon className="h-5 w-5 text-accent" />
                <h3 className="mt-3 font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-line bg-bg-elev py-16">
        <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-6 px-4 sm:px-6 md:flex-row md:items-center">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Ready when the market is.</h2>
            <p className="mt-1 text-fg-2">Sign in to open the market dashboard and the breakout scanner.</p>
          </div>
          <Link to={cta} className="btn-primary px-5 py-2.5">Start Analyzing the Market <ArrowRight className="h-4 w-4" /></Link>
        </div>
      </section>

      <footer className="border-t border-line py-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 sm:px-6 md:flex-row md:items-center md:justify-between">
          <Logo />
          <Disclaimer className="max-w-xl" />
        </div>
      </footer>
    </div>
  );
}
