from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class QuantumRunRecord:
    run_type: str
    event_type: str
    asset_class: str
    preset: str
    shots: int
    grid_points: int
    objective: float
    exact_objective: float
    delta_vs_exact: float
    status: str
    transpile_level: int = 1
    mitigation: str = "none"
    latency_ms: float = 0.0
    repeated_run_std: float = 0.0
    bitstring: str = ""
    generated_at: str = ""
    source_file: str = ""
    problem: str = ""
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
