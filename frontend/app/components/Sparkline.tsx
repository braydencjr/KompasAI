export default function Sparkline({ values, width = 96, height = 32 }: { values: number[]; width?: number; height?: number }) {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * (width - 4) + 2;
    const y = height - 3 - ((v - min) / (max - min || 1)) * (height - 6);
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x},${y}`).join(" ");
  const [lx, ly] = pts[pts.length - 1];

  return (
    <svg className="spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <polygon className="spark-area" points={`2,${height} ${line} ${lx},${height}`} />
      <polyline className="spark-line" points={line} />
      <circle className="spark-dot" cx={lx} cy={ly} r={2.5} />
    </svg>
  );
}
