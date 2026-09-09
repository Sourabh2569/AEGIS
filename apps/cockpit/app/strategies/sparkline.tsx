const WIDTH = 84;
const HEIGHT = 28;

export default function Sparkline({
  values,
  tone,
}: {
  values: string[];
  tone: "pos" | "neg";
}) {
  const numbers = values.map(Number);
  if (numbers.length < 2) return null;

  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  const range = max - min || 1;
  const stepX = WIDTH / (numbers.length - 1);

  const points = numbers
    .map((value, index) => {
      const x = index * stepX;
      const y = HEIGHT - ((value - min) / range) * HEIGHT;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const color = tone === "pos" ? "var(--buy)" : "var(--sell)";

  return (
    <svg
      className="sparkline"
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      aria-hidden="true"
    >
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.6} />
    </svg>
  );
}
