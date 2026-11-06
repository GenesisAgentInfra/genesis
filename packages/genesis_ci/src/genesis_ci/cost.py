"""Calculate explicit conditional scenarios without guessing token use or prices."""

from decimal import Decimal

from genesis_contracts.models import EstimateParameter, ImpactEstimate

from .pricing import scenario_prices
from .prompt_metrics import measurement_parameters
from .rules import identity

ASSUMPTIONS = (
    "User-supplied conditional scenario, not predicted or measured runtime usage.",
    "Per-call quantities and invocations are explicit; prompt fragment tokens, static loop bounds and output caps are never substituted.",
    "Standard uncached text only; cache tiers, batch/priority discounts, tool fees, retries and provider-specific charges need explicit quantities/prices.",
)


def estimate_costs(snapshot_id, patterns, inputs=None, measurements=()):
    if inputs and inputs.snapshot_id != snapshot_id:
        raise ValueError("Cost inputs belong to a different snapshot")
    all_calls = {c.call_id: c for c in patterns.model_calls}
    scenarios = {s.call_id: s for s in inputs.scenarios} if inputs else {}
    if set(scenarios) - set(all_calls):
        raise ValueError("Cost inputs must reference recognized model calls")
    if (
        inputs
        and inputs.format_version == 1
        and any(all_calls[key].side != "head" for key in scenarios)
    ):
        raise ValueError("Version 1 cost inputs must reference head model calls")
    calls = {
        key: call for key, call in all_calls.items() if call.side == "head" or key in scenarios
    }
    metrics = {m.call_id: m for m in measurements}
    estimates, amounts = {}, {}
    for call_id, call in sorted(calls.items()):
        scenario = scenarios.get(call_id)
        if scenario and (
            call.model.kind != "literal"
            or call.model.value != scenario.model
            or call.resolution.status != "resolved"
        ):
            raise ValueError("Cost model must match a resolved literal model at the selected call")
        prices = scenario_prices(call, scenario)
        parameters = [
            EstimateParameter(
                name=name,
                value=getattr(scenario, name) if scenario else None,
                unit="calls" if name == "invocations" else "tokens/call",
                source=scenario.quantity_source if scenario else None,
                unknown_reason="Explicit scenario quantity not supplied"
                if not scenario or getattr(scenario, name) is None
                else None,
            )
            for name in ("input_tokens", "output_tokens", "invocations")
        ]
        unknowns = [p.name + ": " + p.unknown_reason for p in parameters if p.value is None]
        if not prices:
            unknowns.append(
                "No verified price for selected provider/model/revision"
                if scenario
                else "Versioned price and quantity inputs not supplied"
            )
        if prices:
            parameters.extend(
                EstimateParameter(
                    name=name, value=float(price), unit="USD/million tokens", source=prices[2]
                )
                for name, price in zip(
                    ("input_price_per_million", "output_price_per_million"), prices[:2], strict=True
                )
            )
        amount = None
        if not unknowns:
            amount = (
                Decimal(scenario.invocations)
                * (
                    Decimal(scenario.input_tokens) * prices[0]
                    + Decimal(scenario.output_tokens) * prices[1]
                )
                / Decimal(1_000_000)
            )
        metric = metrics.get(call_id)
        if metric:
            parameters.extend(measurement_parameters(metric))
        refs = set(call.evidence_ids)
        if metric:
            refs.update(metric.evidence_ids)
        amounts[call_id] = amount
        estimates[call_id] = ImpactEstimate(
            estimate_id=identity("cost_scenario", call_id),
            structural_signals=(
                f"Recognized {call.side.value} {call.provider} {call.api} call at {call.symbol_id}",
            ),
            parameters=tuple(parameters),
            amount=float(amount) if amount is not None else None,
            formula="invocations * (input_tokens * input_price_per_million + output_tokens * output_price_per_million) / 1000000",
            currency=scenario.currency if scenario else None,
            price_source=prices[2] if prices else None,
            price_date=prices[3].isoformat() if prices else None,
            assumptions=(*ASSUMPTIONS, *(metric.unknowns if metric else ())),
            unknowns=tuple(unknowns),
            evidence_ids=tuple(sorted(refs)),
        )
    deltas = []
    for pair in inputs.comparisons if inputs else ():
        old, new = all_calls.get(pair.base_call_id), all_calls.get(pair.head_call_id)
        if (
            old is None
            or new is None
            or old.side != "base"
            or new.side != "head"
            or pair.base_call_id not in scenarios
            or pair.head_call_id not in scenarios
        ):
            raise ValueError("Cost comparison requires explicit base and head scenarios")
        before, after = estimates[old.call_id], estimates[new.call_id]
        known = amounts[old.call_id] is not None and amounts[new.call_id] is not None
        deltas.append(
            ImpactEstimate(
                estimate_id=identity("cost_delta", pair.comparison_id),
                structural_signals=(
                    f"Explicit scenario comparison: {old.symbol_id} -> {new.symbol_id}",
                ),
                parameters=tuple(
                    EstimateParameter(
                        name=name,
                        value=e.amount,
                        unit="USD/scenario",
                        source=e.estimate_id,
                        unknown_reason="Component scenario amount unknown"
                        if e.amount is None
                        else None,
                    )
                    for name, e in (("base_amount", before), ("head_amount", after))
                ),
                amount=float(amounts[new.call_id] - amounts[old.call_id]) if known else None,
                formula="head_amount - base_amount",
                currency="USD",
                price_source="; ".join(filter(None, (before.price_source, after.price_source)))
                or None,
                price_date=after.price_date if before.price_date == after.price_date else None,
                assumptions=(
                    *ASSUMPTIONS,
                    pair.assumption,
                    "Call correspondence and workload comparability are user-supplied, not inferred; component estimates preserve individual price dates.",
                ),
                unknowns=() if known else ("At least one component scenario is unknown",),
                evidence_ids=tuple(sorted(set(before.evidence_ids) | set(after.evidence_ids))),
            )
        )
    totals = []
    for group in inputs.groups if inputs else ():
        if (
            any(key not in scenarios for key in group.call_ids)
            or len({all_calls[key].side for key in group.call_ids}) != 1
        ):
            raise ValueError("Cost group needs explicit scenarios on one side")
        members = [estimates[key] for key in group.call_ids]
        known = all(amounts[key] is not None for key in group.call_ids)
        dates = {e.price_date for e in members}
        totals.append(
            ImpactEstimate(
                estimate_id=identity("cost_group", group.group_id),
                structural_signals=("Explicit scenario group: " + group.group_id,),
                parameters=tuple(
                    EstimateParameter(
                        name=e.estimate_id,
                        value=e.amount,
                        unit="USD/scenario",
                        source=e.estimate_id,
                        unknown_reason="Component scenario unknown" if e.amount is None else None,
                    )
                    for e in members
                ),
                amount=float(sum((amounts[key] for key in group.call_ids), Decimal(0)))
                if known
                else None,
                formula="sum(component scenario amounts)",
                currency="USD",
                price_source="; ".join(sorted({e.price_source for e in members if e.price_source}))
                or None,
                price_date=next(iter(dates)) if len(dates) == 1 else None,
                assumptions=(
                    *ASSUMPTIONS,
                    group.assumption,
                    "Membership and invocation counts are user supplied; this is not an automatically inferred runtime path.",
                ),
                unknowns=() if known else ("At least one group component is unknown",),
                evidence_ids=tuple(sorted({r for e in members for r in e.evidence_ids})),
            )
        )
    return (*estimates.values(), *deltas, *totals)


def validate_cost_estimates(snapshot_id, patterns, inputs, measurements, estimates):
    if tuple(estimates) != estimate_costs(snapshot_id, patterns, inputs, measurements):
        raise ValueError("Cost estimates differ from deterministic scenario calculations")
