from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Health:
    status: str
    service: str


class GetHealth:
    def __init__(self, service_name: str) -> None:
        self._service_name = service_name

    def execute(self) -> Health:
        return Health(status="ok", service=self._service_name)
