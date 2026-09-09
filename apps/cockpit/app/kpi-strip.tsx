type IconComponent = React.ComponentType<{ size?: number; strokeWidth?: number }>;

export function KpiStrip({ children }: { children: React.ReactNode }) {
  return <div className="kpi-strip">{children}</div>;
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  delta,
  caption,
}: {
  icon: IconComponent;
  label: string;
  value: string;
  delta?: { text: string; tone: "pos" | "neg" } | null;
  caption?: string;
}) {
  return (
    <div className="kpi-card">
      <div className="kpi-card-head">
        <span className="kpi-card-label">{label}</span>
        <Icon size={16} strokeWidth={2} />
      </div>
      <div className="kpi-card-value">{value}</div>
      {(delta || caption) && (
        <div className="kpi-card-foot">
          {delta && <span className={`delta-pill ${delta.tone}`}>{delta.text}</span>}
          {caption && <span className="kpi-card-caption">{caption}</span>}
        </div>
      )}
    </div>
  );
}
