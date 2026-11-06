"""Read only the packaged, explicitly versioned standard-text price catalog."""

from importlib.resources import files

from genesis_contracts.estimates import PriceCatalog

REVISION = "openai-text-2026-11-04"


def load_prices():
    return PriceCatalog.model_validate_json(
        files("genesis_ci").joinpath("assets/prices-2026-11-04.json").read_bytes()
    )


def scenario_prices(call, scenario):
    if scenario is None:
        return None
    if scenario.catalog_revision is None:
        return (
            scenario.input_price_per_million,
            scenario.output_price_per_million,
            scenario.price_source,
            scenario.price_date,
        )
    catalog = load_prices()
    if scenario.catalog_revision != catalog.revision:
        raise ValueError("Unknown price catalog revision")
    entry = next(
        (e for e in catalog.entries if (e.provider, e.model) == (call.provider, scenario.model)),
        None,
    )
    if entry is None:
        return None
    return (
        entry.input_per_million,
        entry.output_per_million,
        catalog.revision + "; " + entry.source_url + "; verified date (effective date unknown)",
        entry.verified_on,
    )
