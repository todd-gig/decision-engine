"""Empirical proof of Modular Replication via Input Substitution.

penrose_signal: strengthens
penrose_dimension: provider_neutrality

WHY: The Modular Replication doctrine
(`~/.claude/projects/-Users-admin/memory/foundational_modular_replication_via_input_substitution.md`)
claims:

> The SAME engine serves alt-operators (Tulum / Tamarindo / Canggu / Bali)
> by swapping operator_context inputs — never by editing engine code.

This test set is the empirical proof. It uses a SINGLE filter primitive
(`scripts.lib.catalog_lookup.filter_catalog`) and a SINGLE catalog
(`catalogs/stvr/playa_dashboard_max/05_Economics.csv`) and verifies that
five different operator contexts yield the doctrine-implied row sets:

    A  Playa del Carmen, MX   — city-specific row matches
    B  Tulum, MX              — statewide rows match, city rows don't
    C  Canggu, Bali, ID       — global rows match, MX rows don't
    D  Multi-value sub_vertical handling
    E  Specificity tiebreaker by observed_at

If any assertion fails the doctrine has drifted from the catalog or the
filter primitive — either condition is a structural defect.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.lib.catalog_lookup import (
    filter_catalog,
    lookup,
    match_score,
    parse_tags,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ECONOMICS_CSV = (
    REPO_ROOT / "catalogs" / "stvr" / "playa_dashboard_max" / "05_Economics.csv"
)


def _load_economics() -> list[dict[str, str]]:
    """Read 05_Economics.csv into a list of row dicts."""
    with ECONOMICS_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def economics_rows() -> list[dict[str, str]]:
    rows = _load_economics()
    assert rows, "Economics catalog must not be empty"
    return rows


def _keys(rows: list[dict[str, str]]) -> set[str]:
    return {r["key"] for r in rows}


# --------------------------------------------------------------------------- #
# Scenario A — Carmen Beach operator (Playa del Carmen, Quintana Roo, Mexico)
# --------------------------------------------------------------------------- #
def test_scenario_a_playa_del_carmen_matches_city_and_state_rows(
    economics_rows: list[dict[str, str]],
) -> None:
    context = {
        "industry": "hospitality",
        "sub_vertical": "short_term_rental",
        "country": "mexico",
        "state": "quintana_roo",
        "city": "playa_del_carmen",
    }
    matched = _keys(filter_catalog(economics_rows, context))

    # State-level fiscal rules MUST match.
    assert "mx_iva_rental_pct" in matched, (
        "Playa operator must see Mexico-IVA row (statewide regime)"
    )
    # City-specific benchmark MUST match.
    assert "playa_del_carmen_avg_adr_usd" in matched, (
        "Playa operator must see Playa city ADR benchmark"
    )
    # Statewide ISH MUST match.
    assert "mx_quintana_roo_ish_pct_official" in matched


# --------------------------------------------------------------------------- #
# Scenario B — Tulum operator (different city, SAME state)
# --------------------------------------------------------------------------- #
def test_scenario_b_tulum_inherits_state_rules_drops_city_specifics(
    economics_rows: list[dict[str, str]],
) -> None:
    context = {
        "industry": "hospitality",
        "sub_vertical": "short_term_rental",
        "country": "mexico",
        "state": "quintana_roo",
        "city": "tulum",
    }
    matched = _keys(filter_catalog(economics_rows, context))

    # Statewide regime rows MUST survive the city swap.
    statewide_must_match = {
        "mx_iva_rental_pct",
        "mx_isr_resident_rental_pct_max",
        "mx_isr_non_resident_rental_pct",
        "mx_quintana_roo_ish_pct_official",
        "mx_quintana_roo_ish_pct_airbnb_collects",
    }
    missing = statewide_must_match - matched
    assert not missing, (
        f"Tulum operator should inherit statewide regime rows; missing={missing}"
    )

    # City-specific rows MUST NOT match (different city).
    playa_city_must_not_match = {
        "playa_del_carmen_avg_adr_usd",
        "playa_del_carmen_occupancy_baseline",
        "playa_del_carmen_alos_nights",
        "playa_seasonality_jan_multiplier",
        "playa_seasonality_dec_multiplier",
        "cleaning_fee_per_stay_usd",  # tagged city:playa_del_carmen
    }
    leaked = playa_city_must_not_match & matched
    assert not leaked, (
        f"Playa-city-specific rows leaked into Tulum context: {leaked}"
    )


# --------------------------------------------------------------------------- #
# Scenario C — Canggu / Bali operator (different country entirely)
# --------------------------------------------------------------------------- #
def test_scenario_c_canggu_matches_global_drops_mexico_specifics(
    economics_rows: list[dict[str, str]],
) -> None:
    context = {
        "industry": "hospitality",
        "sub_vertical": "short_term_rental",
        "country": "indonesia",
        "state": "bali",
        "city": "canggu",
    }
    matched = _keys(filter_catalog(economics_rows, context))

    # Global vendor/regime rows MUST match (industry+sub_vertical alone).
    global_must_match = {
        "airbnb_host_service_fee_pct",
        "vrbo_commission_pct",
        "booking_com_commission_pct_global_avg",
        "tripadvisor_commission_pct",
        "pm_fee_pct_standard",
        "platform_fee_pct_card_processing",
        "maintenance_pct_of_gross",
        "cancellation_rate_avg_pct",
    }
    missing = global_must_match - matched
    assert not missing, (
        f"Canggu operator should inherit global rows; missing={missing}"
    )

    # Mexico-specific tax rows MUST NOT match.
    mexico_must_not_match = {
        "mx_iva_rental_pct",
        "mx_isr_resident_rental_pct_max",
        "mx_isr_non_resident_rental_pct",
        "mx_quintana_roo_ish_pct_official",
        "mx_quintana_roo_ish_pct_airbnb_collects",
        "mx_uma_daily_value_mxn",
        "usd_mxn_fx_rate_observed",
        # city + state-only operator-supplied rows tagged mexico
        "playa_del_carmen_avg_adr_usd",
        "playa_seasonality_jul_multiplier",
        "utilities_pct_of_gross",
        "cleaning_fee_per_stay_usd",
    }
    leaked = mexico_must_not_match & matched
    assert not leaked, (
        f"Mexico-tagged rows leaked into Canggu context: {leaked}"
    )


# --------------------------------------------------------------------------- #
# Scenario D — multi-value tag handling
# --------------------------------------------------------------------------- #
def test_scenario_d_multivalue_sub_vertical_matches_either(
    economics_rows: list[dict[str, str]],
) -> None:
    """`airbnb_host_service_fee_pct` carries BOTH sub_vertical:short_term_rental
    AND sub_vertical:vacation_rental. The match must succeed when context
    supplies either one.
    """
    row = next(r for r in economics_rows if r["key"] == "airbnb_host_service_fee_pct")
    tags = parse_tags(row["tags"])
    assert isinstance(tags["sub_vertical"], list), (
        "airbnb row must parse as multi-value sub_vertical list"
    )
    assert set(tags["sub_vertical"]) == {"short_term_rental", "vacation_rental"}

    # Context with short_term_rental matches.
    assert match_score(tags, {"sub_vertical": "short_term_rental"}) == 1
    # Context with vacation_rental ALSO matches.
    assert match_score(tags, {"sub_vertical": "vacation_rental"}) == 1
    # Counted once even though the row offers two values.
    assert match_score(tags, {"sub_vertical": "short_term_rental"}) == 1
    # When context itself supplies both as a list, both count.
    both = match_score(
        tags, {"sub_vertical": ["short_term_rental", "vacation_rental"]}
    )
    assert both == 2, "Each context value matched contributes one point"
    # Non-matching value scores zero.
    assert match_score(tags, {"sub_vertical": "executive_housing"}) == 0


# --------------------------------------------------------------------------- #
# Scenario E — specificity tiebreaker by observed_at
# --------------------------------------------------------------------------- #
def test_scenario_e_observed_at_breaks_ties_for_lookup() -> None:
    """When two rows match the same number of context tags, the one with the
    higher `observed_at` wins. Verifies both `filter_catalog` ordering and
    `lookup(..., key=...)` selection.
    """
    rows = [
        {
            "key": "fx_rate",
            "value": "17.10",
            "tags": "country:mexico;regime:fx",
            "observed_at": "2026-05-16",
        },
        {
            "key": "fx_rate",
            "value": "16.50",
            "tags": "country:mexico;regime:fx",
            "observed_at": "2025-08-01",
        },
        {
            "key": "fx_rate",
            "value": "16.00",
            "tags": "country:mexico;regime:fx",
            "observed_at": "2024-01-01",
        },
    ]
    context = {"country": "mexico", "regime": "fx"}

    ordered = filter_catalog(rows, context)
    assert [r["observed_at"] for r in ordered] == [
        "2026-05-16",
        "2025-08-01",
        "2024-01-01",
    ], "filter_catalog must order ties by observed_at descending"

    winner = lookup(rows, context, key="fx_rate")
    assert winner is not None
    assert winner["value"] == "17.10", (
        "lookup must return the most-recent row when scores are tied"
    )


# --------------------------------------------------------------------------- #
# Doctrine assertion — engine code is NOT operator-conditional
# --------------------------------------------------------------------------- #
def test_doctrine_no_hardcoded_operator_names_in_lookup() -> None:
    """The lookup primitive MUST be operator-name-free. The doctrine requires
    that the same code path serves any operator — only the input context
    differs. A grep-style assertion on executable code (docstrings stripped)
    locks that invariant in. Docstrings may legitimately reference operator
    names as worked examples; the executable AST must not.
    """
    import ast

    import scripts.lib.catalog_lookup as mod

    forbidden = [
        "carmen_beach",
        "carmenbeach",
        "playa_del_carmen",
        "tulum",
        "tamarindo",
        "canggu",
    ]

    class DocstringStripper(ast.NodeTransformer):
        """Remove the leading string-literal Expr node from any module,
        function, async-function, or class body — i.e. all docstrings."""

        def _strip(self, node: ast.AST) -> ast.AST:
            body = getattr(node, "body", None)
            if (
                isinstance(body, list)
                and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
            return node

        def visit_Module(self, node: ast.Module) -> ast.AST:
            self.generic_visit(node)
            return self._strip(node)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
            self.generic_visit(node)
            return self._strip(node)

        def visit_AsyncFunctionDef(
            self, node: ast.AsyncFunctionDef
        ) -> ast.AST:
            self.generic_visit(node)
            return self._strip(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
            self.generic_visit(node)
            return self._strip(node)

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    stripped = DocstringStripper().visit(tree)
    ast.fix_missing_locations(stripped)
    executable = ast.unparse(stripped).lower()
    leaks = [name for name in forbidden if name in executable]
    assert not leaks, (
        f"Operator-name strings leaked into executable code: {leaks}. "
        "Modular Replication requires zero hardcoded operator names."
    )
