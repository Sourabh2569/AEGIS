from __future__ import annotations

from aegis.domain.models import ExperimentManifest


class ResearchRegistryService:
    def __init__(self) -> None:
        self.manifests: dict[str, ExperimentManifest] = {}

    def create_manifest(self, manifest: ExperimentManifest) -> ExperimentManifest:
        self.manifests[manifest.id] = manifest
        return manifest

    def freeze_manifest(self, manifest_id: str) -> ExperimentManifest:
        frozen = self.manifests[manifest_id].freeze()
        self.manifests[manifest_id] = frozen
        return frozen

    def update_primary_metric(self, manifest_id: str, primary_metric: str) -> ExperimentManifest:
        updated = self.manifests[manifest_id].update_metric(primary_metric)
        self.manifests[manifest_id] = updated
        return updated
