# Governance checks against /cubejs-api/v1/meta: only the three governed
# views are visible, and each exposes exactly the expected members. Any
# extra visible cube or member is a governance leak.

EXPECTED_VISIBLE_CUBES = {"demand", "demand_growth", "generation_mix"}

EXPECTED_MEMBERS = {
    "demand": {
        "measures": {
            "demand.total_demand_mwh",
            "demand.peak_demand_mwh",
            "demand.average_demand_mwh",
            "demand.hours",
            "demand.imputed_hours",
            "demand.imputed_demand_share",
        },
        "dimensions": {
            "demand.ba_code",
            "demand.datetime_utc",
            "demand.is_imputed",
            "demand.imputation_code",
        },
    },
    "demand_growth": {
        "measures": {
            "demand_growth.annual_total_demand_mwh",
            "demand_growth.demand_yoy_growth",
            "demand_growth.demand_cagr",
        },
        "dimensions": {
            "demand_growth.ba_code",
            "demand_growth.year",
            "demand_growth.is_complete_year",
        },
    },
    "generation_mix": {
        "measures": {
            "generation_mix.generation_mwh",
            "generation_mix.denominator_generation_mwh",
            "generation_mix.renewable_generation_mwh",
            "generation_mix.fossil_generation_mwh",
            "generation_mix.carbon_free_generation_mwh",
            "generation_mix.renewable_share",
            "generation_mix.fossil_share",
            "generation_mix.carbon_free_share",
            "generation_mix.coal_share",
            "generation_mix.gas_share",
            "generation_mix.oil_share",
            "generation_mix.nuclear_share",
            "generation_mix.hydro_share",
            "generation_mix.solar_share",
            "generation_mix.wind_share",
            "generation_mix.geothermal_share",
            "generation_mix.other_share",
            "generation_mix.unknown_share",
            "generation_mix.imputed_generation_rows_share",
        },
        "dimensions": {
            "generation_mix.ba_code",
            "generation_mix.datetime_utc",
            "generation_mix.unified_fuel_category",
            "generation_mix.source_regime",
            "generation_mix.in_mix_denominator",
            "generation_mix.is_imputed_eia",
        },
    },
}


def test_visible_cubes_are_exactly_the_governed_views(cube_meta):
    """The visible cube set is exactly {demand, demand_growth, generation_mix}."""
    visible = {c["name"] for c in cube_meta["cubes"] if c.get("isVisible")}
    assert visible == EXPECTED_VISIBLE_CUBES, (
        f"visible cubes {sorted(visible)} != expected {sorted(EXPECTED_VISIBLE_CUBES)}"
    )


def test_visible_members_match_governed_surface(cube_meta):
    """Each governed view exposes exactly the expected measures and dimensions."""
    by_name = {c["name"]: c for c in cube_meta["cubes"]}
    for view_name, expected in EXPECTED_MEMBERS.items():
        cube = by_name[view_name]

        visible_measures = {
            m["name"] for m in cube["measures"] if m.get("isVisible")
        }
        assert visible_measures == expected["measures"], (
            f"{view_name} measures: unexpected "
            f"{sorted(visible_measures - expected['measures'])}, missing "
            f"{sorted(expected['measures'] - visible_measures)}"
        )

        visible_dimensions = {
            d["name"] for d in cube["dimensions"] if d.get("isVisible")
        }
        assert visible_dimensions == expected["dimensions"], (
            f"{view_name} dimensions: unexpected "
            f"{sorted(visible_dimensions - expected['dimensions'])}, missing "
            f"{sorted(expected['dimensions'] - visible_dimensions)}"
        )
