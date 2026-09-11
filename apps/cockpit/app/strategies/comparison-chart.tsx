"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { CHART_THEME } from "../chart-theme";

export type EquityPoint = { date: string; nav: string };
export type ComparisonCurve = {
  label: string;
  color: string;
  lineWidth: 1 | 2;
  lineStyle: 0 | 2;
  points: EquityPoint[];
};

function toTime(dateStr: string): UTCTimestamp {
  return (new Date(`${dateStr}T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

/** Real backtest NAV, overlaid across every strategy that has one, with
 * actual calendar dates -- replaces trying to compare shape-only sparklines
 * (no time axis) by eye across separate leaderboard cards. */
export default function ComparisonChart({ curves }: { curves: ComparisonCurve[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Line">[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_THEME.background },
        textColor: CHART_THEME.text,
        fontFamily: "ui-monospace, SF Mono, Menlo, monospace",
      },
      grid: {
        vertLines: { color: CHART_THEME.grid },
        horzLines: { color: CHART_THEME.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: CHART_THEME.border },
      timeScale: { borderColor: CHART_THEME.border },
      autoSize: true,
      height: 280,
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      // Series objects die with the chart -- drop the stale refs too, or a
      // remount (React Strict Mode double-invokes this in dev) tries to
      // remove series that belonged to the now-disposed chart instance.
      seriesRef.current = [];
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    seriesRef.current.forEach((series) => chart.removeSeries(series));
    seriesRef.current = curves.map((curve) => {
      const series = chart.addLineSeries({
        color: curve.color,
        lineWidth: curve.lineWidth,
        lineStyle: curve.lineStyle,
        title: curve.label,
      });
      series.setData(
        curve.points.map((point) => ({ time: toTime(point.date), value: Number(point.nav) })),
      );
      return series;
    });
    chart.timeScale().fitContent();
  }, [curves]);

  return <div ref={containerRef} className="chart-box" style={{ width: "100%" }} />;
}
