import json
from pathlib import Path

from genesis_ci.report import assemble_report, render_markdown
from genesis_contracts import AnalysisRequest, LocalAnalysis, SemanticAnalysisResponse
from genesis_contracts.models import BehaviorAnalysisResponse, BehaviorReview
from genesis_contracts.validation import validate_public_response

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT.parent / "code-intelligence-protocol" / "examples" / "v0.1.0"
FIXTURES = (
    "normal-five-sections",
    "dynamic-call-unresolved",
    "missing-intent-and-tests",
    "flow-entry-invalid",
)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    for name in FIXTURES:
        fixture_dir = ROOT / "fixtures" / name
        data = json.loads((fixture_dir / "semantic.json").read_text(encoding="utf-8"))
        local = LocalAnalysis.model_validate(data["local_analysis"])
        request = AnalysisRequest.model_validate(data["request"])
        semantic = SemanticAnalysisResponse.model_validate(data["semantic_response"])
        report = assemble_report(local, request, semantic)
        encoded = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        write(fixture_dir / "report.json", encoded)
        write(fixture_dir / "report.md", render_markdown(report))
        write(PUBLIC / f"{name}.json", encoded)
        if name == "normal-five-sections":
            base = next(
                ref.evidence_id
                for ref in request.evidence
                if ref.kind == "code" and ref.side == "base"
            )
            head = next(
                ref.evidence_id
                for ref in request.evidence
                if ref.kind == "code" and ref.side == "head"
            )
            review = BehaviorReview.model_validate(
                {
                    "coverage": {
                        "status": "insufficient_context",
                        "reason": "Synthetic example; caller and notification implementation are absent.",
                    },
                    "changes": [
                        {
                            "change_id": "report-notification",
                            "scenario": "提交报告并通知",
                            "condition": "按各版本的调用方式执行 submit_report，第三方提交返回结果。",
                            "before": "直接返回第三方提交结果。",
                            "after": "等待通知完成后才返回提交结果；函数现在需要异步调用。",
                            "before_evidence_ids": [base],
                            "after_evidence_ids": [head],
                            "explanation": "新增 await notify(result)，放在提交与返回之间。",
                            "impact": "完成时间包含通知等待；若通知抛出异常，当前函数不会正常返回结果。",
                            "preserved_behavior": "第三方提交调用仍是同步调用。",
                            "evidence_ids": [base, head],
                            "finding_ids": [],
                            "limitations": [
                                "未提供调用方及通知实现，无法确认调用方适配、通知耗时及失败概率。"
                            ],
                        }
                    ],
                }
            )
            compared = BehaviorAnalysisResponse.model_validate(
                {
                    **report.model_dump(mode="json"),
                    "schema_version": "0.2.0",
                    "analysis_status": "partial",
                    "behavior_review": review.model_dump(mode="json"),
                }
            )
            validate_public_response(compared)
            write(
                PUBLIC.parent / "v0.2.0" / "behavior-comparison.json",
                compared.model_dump_json(indent=2) + "\n",
            )
    write(
        PUBLIC / "flows.yaml",
        "schema_version: 1\n"
        "flows:\n"
        "  - id: submit-report\n"
        "    name: Submit report\n"
        "    status: confirmed\n"
        "    entries:\n"
        "      - src/app.py#submit_report\n"
        "    acceptance:\n"
        "      - Failed submissions do not send a success notification\n",
    )
    print(f"Exported {len(FIXTURES)} synthetic report examples to {PUBLIC}")


if __name__ == "__main__":
    main()
