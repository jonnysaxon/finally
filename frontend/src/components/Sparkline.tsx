// Tiny inline SVG sparkline — no chart lib for a 40-point line. Colored by net
// direction over the window (last vs first). Renders nothing meaningful until
// the SSE stream has accumulated a couple of points (PLAN §13.12).

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
}

export function Sparkline({ data, width = 84, height = 26 }: SparklineProps) {
  if (data.length < 2) {
    return (
      <svg width={width} height={height} className="opacity-40" aria-hidden>
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#5c6878"
          strokeWidth={1}
          strokeDasharray="2 3"
        />
      </svg>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1);

  const points = data
    .map((v, i) => {
      const x = i * stepX;
      // Pad 2px top/bottom so peaks aren't clipped.
      const y = height - 2 - ((v - min) / span) * (height - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const up = data[data.length - 1] >= data[0];
  const stroke = up ? "#1fd49a" : "#ff5d6c";
  const lastX = (data.length - 1) * stepX;
  const lastY =
    height - 2 - ((data[data.length - 1] - min) / span) * (height - 4);

  return (
    <svg width={width} height={height} aria-hidden className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.4}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={lastX} cy={lastY} r={1.8} fill={stroke} />
    </svg>
  );
}
