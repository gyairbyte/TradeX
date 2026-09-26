"""Setup specification and interface contract for day trading research (DAYTRADE-001A)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from .models import (
    MultiResolutionSeries,
    Resolution,
    SetupEvaluationResult,
)


class DaytradeSetup(ABC):
    """Abstract interface defining a concrete multi-resolution day-trading setup specification.

    Ensures strategy logic remains explicit, parameterized, and decoupled from
    data ingestion and evaluation infrastructure.
    """

    @property
    @abstractmethod
    def setup_id(self) -> str:
        """Unique identifier for the setup (e.g. 'SYNTH-DAYTRADE-001')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Version of the setup specification (e.g. '0.1.0')."""
        ...

    @property
    @abstractmethod
    def required_resolutions(self) -> frozenset[Resolution]:
        """Set of resolutions strictly required for evaluation."""
        ...

    @property
    def is_synthetic(self) -> bool:
        """Indicates whether this setup is an example/synthetic test harness."""
        return False

    @property
    def production_promotion_eligible(self) -> bool:
        """Strict governance guard: defaults to False for research setups."""
        return False

    @abstractmethod
    def evaluate(
        self, series: MultiResolutionSeries, as_of: datetime
    ) -> SetupEvaluationResult:
        """Evaluate the setup against a point-in-time materialized MultiResolutionSeries.

        Args:
            series: Newly materialized MultiResolutionSeries containing only data available
                    at or before as_of.
            as_of: Timezone-aware timestamp defining the evaluation decision point.

        Returns:
            SetupEvaluationResult indicating detection, non-detection, or invalid input.
        """
        ...
