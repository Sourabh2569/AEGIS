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
import type { IndicatorPoint } from "./price-chart";

function toTime(dateStr: string): UTCTimestamp {
  return (new Date(`${dateStr}T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

export default function MomentumChart({ indicators }: { indicators: IndicatorPoint[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

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
      height: 120,
    });
    chartRef.current = chart;
    seriesRef.current = chart.addHistogramSeries({ title: "60-day momentum" });

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(
      indicators
        .filter((point) => point.momentum_60 !== null)
        .map((point) => ({
          time: toTime(point.date),
          value: point.momentum_60 as number,
          color: (point.momentum_60 as number) >= 0 ? CHART_THEME.buy : CHART_THEME.sell,
        })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [indicators]);

  return <div ref={containerRef} className="momentum-box" style={{ width: "100%" }} />;
}
