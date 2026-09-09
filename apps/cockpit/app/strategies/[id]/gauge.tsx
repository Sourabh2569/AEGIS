const SIZE = 120;
const STROKE = 10;
const RADIUS = (SIZE - STROKE) / 2;
// Semi-circle: half the circumference.
const HALF_CIRCUMFERENCE = Math.PI * RADIUS;

export default function Gauge({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label: string;
}) {
  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  const filled = HALF_CIRCUMFERENCE * ratio;
  const center = SIZE / 2;

  return (
    <div className="gauge">
      <svg width={SIZE} height={SIZE / 2 + 4} viewBox={`0 0 ${SIZE} ${SIZE / 2 + 4}`}>
        <path
          d={`M ${STROKE / 2} ${center} A ${RADIUS} ${RADIUS} 0 0 1 ${SIZE - STROKE / 2} ${center}`}
          fill="none"
          stroke="var(--border)"
          strokeWidth={STROKE}
          strokeLinecap="round"
        />
        <path
          d={`M ${STROKE / 2} ${center} A ${RADIUS} ${RADIUS} 0 0 1 ${SIZE - STROKE / 2} ${center}`}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${HALF_CIRCUMFERENCE}`}
        />
      </svg>
      <div className="gauge-value">
        {value} <span className="gauge-max">/ {max}</span>
      </div>
      <div className="gauge-label">{label}</div>
    </div>
  );
}
