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
import { CHART_THEME } from "../../chart-theme";

export type Bar = { date: string; open: number; high: number; low: number; close: number };
export type IndicatorPoint = {
  date: string;
  close: number | null;
  sma_50: number | null;
  sma_200: number | null;
  momentum_60: number | null;
  atr_14: number | null;
};
export type RuleEvent = { date: string; type: "ELIGIBILITY_START" | "ELIGIBILITY_END" };

function toTime(dateStr: string): UTCTimestamp {
  return (new Date(`${dateStr}T00:00:00Z`).getTime() / 1000) as UTCTimestamp;
}

export default function PriceChart({
  bars,
  indicators,
  ruleEvents,
}: {
  bars: Bar[];
  indicators: IndicatorPoint[];
  ruleEvents: RuleEvent[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const sma50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const sma200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const atrUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const atrLowerRef = useRef<ISeriesApi<"Line"> | null>(null);

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
      height: 360,
    });
    chartRef.current = chart;

    candleSeriesRef.current = chart.addCandlestickSeries({
      upColor: CHART_THEME.buy,
      downColor: CHART_THEME.sell,
      borderVisible: false,
      wickUpColor: CHART_THEME.buy,
      wickDownColor: CHART_THEME.sell,
    });
    sma50Ref.current = chart.addLineSeries({
      color: CHART_THEME.accent,
      lineWidth: 1,
      title: "SMA 50",
    });
    sma200Ref.current = chart.addLineSeries({
      color: CHART_THEME.hold,
      lineWidth: 1,
      title: "SMA 200",
    });
    atrUpperRef.current = chart.addLineSeries({
      color: CHART_THEME.benchmark,
      lineWidth: 1,
      lineStyle: 2,
      title: "+2 ATR",
    });
    atrLowerRef.current = chart.addLineSeries({
      color: CHART_THEME.benchmark,
      lineWidth: 1,
      lineStyle: 2,
      title: "-2 ATR",
    });

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!candleSeriesRef.current) return;
    candleSeriesRef.current.setData(
      bars.map((bar) => ({
        time: toTime(bar.date),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    );

    const sma50 = indicators
      .filter((point) => point.sma_50 !== null)
      .map((point) => ({ time: toTime(point.date), value: point.sma_50 as number }));
    const sma200 = indicators
      .filter((point) => point.sma_200 !== null)
      .map((point) => ({ time: toTime(point.date), value: point.sma_200 as number }));
    const atrBandPoints = indicators.filter(
      (point) => point.close !== null && point.atr_14 !== null,
    );
    sma50Ref.current?.setData(sma50);
    sma200Ref.current?.setData(sma200);
    atrUpperRef.current?.setData(
      atrBandPoints.map((point) => ({
        time: toTime(point.date),
        value: (point.close as number) + 2 * (point.atr_14 as number),
      })),
    );
    atrLowerRef.current?.setData(
      atrBandPoints.map((point) => ({
        time: toTime(point.date),
        value: (point.close as number) - 2 * (point.atr_14 as number),
      })),
    );

    candleSeriesRef.current.setMarkers(
      ruleEvents.map((event) => ({
        time: toTime(event.date),
        position: event.type === "ELIGIBILITY_START" ? "belowBar" : "aboveBar",
        color: event.type === "ELIGIBILITY_START" ? CHART_THEME.buy : CHART_THEME.sell,
        shape: event.type === "ELIGIBILITY_START" ? "arrowUp" : "arrowDown",
        text: event.type === "ELIGIBILITY_START" ? "Rule fired" : "Rule ended",
      })),
    );

    chartRef.current?.timeScale().fitContent();
  }, [bars, indicators, ruleEvents]);

  return <div ref={containerRef} className="chart-box" style={{ width: "100%" }} />;
}
