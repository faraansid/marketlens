export type Trend = "Strong Uptrend" | "Uptrend" | "Neutral" | "Downtrend" | "Strong Downtrend";
export type PatternKey = "uptrend" | "downtrend" | "falling_wedge" | "vcp" | "breakout";
export type PatternStatus = "forming" | "potential" | "confirmed" | "failed" | "active";

export interface User {
  id: number;
  username: string | null;
  fullName: string | null;
  isAdmin: boolean;
}

export interface ManagedUser {
  id: number;
  username: string | null;
  fullName: string | null;
  isOwner: boolean;
  isActive: boolean;
  createdAt: string | null;
  lastLoginAt: string | null;
}

export interface JobRun {
  id: number;
  status: "running" | "success" | "partial" | "failed" | "skipped";
  trigger: string;
  startedAt: string | null;
  finishedAt: string | null;
  symbolsOk: number;
  symbolsFailed: number;
  detections: number;
  message: string | null;
  error: string | null;
}

export interface MarketStatus {
  market: { state: "open" | "closed" | "pre_open"; label: string };
  lastSuccessfulUpdate: string | null;
  lastRun: JobRun | null;
  isRefreshing: boolean;
  nextScheduledRun: string | null;
  refreshIntervalMinutes: number;
  serverTime: string;
}

export interface Instrument {
  key: string;
  name: string;
  symbol: string;
  category: "index" | "fx" | "commodity" | "volatility";
  unit: string | null;
  value: number | null;
  prevClose: number | null;
  change: number | null;
  changePct: number | null;
  sparkline: number[];
  sparklineLabel: string | null;
  marketTime: string | null;
  updatedAt: string | null;
  stale: boolean;
}

export interface MarketOverview {
  instruments: Instrument[];
  breadth: { total: number; advancers: number; decliners: number; asOf: string | null };
  patternCounts: Partial<Record<PatternKey, number>>;
}

export interface Equity {
  symbol: string;
  name: string;
  price: number | null;
  prevClose: number | null;
  oneDayChange: number | null;
  oneWeekChange: number | null;
  oneMonthChange: number | null;
  volume: number | null;
  avgVolumeWeek: number | null;
  avgVolume50d: number | null;
  volumeRatio: number | null;
  marketCap: number | null;
  high52w: number | null;
  low52w: number | null;
  rsRating: number | null;
  trend: Trend | null;
  trendScore: number | null;
  signals: string[];
  lastBarDate: string | null;
  asOf: string | null;
}

export interface Page<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  lastUpdated?: string | null;
}

export interface Detection {
  id: number;
  symbol: string;
  name: string | null;
  pattern: PatternKey;
  patternLabel: string;
  status: PatternStatus;
  confidenceScore: number;
  currentPrice: number | null;
  support: number | null;
  resistance: number | null;
  breakoutLevel: number | null;
  volumeCurrent: number | null;
  volumeAvg: number | null;
  volumeRatio: number | null;
  trend: Trend | null;
  metrics: Record<string, unknown>;
  chart: number[];
  detectedAt: string;
  marketCap: number | null;
  oneDayChange: number | null;
  signal?: { firstDetectedAt: string | null; confirmedAt: string | null; failedAt: string | null; lastSeenAt: string | null };
}

export interface EquityDetail {
  company: {
    symbol: string;
    name: string;
    isin: string | null;
    series: string | null;
    listingDate: string | null;
    isEligible: boolean;
    eligibilityNote: string | null;
    sharesOutstanding: number | null;
  };
  snapshot: Equity | null;
  technicals: {
    sma20: number | null;
    sma50: number | null;
    sma200: number | null;
    atr14Pct: number | null;
    rsRating: number | null;
    high52w: number | null;
    low52w: number | null;
  };
  trend: { label: Trend; score: number; components: Record<string, number | null> } | null;
  patterns: Detection[];
}

export interface Bar {
  t: string | number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number | null;
}

export interface ChartData {
  timeframe: string;
  interval: string;
  source: "stored" | "live";
  bars: Bar[];
  asOf: string;
}
