from pathlib import Path

from aegis.backtesting.sprint2 import Sprint2ResearchScenarioRunner


runner = Sprint2ResearchScenarioRunner(Path("sample_data/sprint_2"))
report = runner.run_trend_following_scenario()
print(
    {
        "scenario": report.scenario,
        "classification": report.classification,
        "ending_nav": report.ending_nav,
        "total_return": report.total_return,
        "cash_weight": report.cash_weight,
        "position_count": report.position_count,
        "warnings": report.warnings,
        "settlement_restriction_demo": runner.settlement_restriction_demo(),
    }
)
