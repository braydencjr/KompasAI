type RingProps = {
  value: number;
  size?: number;
  stroke?: number;
  tone?: "blue" | "muted";
};

export default function Ring({ value, size = 64, stroke = 5, tone = "blue" }: RingProps) {
  const r = (size - stroke) / 2 - 3;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - value / 100);
  const tickR = size / 2 - 1;
  const tickC = 2 * Math.PI * tickR;

  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* instrument-style tick marks around the dial */}
        <circle cx={size / 2} cy={size / 2} r={tickR} className="ring-ticks" strokeWidth={1.5}
          strokeDasharray={`1 ${tickC / 48 - 1}`} />
        <circle cx={size / 2} cy={size / 2} r={r} className="ring-track" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          className={`ring-value ring-${tone}`}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="ring-label">{value}%</span>
    </div>
  );
}
