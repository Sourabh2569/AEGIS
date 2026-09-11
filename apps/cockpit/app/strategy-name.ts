/** Shared so every screen that shows a strategy_id agrees on the same short
 * display name and the same real/benchmark distinction -- previously only
 * the Strategies page shortened these, so Overview showed the raw
 * "EqualWeightUniverseBenchmarkStrategyV0" unshortened. */
export function shortName(strategyId: string): string {
  return strategyId.replace(/(Baseline|Benchmark)?StrategyV0$/, "");
}

export function isBenchmark(strategyId: string): boolean {
  return strategyId.includes("Benchmark");
}
