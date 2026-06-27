from __future__ import annotations

from dataclasses import replace

from aegis.domain.models import CorporateAction, CorporateActionVerificationStatus


class CorporateActionService:
    def __init__(self) -> None:
        self.actions: dict[str, CorporateAction] = {}

    def create(self, action: CorporateAction) -> CorporateAction:
        self.actions[action.id] = action
        return action

    def verify(self, action_id: str) -> CorporateAction:
        action = self.actions[action_id]
        verified = replace(action, verification_status=CorporateActionVerificationStatus.VERIFIED)
        self.actions[action_id] = verified
        return verified

    def can_impact_curated_dataset(self, action_id: str) -> bool:
        return (
            self.actions[action_id].verification_status
            == CorporateActionVerificationStatus.VERIFIED
        )
