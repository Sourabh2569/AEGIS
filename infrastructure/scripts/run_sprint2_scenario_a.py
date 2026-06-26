from pathlib import Path

from aegis.backtesting.sprint2 import Sprint2ResearchScenarioRunner


report = Sprint2ResearchScenarioRunner(Path("sample_data/sprint_2")).run_equal_weight_scenario()
print(
    {
        "scenario": report.scenario,
        "classification": report.classification,
        "ending_nav": report.ending_nav,
        "total_return": report.total_return,
        "cash_weight": report.cash_weight,
        "gross_equity_exposure": report.gross_equity_exposure,
        "total_transaction_cost": report.total_transaction_cost,
        "position_count": report.position_count,
        "risk_decisions": [assessment.decision for assessment in report.risk_assessments],
        "warnings": report.warnings,
    }
)
