from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class ReadinessProbe(Protocol):
    name: str

    async def check(self) -> bool: ...


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool


@dataclass(frozen=True)
class Readiness:
    status: str
    probes: tuple[ProbeResult, ...]


class GetReadiness:
    def __init__(self, probes: Sequence[ReadinessProbe]) -> None:
        self._probes = probes

    async def execute(self) -> Readiness:
        results: list[ProbeResult] = []
        for probe in self._probes:
            results.append(ProbeResult(name=probe.name, ok=await probe.check()))
        ok = all(item.ok for item in results) if results else True
        return Readiness(status="ok" if ok else "unavailable", probes=tuple(results))
