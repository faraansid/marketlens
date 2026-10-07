import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api, qs } from "./api";
import type { ChartData, Detection, Equity, EquityDetail, MarketOverview, MarketStatus, Page } from "./types";

/*
 * Data freshness: the backend refreshes market data on a server-side schedule.
 * The UI does not poll for market data; it fetches processed results on
 * navigation / focus and lets React Query reuse them for a few minutes.
 */
const STALE = 5 * 60_000;

export function useMarketStatus() {
  return useQuery({ queryKey: ["market-status"], queryFn: () => api<MarketStatus>("/api/market/status"), staleTime: 60_000 });
}

export function useMarketOverview() {
  return useQuery({ queryKey: ["market-overview"], queryFn: () => api<MarketOverview>("/api/market/overview"), staleTime: STALE });
}

export interface EquityQuery {
  search?: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
  pageSize: number;
  trend?: string;
}

export function useEquities(p: EquityQuery) {
  return useQuery({
    queryKey: ["equities", p],
    queryFn: () => api<Page<Equity>>(`/api/equities${qs({ ...p })}`),
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useEquity(symbol: string) {
  return useQuery({
    queryKey: ["equity", symbol],
    queryFn: () => api<EquityDetail>(`/api/equities/${encodeURIComponent(symbol)}`),
    staleTime: STALE,
  });
}

export function useChart(symbol: string, tf: string) {
  return useQuery({
    queryKey: ["chart", symbol, tf],
    queryFn: () => api<ChartData>(`/api/equities/${encodeURIComponent(symbol)}/chart${qs({ tf })}`),
    staleTime: ["INTRADAY", "1D", "1W"].includes(tf) ? 60_000 : STALE,
    placeholderData: keepPreviousData,
    retry: 1,
  });
}

export interface PatternQuery {
  pattern?: string;
  status?: string;
  minConfidence?: number;
  trend?: string;
  minMarketCapCr?: number;
  maxMarketCapCr?: number;
  minPrice?: number;
  maxPrice?: number;
  minVolumeRatio?: number;
  search?: string;
  sort: string;
  order: "asc" | "desc";
  page: number;
  pageSize: number;
}

export function usePatterns(p: PatternQuery) {
  return useQuery({
    queryKey: ["patterns", p],
    queryFn: () => api<Page<Detection>>(`/api/patterns${qs({ ...p })}`),
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export type PatternSummary = Record<string, { total: number; byStatus: Record<string, number> }>;
export function usePatternSummary() {
  return useQuery({ queryKey: ["pattern-summary"], queryFn: () => api<PatternSummary>("/api/patterns/summary"), staleTime: STALE });
}
