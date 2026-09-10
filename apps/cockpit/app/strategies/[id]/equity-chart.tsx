"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { CHART_THEME } from "../../chart-theme";

export type EquityPoint = { date: string; nav: string };

function toTime(dateStr: string): UTCTimestamp {
  return (new Date(`${dateStr}T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

export default function EquityChart({
  equityCurve,
  benchmarkCurve,
}: {
  equityCurve: EquityPoint[];
  benchmarkCurve: EquityPoint[] | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const strategyRef = useRef<ISeriesApi<"Line"> | null>(null);
  const benchmarkRef = useRef<ISeriesApi<"Line"> | null>(null);

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
      rightPriceScale: { borderColor: CHART_THEME.border },
      timeScale: { borderColor: CHART_THEME.border },
      autoSize: true,
      height: 320,
    });
    chartRef.current = chart;
    strategyRef.current = chart.addLineSeries({
      color: CHART_THEME.accent,
      lineWidth: 2,
      title: "Strategy NAV",
    });
    benchmarkRef.current = chart.addLineSeries({
      color: CHART_THEME.benchmark,
      lineWidth: 1,
      lineStyle: 2,
      title: "Equal-Weight benchmark NAV",
    });

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!strategyRef.current) return;
    strategyRef.current.setData(
      equityCurve.map((point) => ({ time: toTime(point.date), value: Number(point.nav) })),
    );
    benchmarkRef.current?.setData(
      (benchmarkCurve ?? []).map((point) => ({
        time: toTime(point.date),
        value: Number(point.nav),
      })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [equityCurve, benchmarkCurve]);

  return <div ref={containerRef} className="chart-box" style={{ width: "100%" }} />;
}
