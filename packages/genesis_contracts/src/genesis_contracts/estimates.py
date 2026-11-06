"""Auditable local text measurements and explicit price catalog; no HTTP changes."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .models import ContractModel, EvidenceSide


class PriceEntry(ContractModel):
    provider: Literal["openai", "anthropic"]
    model: str = Field(min_length=1)
    input_per_million: Decimal = Field(ge=0, le=10**9)
    output_per_million: Decimal = Field(ge=0, le=10**9)
    currency: Literal["USD"] = "USD"
    unit: Literal["USD/million tokens"] = "USD/million tokens"
    tier: Literal["standard_uncached_text"] = "standard_uncached_text"
    source_url: str = Field(pattern=r"^https://")
    verified_on: date
    effective_from: date | None = None


class PriceCatalog(ContractModel):
    format_version: Literal[1] = 1
    revision: str = Field(min_length=1)
    entries: tuple[PriceEntry, ...]

    @model_validator(mode="after")
    def unique_models(self):
        if len({(e.provider, e.model) for e in self.entries}) != len(self.entries):
            raise ValueError("Duplicate price model")
        return self


class PromptMeasurement(ContractModel):
    call_id: str
    side: EvidenceSide
    symbol_id: str
    model: str | None
    known_characters: int = Field(ge=0)
    text_fragments: int = Field(ge=0)
    fragment_tokens: int | None = Field(default=None, ge=0)
    encoding: str | None = None
    tokenizer_version: str | None = None
    encoding_sha256: str | None = None
    input_complete: bool = False
    unknowns: tuple[str, ...]
    evidence_ids: tuple[str, ...]
