"""Bounded HTTP transport; service failures contain no remote content."""

from __future__ import annotations

import json
import math

import httpx
from genesis_contracts.models import (
    AnalysisRequest,
    FlowDraftRequest,
    FlowDraftResponse,
    SemanticAnalysisResponse,
    ServiceError,
)
from genesis_contracts.validation import validate_flow_draft_response, validate_model_response

from .config import normalize_service_url


class SemanticFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SemanticClient:
    def __init__(self, service_url: str, api_key: str, *, transport=None, timeout: float = 310):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("client timeout must be finite and positive")
        self.url = normalize_service_url(service_url)
        self.key = api_key
        self.transport = transport
        self.timeout = timeout

    def capabilities(self) -> dict:
        """Bounded, credential-free discovery; unsupported servers use legacy mode.

        No customer context is sent and no analysis POST is retried or downgraded.
        """
        try:
            with httpx.Client(
                timeout=min(self.timeout, 3),
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                with client.stream("GET", self.url + "/capabilities") as response:
                    if response.status_code != 200:
                        return {}
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 16_384:
                            return {}
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        return {}
                    versions = data.get("behavior_view_versions", [])
                    if not isinstance(versions, list):
                        versions = []
                    if data.get("behavior_view_version") == "1":
                        versions = [*versions, "1"]
                    return {
                        "behavior_review_version": "1"
                        if data.get("behavior_review_version") == "1"
                        else None,
                        "behavior_view_versions": tuple(v for v in ("1", "2") if v in versions),
                    }
        except (httpx.HTTPError, ValueError, TypeError):
            return {}

    def _post(self, path: str, request):
        try:
            with httpx.Client(
                timeout=self.timeout,
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                with client.stream(
                    "POST",
                    self.url + path,
                    headers={"Authorization": f"Bearer {self.key}"},
                    json=request.model_dump(mode="json"),
                ) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise SemanticFailure("provider_output_invalid")
                    if response.status_code != 200:
                        code = {
                            401: "invalid_api_key",
                            402: "quota_exceeded",
                            413: "request_too_large",
                            504: "analysis_timeout",
                        }.get(response.status_code, "service_unavailable")
                        try:
                            envelope = ServiceError.model_validate(json.loads(body)["error"])
                            # The service uses its own content-free correlation UUID.
                            # Only the validated enum is retained, never its message.
                            code = envelope.code.value
                        except (ValueError, KeyError, TypeError):
                            pass
                        raise SemanticFailure(code)
                    return json.loads(body)
        except httpx.TimeoutException as error:
            raise SemanticFailure("analysis_timeout") from error
        except httpx.HTTPError as error:
            raise SemanticFailure("service_unavailable") from error
        except (ValueError, TypeError) as error:
            raise SemanticFailure("provider_output_invalid") from error

    def analyze(self, request: AnalysisRequest) -> SemanticAnalysisResponse:
        try:
            response = SemanticAnalysisResponse.model_validate(self._post("/v1/analyze", request))
            validate_model_response(request, response)
            if request.review_directives is not None and response.review_receipt is None:
                raise ValueError("Service did not acknowledge reviewer directives")
            return response
        except ValueError as error:
            raise SemanticFailure("provider_output_invalid") from error

    def draft(self, request: FlowDraftRequest) -> FlowDraftResponse:
        try:
            response = FlowDraftResponse.model_validate(self._post("/v1/flows/draft", request))
            validate_flow_draft_response(request, response)
            return response
        except ValueError as error:
            raise SemanticFailure("provider_output_invalid") from error
