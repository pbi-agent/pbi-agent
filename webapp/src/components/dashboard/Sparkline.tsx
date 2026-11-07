/**
 * Inline SVG sparkline — no external dependencies.
 *
 * Renders a polyline + gradient area fill for a series of numeric values.
 */

import { useId } from "react";
import { cn } from "@/lib/utils";

type SparklineProps = {
  values: number[];
  width?: number;
  height?: number;
  /** Text-colour utility driving the stroke via currentColor. */
  className?: string;
};

export function Sparkline({
  values,
  width = 120,
  height = 32,
  className,
}: SparklineProps) {
  const gradientId = useId();

  if (values.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={cn("shrink-0 opacity-30", className)}
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
      className={cn("block shrink-0 text-chart-1", className)}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity={0.25} />
          <stop offset="100%" stopColor="currentColor" stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <polyline
        points={polyline}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
