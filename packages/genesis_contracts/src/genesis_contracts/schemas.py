from .models import AnalysisResponse, BehaviorAnalysisResponse, FlowsDocument

PUBLIC_MODELS = {
    "analysis-response.schema.json": AnalysisResponse,
    "flows.schema.json": FlowsDocument,
}


def public_schemas(version="0.1.0") -> dict[str, dict[str, object]]:
    if version not in {"0.1.0", "0.2.0"}:
        raise ValueError("unsupported public schema version")
    models = (
        PUBLIC_MODELS
        if version == "0.1.0"
        else {"analysis-response.schema.json": BehaviorAnalysisResponse}
    )
    return {
        filename: model.model_json_schema(mode="validation") for filename, model in models.items()
    }
