/** Formatting helpers. Missing values always render as an em dash — never a fabricated number. */

export const DASH = "—";

const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function price(v: number | null | undefined, digits = 2): string {
  if (!isNum(v)) return DASH;
  if (digits === 2) return inr.format(v);
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);
}

export function pct(v: number | null | undefined, digits = 2, sign = true): string {
  if (!isNum(v)) return DASH;
  const s = v.toFixed(digits);
  return `${sign && v > 0 ? "+" : ""}${s}%`;
}

/** Indian-style compact volume: 12.4 L, 3.1 Cr, 950 K. */
export function volume(v: number | null | undefined): string {
  if (!isNum(v)) return DASH;
  if (v >= 1e7) return `${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `${(v / 1e5).toFixed(2)} L`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)} K`;
  return inr0.format(v);
}

/** Market cap in ₹ crore (input is INR). */
export function mcap(v: number | null | undefined): string {
  if (!isNum(v)) return DASH;
  const cr = v / 1e7;
  if (cr >= 1e5) return `₹${(cr / 1e5).toFixed(2)} L Cr`;
  return `₹${inr0.format(Math.round(cr))} Cr`;
}

export function ratio(v: number | null | undefined, digits = 2): string {
  return isNum(v) ? `${v.toFixed(digits)}×` : DASH;
}

export function num(v: number | null | undefined, digits = 1): string {
  return isNum(v) ? v.toFixed(digits) : DASH;
}

const dtf = new Intl.DateTimeFormat("en-IN", {
  day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata",
});
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : `${dtf.format(d)} IST`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function toneOf(v: number | null | undefined): "up" | "down" | "flat" {
  if (!isNum(v) || v === 0) return "flat";
  return v > 0 ? "up" : "down";
}
