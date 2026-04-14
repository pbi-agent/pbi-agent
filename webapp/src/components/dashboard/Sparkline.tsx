/**
 * Inline SVG sparkline — no external dependencies.
 *
 * Renders a polyline + gradient area fill for a series of numeric values.
 */

import { useId } from "react";

type SparklineProps = {
  values: number[];
  width?: number;
  height?: number;
  /** CSS colour for the line. Defaults to the accent token. */
  color?: string;
};

export function Sparkline({
  values,
  width = 120,
  height = 32,
  color = "var(--color-accent)",
}: SparklineProps) {
  const gradientId = useId();

  if (values.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="sparkline sparkline--empty"
      />
    );
  }

  const pad = 2;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;

  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;

  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * innerW;
    const y = pad + innerH - ((v - min) / range) * innerH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polyline = points.join(" ");

  // Area fill: close the path along the bottom edge.
  const first = points[0];
  const last = points[points.length - 1];
  const areaPath = [
    `M${first}`,
    ...points.slice(1).map((p) => `L${p}`),
    `L${last.split(",")[0]},${height}`,
    `L${first.split(",")[0]},${height}`,
    "Z",
  ].join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="sparkline"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.25} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <polyline
        points={polyline}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
