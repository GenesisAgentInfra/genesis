"""Local, explicit scenario inputs. No public schema or automatic price lookup."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .models import ContractModel


class CostScenario(ContractModel):
    call_id: str
    model: str
    input_tokens: int | None = Field(default=None, ge=0, le=10**12, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, le=10**12, strict=True)
    invocations: int | None = Field(default=None, ge=0, le=10**9, strict=True)
    quantity_source: str = Field(min_length=1)
    input_price_per_million: Decimal | None = Field(default=None, ge=0, le=10**9)
    output_price_per_million: Decimal | None = Field(default=None, ge=0, le=10**9)
    currency: Literal["USD"] = "USD"
    price_source: str | None = Field(default=None, min_length=1)
    price_date: date | None = None
    catalog_revision: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def price_mode(self):
        explicit = (
            self.input_price_per_million,
            self.output_price_per_million,
            self.price_source,
            self.price_date,
        )
        if self.catalog_revision:
            if any(value is not None for value in explicit):
                raise ValueError("Catalog selection cannot override explicit price fields")
        elif any(value is None for value in explicit):
            raise ValueError(
                "Supply both explicit prices with source/date or select a catalog revision"
            )
        return self


class CostComparison(ContractModel):
    comparison_id: str = Field(min_length=1)
    base_call_id: str
    head_call_id: str
    assumption: str = Field(min_length=1)


class CostGroup(ContractModel):
    group_id: str = Field(min_length=1)
    call_ids: tuple[str, ...] = Field(min_length=1)
    assumption: str = Field(min_length=1)

    @model_validator(mode="after")
    def unique_members(self):
        if len(set(self.call_ids)) != len(self.call_ids):
            raise ValueError("Cost group calls must be unique")
        return self


class CostInputs(ContractModel):
    format_version: Literal[1, 2] = 1
    snapshot_id: str
    scenarios: tuple[CostScenario, ...]
    comparisons: tuple[CostComparison, ...] = ()
    groups: tuple[CostGroup, ...] = ()

    @model_validator(mode="after")
    def unique_calls(self):
        if len({s.call_id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Each call has at most one cost scenario")
        if self.format_version == 1 and (self.comparisons or self.groups):
            raise ValueError("Cost comparisons require format_version 2")
        if len({c.comparison_id for c in self.comparisons}) != len(self.comparisons):
            raise ValueError("Duplicate cost comparison IDs")
        if len({(c.base_call_id, c.head_call_id) for c in self.comparisons}) != len(
            self.comparisons
        ):
            raise ValueError("Duplicate cost comparison pairs")
        if len({g.group_id for g in self.groups}) != len(self.groups):
            raise ValueError("Duplicate cost group IDs")
        return self
