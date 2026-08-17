"""Value objects for the LONG-002B feasibility probe."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderRequestRecord:
    """One executed request across any data family."""

    family: str
    provider: str
    symbol: str | None
    as_of_date: str | None
    endpoint_pattern: str
    http_status: int | None
    error_classification: str
    retry_count: int
    request_timestamp_utc: str
    response_summary: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "provider": self.provider,
            "symbol": self.symbol,
            "as_of_date": self.as_of_date,
            "endpoint_pattern": self.endpoint_pattern,
            "http_status": self.http_status,
            "error_classification": self.error_classification,
            "retry_count": self.retry_count,
            "request_timestamp_utc": self.request_timestamp_utc,
            "response_summary": self.response_summary,
            "provenance": self.provenance,
        }


@dataclass
class DataFamilyResult:
    family: str
    disposition: str = "not_supported"
    evidence_confidence: str = "limited_but_usable_evidence"
    provider_selected: str | None = None
    provider_role: str | None = None
    blockers: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    request_count: int = 0
    records: list[ProviderRequestRecord] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "disposition": self.disposition,
            "evidence_confidence": self.evidence_confidence,
            "provider_selected": self.provider_selected,
            "provider_role": self.provider_role,
            "blockers": self.blockers,
            "limitations": self.limitations,
            "request_count": self.request_count,
            "records": [r.to_dict() for r in self.records],
            "summary": self.summary,
        }


@dataclass
class FeasibilityReport:
    task_id: str = "LONG-002B"
    overall_disposition: str = "not_supported"
    overall_evidence_confidence: str = "limited_but_usable_evidence"
    total_http_requests: int = 0
    runtime_seconds: float = 0.0
    code_commit_sha: str = ""
    preregistration_commit_sha: str = ""
    original_preregistration_commit_sha: str = ""
    rebased_preregistration_commit_sha: str = ""
    rebased_code_commit_sha: str = ""
    original_implementation_commit_sha: str = ""
    code_source_tree_sha: str = ""
    provenance_note: str = ""
    long_002_spec_sha256: str = ""
    probe_spec_sha256: str = ""
    data_contract_sha256: str = ""
    data_families: list[DataFamilyResult] = field(default_factory=list)
    recommended_next_action: str = ""
    limitations: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "overall_disposition": self.overall_disposition,
            "overall_evidence_confidence": self.overall_evidence_confidence,
            "total_http_requests": self.total_http_requests,
            "runtime_seconds": self.runtime_seconds,
            "code_commit_sha": self.code_commit_sha,
            "preregistration_commit_sha": self.preregistration_commit_sha,
            "original_preregistration_commit_sha": self.original_preregistration_commit_sha,
            "rebased_preregistration_commit_sha": self.rebased_preregistration_commit_sha,
            "rebased_code_commit_sha": self.rebased_code_commit_sha,
            "original_implementation_commit_sha": self.original_implementation_commit_sha,
            "code_source_tree_sha": self.code_source_tree_sha,
            "provenance_note": self.provenance_note,
            "long_002_spec_sha256": self.long_002_spec_sha256,
            "probe_spec_sha256": self.probe_spec_sha256,
            "data_contract_sha256": self.data_contract_sha256,
            "data_families": [f.to_dict() for f in self.data_families],
            "recommended_next_action": self.recommended_next_action,
            "limitations": self.limitations,
            "blockers": self.blockers,
        }
