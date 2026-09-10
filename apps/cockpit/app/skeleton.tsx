export function Skeleton({
  width = "100%",
  height = 16,
  radius = 6,
}: {
  width?: string | number;
  height?: string | number;
  radius?: number;
}) {
  return (
    <div
      className="skeleton"
      style={{ width, height, borderRadius: radius }}
      aria-hidden="true"
    />
  );
}

export function KpiStripSkeleton({ count }: { count: number }) {
  return (
    <div className="kpi-strip">
      {Array.from({ length: count }, (_, index) => (
        <div className="kpi-card" key={index}>
          <div className="kpi-card-head">
            <Skeleton width={70} height={11} />
            <Skeleton width={16} height={16} radius={4} />
          </div>
          <Skeleton width="60%" height={24} />
        </div>
      ))}
    </div>
  );
}

export function PanelSkeleton({ lines }: { lines: number }) {
  return (
    <div className="panel">
      <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} height={14} width={index % 2 === 0 ? "100%" : "70%"} />
        ))}
      </div>
    </div>
  );
}
