from __future__ import annotations


class AegisError(Exception):
    reason_code = "AEGIS_ERROR"


class EligibilityError(AegisError):
    reason_code = "ELIGIBILITY_FAILED"


class OrderRejected(AegisError):
    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class ReconciliationError(AegisError):
    reason_code = "RECONCILIATION_FAILED"
