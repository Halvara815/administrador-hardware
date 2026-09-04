from datetime import UTC, datetime
from unittest import TestCase

from hardware_admin.domain.models import (
    ComponentKind,
    ComponentResult,
    EvidenceRecord,
    HealthStatus,
)


class ComponentResultTests(TestCase):
    def test_problem_result_keeps_its_evidence(self) -> None:
        evidence = EvidenceRecord(
            source="PowerShell",
            query="Get-PnpDevice -PresentOnly",
            output="USB Mass Storage Device | Error | Código 43",
            collected_at=datetime.now(UTC),
        )

        result = ComponentResult(
            component=ComponentKind.USB,
            name="USB Mass Storage Device",
            facts={"problem_code": 43},
            status=HealthStatus.CRITICAL,
            possible_problem="Driver o configuración",
            evidence=(evidence,),
        )

        self.assertIs(result.status, HealthStatus.CRITICAL)
        self.assertEqual(result.evidence, (evidence,))
        self.assertEqual(result.facts["problem_code"], 43)
