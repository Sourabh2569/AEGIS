from __future__ import annotations

from aegis.domain.models import ProviderLicense, ProviderLicenseStatus


class ProviderLicenseGuard:
    blocked_statuses = {ProviderLicenseStatus.EXPIRED, ProviderLicenseStatus.REJECTED}

    def assert_ingestion_allowed(self, license_: ProviderLicense | None) -> None:
        if license_ is None:
            raise PermissionError("Provider has no license record; ingestion is blocked.")
        if license_.license_status in self.blocked_statuses:
            raise PermissionError(
                f"Provider license is {license_.license_status}; ingestion is blocked."
            )
        if license_.license_status != ProviderLicenseStatus.APPROVED:
            raise PermissionError(
                f"Provider license is {license_.license_status}; Sprint 0 ingestion requires APPROVED."
            )
