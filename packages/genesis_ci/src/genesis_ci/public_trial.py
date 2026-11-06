"""Intentionally public, revocable trial identity, bound to the official service."""

import json
from importlib.resources import files

OFFICIAL_SERVICE_URL = "https://semantic-api-production.up.railway.app"


def trial_failure_message(code: str) -> str:
    reason = {
        "quota_exceeded": "公共试用共享额度已用完，请等待管理员补充额度或配置个人 Genesis Key。",
        "invalid_api_key": "公共试用凭证已失效，请更新 CLI 或配置个人 Genesis Key。",
        "analysis_timeout": "公共试用分析超时，请稍后重试。",
    }.get(code, "公共试用暂时无法完成分析，请稍后重试或配置个人 Genesis Key。")
    return reason + " 本次保留本地分析结果；未自动重试。"


def public_trial_key() -> str:
    data = json.loads(
        files("genesis_ci").joinpath("assets/public-trial.json").read_text(encoding="utf-8")
    )
    if (
        not isinstance(data, dict)
        or data.get("service_url") != OFFICIAL_SERVICE_URL
        or data.get("purpose") != "shared_public_trial"
        or not isinstance(data.get("api_key"), str)
        or not data["api_key"].strip()
        or "\n" in data["api_key"]
        or "\r" in data["api_key"]
    ):
        raise ValueError("Invalid bundled public trial configuration; update the CLI.")
    return data["api_key"]
