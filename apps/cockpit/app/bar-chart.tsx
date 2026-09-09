type BarDatum = { label: string; value: number; tone?: "pos" | "neg" };

export default function BarChart({
  data,
  formatValue,
}: {
  data: BarDatum[];
  formatValue?: (value: number) => string;
}) {
  if (data.length === 0) return null;
  const max = Math.max(...data.map((d) => Math.abs(d.value)), 0.0001);
  const format = formatValue ?? ((v: number) => v.toFixed(2));

  return (
    <div className="bar-chart">
      {data.map((datum) => {
        const tone = datum.tone ?? (datum.value >= 0 ? "pos" : "neg");
        const heightPct = Math.max((Math.abs(datum.value) / max) * 100, 3);
        return (
          <div className="bar-chart-col" key={datum.label}>
            <div className="bar-chart-value">{format(datum.value)}</div>
            <div className="bar-chart-track">
              <div className={`bar-chart-bar ${tone}`} style={{ height: `${heightPct}%` }} />
            </div>
            <div className="bar-chart-label">{datum.label}</div>
          </div>
        );
      })}
    </div>
  );
}
