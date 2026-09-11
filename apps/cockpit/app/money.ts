/** One shared rupee formatter, replacing 6 near-identical copies that had
 * drifted (0 vs 2 fraction digits, string vs number input) and none of
 * which guarded against a genuinely large real number -- a 20-day average
 * value traded of ~₹395 crore rendered as "₹3,95,12,41,779.84" and broke a
 * KPI card's layout. `compact` renders real Indian-market scale (Lakh/Crore)
 * for aggregate figures (AUM, NAV, value traded) where that's the natural
 * unit; per-share prices should omit it so they still read as plain rupees. */
export function money(
  value: string | number | null | undefined,
  opts?: { compact?: boolean; maximumFractionDigits?: number },
): string {
  if (value === null || value === undefined) return "not available";
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) return "not available";

  if (opts?.compact) {
    const abs = Math.abs(num);
    if (abs >= 1e7) {
      return `₹${(num / 1e7).toLocaleString("en-IN", { maximumFractionDigits: 2 })} Cr`;
    }
    if (abs >= 1e5) {
      return `₹${(num / 1e5).toLocaleString("en-IN", { maximumFractionDigits: 2 })} L`;
    }
  }

  return `₹${num.toLocaleString("en-IN", { maximumFractionDigits: opts?.maximumFractionDigits ?? 2 })}`;
}
