from .business_map import BusinessMap
from .change_report import ChangeReport
from .evidence_bundle import EvidenceBundle
from .map_tasks import ChangeSubmission, FlowSubmission, MapPlan
from .models import AnalysisResponse, BehaviorAnalysisResponse, FlowsDocument, PathAnalysisResponse

PUBLIC_MODELS = {
    "analysis-response.schema.json": AnalysisResponse,
    "flows.schema.json": FlowsDocument,
}
# Draft artifacts of the local map workflow; versioned apart from the report schemas.
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


def public_schemas(version="0.1.0") -> dict[str, dict[str, object]]:
    if version not in {"0.1.0", "0.2.0", "0.3.0"}:
        raise ValueError("unsupported public schema version")
    models = (
        PUBLIC_MODELS
        if version == "0.1.0"
        else {
            "analysis-response.schema.json": BehaviorAnalysisResponse
            if version == "0.2.0"
            else PathAnalysisResponse
        }
    )
    return {
        filename: model.model_json_schema(mode="validation") for filename, model in models.items()
    }
