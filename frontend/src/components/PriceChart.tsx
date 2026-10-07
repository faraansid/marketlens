import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type Time,
} from "lightweight-charts";
import { cssVar, useTheme } from "../lib/theme";
import type { Bar } from "../lib/types";

export interface Level {
  price: number;
  label: string;
  kind: "support" | "resistance" | "breakout";
}

export interface TrendLine {
  points: [string, number][]; // [isoDate, price]
  kind: "support" | "resistance";
}

/**
 * Candlestick price chart with a volume histogram pane underneath, horizontal
 * support/resistance/breakout levels and optional pattern trendlines.
 */
export function PriceChart({ bars, levels = [], lines = [], height = 420 }: {
  bars: Bar[]; levels?: Level[]; lines?: TrendLine[]; height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const up = cssVar("--up"), down = cssVar("--down"), muted = cssVar("--muted"), line = cssVar("--line");
    const chart: IChartApi = createChart(el, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: muted, fontFamily: "Inter, sans-serif", fontSize: 11 },
      grid: { vertLines: { color: line }, horzLines: { color: line } },
      rightPriceScale: { borderColor: line, scaleMargins: { top: 0.08, bottom: 0.28 } },
      timeScale: { borderColor: line, timeVisible: typeof bars[0]?.t === "number", secondsVisible: false },
      crosshair: { mode: 0 },
      localization: { priceFormatter: (p: number) => p.toLocaleString("en-IN", { maximumFractionDigits: 2 }) },
    });

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down,
    });
    candles.setData(bars.map((b) => ({ time: b.t as Time, open: b.o, high: b.h, low: b.l, close: b.c })));

    const vol = chart.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
    vol.setData(
      bars.filter((b) => b.v !== null).map((b) => ({
        time: b.t as Time, value: b.v as number, color: (b.c >= b.o ? up : down) + "66",
      })),
    );

    const colors = { support: up, resistance: down, breakout: cssVar("--accent") };
    for (const lv of levels) {
      candles.createPriceLine({
        price: lv.price, color: colors[lv.kind], lineWidth: 1,
        lineStyle: lv.kind === "breakout" ? LineStyle.Solid : LineStyle.Dashed, axisLabelVisible: true, title: lv.label,
      });
    }
    // Pattern trendlines only make sense on daily bars (they are keyed by date).
    if (typeof bars[0]?.t === "string") {
      const first = bars[0].t as string;
      for (const tl of lines) {
        const pts = tl.points.filter(([d]) => d >= first);
        if (pts.length < 2) continue;
        const s = chart.addSeries(LineSeries, { color: colors[tl.kind], lineWidth: 2, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
        s.setData(pts.map(([d, p]) => ({ time: d as Time, value: p })));
      }
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars, levels, lines, height, theme]);

  return <div ref={ref} style={{ height }} className="w-full" />;
}
