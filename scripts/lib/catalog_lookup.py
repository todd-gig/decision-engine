"""catalog_lookup — Modular Replication via Input Substitution helpers.

penrose_signal: neutral
penrose_dimension: provider_neutrality

Implements the lookup primitives that turn a tagged catalog row + an
operator_context into a filtered, scored, ordered result set. This is the
runtime expression of the doctrine: the SAME engine code serves any operator
(Carmen Beach / Tulum / Tamarindo / Canggu / Bali) — only the context tags
change. There are zero operator names hardcoded here.

Tag schema (semicolon-separated `key:value` pairs, see
`catalogs/stvr/playa_dashboard_max/README.md`):

    industry:hospitality;sub_vertical:short_term_rental;
    sub_vertical:vacation_rental;country:mexico;state:quintana_roo;
    city:playa_del_carmen;regime:mx_iva;source:government_doc;...

Multi-value keys (e.g. multiple `sub_vertical:` entries on one row) are
collapsed into a list under that key. `match_score` then counts each
context key:value pair that is present (once, even if the multi-value list
contains additional entries).

Scoping axes
------------
The doctrine README mandates that a Tulum operator must skip rows tagged
`city:playa_del_carmen` and a Canggu operator must skip rows tagged
`country:mexico`. Those geographic axes are SCOPING — when a row constrains
the axis to a value different from the context's value, the row is excluded
even if other axes match. The default scoping axes are
`country`, `state`, `city` (the geographic hierarchy); callers may pass
`scoping_axes=` to override (e.g. `industry`, `sub_vertical` if a
cross-vertical lookup needs stricter scoping).

WHY: doctrine memory
`~/.claude/projects/-Users-admin/memory/foundational_modular_replication_via_input_substitution.md`
mandates that every datum carries multi-axis JSONB tags so an alt-operator
can be served by swapping `operator_context.tags`. This module is the
reference filter primitive.
"""

from __future__ import annotations

from typing import Any, Iterable

# Geographic scoping axes — if a row constrains one of these to a value
# different from the context, the row is excluded. This is what makes
# "city:playa_del_carmen" skipped by a Tulum operator and "country:mexico"
# skipped by a Canggu operator.
DEFAULT_SCOPING_AXES: tuple[str, ...] = ("country", "state", "city")


def parse_tags(tag_str: str | None) -> dict[str, str | list[str]]:
    """Parse a semicolon-delimited `key:value` tag string.

    Multi-value keys collapse to a list (order-preserved, de-duplicated).
    Empty / None input returns an empty dict. Whitespace around tokens is
    stripped; malformed pairs (no `:`) are skipped silently — catalog
    authoring is allowed to be lenient.
    """
    out: dict[str, str | list[str]] = {}
    if not tag_str:
        return out
    for raw in tag_str.split(";"):
        token = raw.strip()
        if not token or ":" not in token:
            continue
        key, _, value = token.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key in out:
            existing = out[key]
            if isinstance(existing, list):
                if value not in existing:
                    existing.append(value)
            elif existing != value:
                out[key] = [existing, value]
        else:
            out[key] = value
    return out


def _values_for(tags: dict[str, str | list[str]], key: str) -> list[str]:
    """Return the value(s) for a key as a list (empty if absent)."""
    if key not in tags:
        return []
    v = tags[key]
    return list(v) if isinstance(v, list) else [v]


def match_score(
    row_tags: dict[str, str | list[str]],
    context_tags: dict[str, str | list[str]],
) -> int:
    """Count context key:value pairs that match the row's tags.

    A context entry matches if the row carries the same key AND the
    context's value(s) intersect the row's value(s). Multi-value keys
    on either side count once per (key, matched-value) pair from the
    context — never more than the number of context values supplied.
    """
    score = 0
    for ctx_key, ctx_value in context_tags.items():
        row_values = _values_for(row_tags, ctx_key)
        if not row_values:
            continue
        ctx_values = ctx_value if isinstance(ctx_value, list) else [ctx_value]
        for cv in ctx_values:
            if cv in row_values:
                score += 1
    return score


def _row_tags(row: dict[str, Any]) -> dict[str, str | list[str]]:
    """Lazily parse / cache the row's `tags` field as a dict."""
    cached = row.get("_parsed_tags")
    if isinstance(cached, dict):
        return cached
    parsed = parse_tags(row.get("tags"))
    row["_parsed_tags"] = parsed
    return parsed


def _observed_at(row: dict[str, Any]) -> str:
    """Best-available `observed_at` (CSV column wins, tag fallback)."""
    explicit = row.get("observed_at")
    if explicit:
        return str(explicit)
    tag_val = _row_tags(row).get("observed_at")
    if isinstance(tag_val, list):
        return tag_val[-1]
    return tag_val or ""


def _scope_compatible(
    row_tags: dict[str, str | list[str]],
    context_tags: dict[str, str | list[str]],
    scoping_axes: Iterable[str],
) -> bool:
    """Return False if the row's value on any scoping axis conflicts with
    the context. A row that omits the axis is treated as global on that
    axis (compatible with any context). A context that omits the axis is
    treated as unconstrained on that axis.
    """
    for axis in scoping_axes:
        row_values = _values_for(row_tags, axis)
        if not row_values:
            continue  # row is global on this axis
        ctx_values = (
            context_tags.get(axis)
            if axis in context_tags
            else None
        )
        if ctx_values is None:
            # context doesn't constrain this axis — row's constraint is fine
            continue
        ctx_list = ctx_values if isinstance(ctx_values, list) else [ctx_values]
        if not any(cv in row_values for cv in ctx_list):
            return False
    return True


def filter_catalog(
    rows: Iterable[dict[str, Any]],
    context: dict[str, str | list[str]],
    scoping_axes: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Return rows that are scope-compatible AND match_score >= 1,
    sorted by score desc, observed_at desc.

    Scope-compatibility (see `_scope_compatible`) is what implements the
    doctrine semantic: a Tulum operator skips Playa-city rows; a Canggu
    operator skips Mexico-country rows. Rows that don't constrain a given
    scoping axis are considered global on that axis and remain eligible.

    `rows` is any iterable of dicts that include a `tags` field. `context`
    is a flat dict of axis key -> value (or list of values) representing
    the operator's environment.
    """
    axes = tuple(scoping_axes) if scoping_axes is not None else DEFAULT_SCOPING_AXES
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for row in rows:
        row_tags = _row_tags(row)
        if not _scope_compatible(row_tags, context, axes):
            continue
        score = match_score(row_tags, context)
        if score >= 1:
            scored.append((score, _observed_at(row), row))
    scored.sort(key=lambda triple: (triple[0], triple[1]), reverse=True)
    return [row for _, _, row in scored]


def lookup(
    rows: Iterable[dict[str, Any]],
    context: dict[str, str | list[str]],
    key: str | None = None,
    key_field: str = "key",
    scoping_axes: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Return the single most-specific row matching the context.

    If `key` is provided, restrict candidates to rows where
    `row[key_field] == key` BEFORE scoring. Returns None if no row
    matches the context (or the key, when supplied).
    """
    candidates: Iterable[dict[str, Any]]
    if key is not None:
        candidates = [r for r in rows if r.get(key_field) == key]
    else:
        candidates = rows
    filtered = filter_catalog(candidates, context, scoping_axes=scoping_axes)
    return filtered[0] if filtered else None
