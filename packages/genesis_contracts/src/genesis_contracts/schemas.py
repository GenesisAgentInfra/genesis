from .models import AnalysisResponse, BehaviorAnalysisResponse, FlowsDocument, PathAnalysisResponse

PUBLIC_MODELS = {
    "analysis-response.schema.json": AnalysisResponse,
    "flows.schema.json": FlowsDocument,
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
