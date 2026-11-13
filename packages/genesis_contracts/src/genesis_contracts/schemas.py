from .business_map import BusinessMap
from .change_report import ChangeReport
from .evidence_bundle import EvidenceBundle
from .map_tasks import ChangeSubmission, FlowSubmission, MapPlan

# Draft artifacts of the local map workflow.
MAP_MODELS = {
    "business-map.schema.json": BusinessMap,
    "change-report.schema.json": ChangeReport,
    "evidence-bundle.schema.json": EvidenceBundle,
    "map-plan.schema.json": MapPlan,
    "flow-submission.schema.json": FlowSubmission,
    "change-submission.schema.json": ChangeSubmission,
}


def map_schemas(version="0.1.0") -> dict[str, dict[str, object]]:
    if version != "0.1.0":
        raise ValueError("unsupported map schema version")
    return {
        filename: model.model_json_schema(mode="validation")
        for filename, model in MAP_MODELS.items()
    }
