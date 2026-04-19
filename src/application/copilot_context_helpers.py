from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any, Iterable


def dedupe_warnings(*groups: Iterable[str] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for warning in group or []:
            text = str(warning or "").strip()
            if text and text not in seen:
                seen.add(text)
                ordered.append(text)
    return ordered


def summarize_portfolio_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    position_limit: int = 5,
    bucket_limit: int = 5,
) -> dict[str, Any] | None:
    if not snapshot:
        return None
    positions = [row for row in snapshot.get("positions", []) if isinstance(row, dict)]
    total_value = _as_float(snapshot.get("net_liquidation"))
    if total_value is None:
        total_value = _as_float(snapshot.get("total_market_value"))

    gross_exposure = sum(abs(_as_float(position.get("base_market_value")) or 0.0) for position in positions)
    net_exposure = sum(_as_float(position.get("base_market_value")) or 0.0 for position in positions)
    cash_value = sum(
        _as_float(position.get("base_market_value")) or 0.0
        for position in positions
        if _is_cash_position(position)
    )
    largest_position = _best_position(positions, key="base_market_value", absolute=True)
    best_pnl = _best_position(positions, key="unrealized_pnl", absolute=False)
    worst_pnl = _worst_position(positions, key="unrealized_pnl", absolute=False)
    sorted_positions = sorted(
        positions,
        key=lambda row: abs(_as_float(row.get("base_market_value")) or 0.0),
        reverse=True,
    )

    return {
        "timestamp": _isoformat(snapshot.get("timestamp")),
        "base_currency": snapshot.get("base_currency"),
        "positions_count": len(positions),
        "net_liquidation": _as_float(snapshot.get("net_liquidation")),
        "total_market_value": _as_float(snapshot.get("total_market_value")),
        "total_cash": _as_float(snapshot.get("total_cash")),
        "day_pnl": _as_float(snapshot.get("day_pnl")),
        "day_pnl_pct": _as_float(snapshot.get("day_pnl_pct")),
        "day_pnl_source": snapshot.get("day_pnl_source"),
        "gross_exposure": gross_exposure,
        "net_exposure": net_exposure,
        "cash_weight": (cash_value / total_value) if total_value and total_value > 0 else None,
        "largest_position": _position_summary(largest_position),
        "best_pnl": _position_summary(best_pnl),
        "worst_pnl": _position_summary(worst_pnl),
        "top_positions": [_position_summary(position) for position in sorted_positions[:position_limit]],
        "security_type_buckets": _bucket_counts(
            [str(position.get("sec_type") or "Unknown") for position in positions],
            limit=bucket_limit,
        ),
        "currency_buckets": _bucket_counts(
            [str(position.get("currency") or "Unknown") for position in positions],
            limit=bucket_limit,
        ),
        "warnings": list(snapshot.get("warnings", []) or []),
    }


def summarize_portfolio_history(
    history: dict[str, Any] | None,
    *,
    point_limit: int = 24,
) -> dict[str, Any] | None:
    if not history:
        return None
    points = [row for row in history.get("points", []) if isinstance(row, dict)]
    values = [_as_float(point.get("portfolio_value")) for point in points]
    clean_values = [value for value in values if value is not None]
    start_value = clean_values[0] if clean_values else None
    latest_value = clean_values[-1] if clean_values else None

    return {
        "source": history.get("source"),
        "observations": len(points),
        "start_timestamp": _isoformat(points[0].get("timestamp")) if points else None,
        "latest_timestamp": _isoformat(points[-1].get("timestamp")) if points else None,
        "start_value": start_value,
        "latest_value": latest_value,
        "total_return": ((latest_value / start_value) - 1.0) if start_value and latest_value is not None else None,
        "max_drawdown": _drawdown_from_values(clean_values),
        "points": [
            {
                "timestamp": _isoformat(point.get("timestamp")),
                "portfolio_value": _as_float(point.get("portfolio_value")),
            }
            for point in points[-point_limit:]
        ],
    }


def summarize_portfolio_performance(
    performance: dict[str, Any] | None,
    *,
    point_limit: int = 24,
) -> dict[str, Any] | None:
    if not performance:
        return None
    performance_points = [row for row in performance.get("performance_points", []) if isinstance(row, dict)]
    benchmark_points = [row for row in performance.get("benchmark_points", []) if isinstance(row, dict)]
    latest_perf = _point_value(performance_points[-1], "value") if performance_points else None
    latest_benchmark = _point_value(benchmark_points[-1], "value") if benchmark_points else None

    return {
        "benchmark_symbol": performance.get("benchmark_symbol"),
        "benchmark_source": performance.get("benchmark_source"),
        "observations": len(performance_points),
        "benchmark_observations": len(benchmark_points),
        "portfolio_base_value": _as_float(performance.get("portfolio_base_value")),
        "portfolio_total_return": (latest_perf - 1.0) if latest_perf is not None else None,
        "benchmark_total_return": (latest_benchmark - 1.0) if latest_benchmark is not None else None,
        "relative_return": (
            (latest_perf / latest_benchmark) - 1.0
            if latest_perf is not None and latest_benchmark not in {None, 0.0}
            else None
        ),
        "max_drawdown": _drawdown_from_index_points(performance_points),
        "day_pnl": _as_float(performance.get("day_pnl")),
        "day_pnl_pct": _as_float(performance.get("day_pnl_pct")),
        "day_pnl_source": performance.get("day_pnl_source"),
        "missing_symbols": [str(item) for item in performance.get("missing_symbols", [])],
        "message": performance.get("message"),
        "warnings": list(performance.get("warnings", []) or []),
        "performance_points": [
            {
                "timestamp": _isoformat(point.get("timestamp")),
                "value": _as_float(point.get("value")),
            }
            for point in performance_points[-point_limit:]
        ],
        "benchmark_points": [
            {
                "timestamp": _isoformat(point.get("timestamp")),
                "value": _as_float(point.get("value")),
            }
            for point in benchmark_points[-point_limit:]
        ],
    }


def summarize_research_result(
    result: dict[str, Any] | None,
    *,
    weight_limit: int = 6,
    constituent_limit: int = 6,
) -> dict[str, Any] | None:
    if not result:
        return None
    weights = [row for row in result.get("weights", []) if isinstance(row, dict)]
    constituents = [row for row in result.get("constituents", []) if isinstance(row, dict)]
    sorted_weights = sorted(weights, key=lambda row: abs(_as_float(row.get("weight")) or 0.0), reverse=True)
    sorted_constituents = sorted(
        constituents,
        key=lambda row: abs(_as_float(row.get("weighted_return")) or _as_float(row.get("weight")) or 0.0),
        reverse=True,
    )
    best_constituent = _best_row(constituents, key="total_return", absolute=False)
    worst_constituent = _worst_row(constituents, key="total_return", absolute=False)
    weighted_leader = _best_row(constituents, key="weighted_return", absolute=False)

    return {
        "scope_type": result.get("scope_type"),
        "benchmark_symbol": result.get("benchmark_symbol"),
        "primary_symbol": result.get("primary_symbol"),
        "observations_count": int(result.get("observations_count") or 0),
        "summary": dict(result.get("summary") or {}),
        "structure": dict(result.get("structure") or {}),
        "coverage": dict(result.get("coverage") or {}),
        "top_weights": [_research_weight_summary(row) for row in sorted_weights[:weight_limit]],
        "top_constituents": [_research_constituent_summary(row) for row in sorted_constituents[:constituent_limit]],
        "best_constituent": _research_constituent_summary(best_constituent),
        "worst_constituent": _research_constituent_summary(worst_constituent),
        "weighted_leader": _research_constituent_summary(weighted_leader),
        "snapshot_summary": summarize_portfolio_snapshot(result.get("snapshot")),
        "warnings": list(result.get("warnings", []) or []),
    }


def summarize_risk_result(
    result: dict[str, Any] | None,
    *,
    contribution_limit: int = 8,
    excluded_limit: int = 8,
) -> dict[str, Any] | None:
    if not result:
        return None
    metrics = dict(result.get("metrics") or {})
    contributions = [row for row in result.get("contributions", []) if isinstance(row, dict)]
    excluded_assets = [row for row in result.get("excluded_assets", []) if isinstance(row, dict)]
    terminal_returns = [
        _as_float(value)
        for value in (result.get("monte_carlo") or {}).get("terminal_returns", [])
    ]
    clean_terminal_returns = [value for value in terminal_returns if value is not None]
    sorted_contributions = sorted(
        contributions,
        key=lambda row: abs(_as_float(row.get("variance_contribution_pct")) or 0.0),
        reverse=True,
    )

    return {
        "metrics": metrics,
        "coverage": {
            "portfolio_value": _as_float(metrics.get("portfolio_value")),
            "covered_portfolio_value": _as_float(metrics.get("covered_portfolio_value")),
            "covered_risk_basis_value": _as_float(metrics.get("covered_risk_basis_value")),
            "risk_basis_value": _as_float(metrics.get("risk_basis_value")),
            "risk_coverage_ratio": _as_float(metrics.get("risk_coverage_ratio")),
            "aligned_obs_count": _as_int(metrics.get("aligned_obs_count")),
            "benchmark_overlap_count": _as_int(metrics.get("benchmark_overlap_count")),
        },
        "benchmark": {
            "beta": _as_float(metrics.get("beta")),
            "correlation": _as_float(metrics.get("correlation")),
            "alpha_annual": _as_float(metrics.get("alpha_annual")),
        },
        "monte_carlo": {
            "model": metrics.get("monte_carlo_model"),
            "horizon_days": _as_int(metrics.get("monte_carlo_horizon_days")),
            "num_simulations": _as_int(metrics.get("monte_carlo_num_simulations")),
            "var": _as_float(metrics.get("monte_carlo_var")),
            "cvar": _as_float(metrics.get("monte_carlo_cvar")),
            "var_total_estimate": _as_float(metrics.get("monte_carlo_var_total_estimate")),
            "cvar_total_estimate": _as_float(metrics.get("monte_carlo_cvar_total_estimate")),
            "terminal_return_p05": _percentile(clean_terminal_returns, 0.05),
            "terminal_return_p50": _percentile(clean_terminal_returns, 0.50),
            "terminal_return_p95": _percentile(clean_terminal_returns, 0.95),
        },
        "top_contributions": [_risk_contribution_summary(row) for row in sorted_contributions[:contribution_limit]],
        "excluded_assets": [
            {
                "symbol": row.get("display_symbol") or row.get("symbol"),
                "reason": row.get("reason"),
            }
            for row in excluded_assets[:excluded_limit]
        ],
        "warnings": list(result.get("warnings", []) or []),
    }


def summarize_iv_state(
    surface: dict[str, Any] | None,
    session: dict[str, Any] | None,
) -> dict[str, Any] | None:
    active_surface = resolve_iv_surface(surface, session)
    if not active_surface:
        return None
    strikes = [_as_float(value) for value in active_surface.get("strikes", [])]
    clean_strikes = [value for value in strikes if value is not None]
    expiries = [str(value) for value in active_surface.get("expiries", [])]
    iv_grid = active_surface.get("iv_grid", []) or []
    spot = _as_float(active_surface.get("spot"))
    atm_index = nearest_strike_index(clean_strikes, spot)
    selected_expiry_index = 0
    selected_expiry = expiries[selected_expiry_index] if expiries else None
    selected_slice = [
        {
            "strike": clean_strikes[index] if index < len(clean_strikes) else None,
            "iv": _surface_value(iv_grid, selected_expiry_index, index),
        }
        for index in range(min(len(clean_strikes), len(iv_grid[selected_expiry_index]) if iv_grid else 0))
    ]
    term_structure = [
        {
            "expiry": expiry,
            "iv": _surface_value(iv_grid, row_index, atm_index),
        }
        for row_index, expiry in enumerate(expiries)
    ]
    front_slice = selected_slice

    return {
        "symbol": active_surface.get("symbol") or session.get("active_symbol") if session else None,
        "timestamp": _isoformat(active_surface.get("timestamp")),
        "snapshot_available": bool(active_surface.get("snapshot_available")),
        "spot": spot,
        "points": _as_int(active_surface.get("points")),
        "delayed": active_surface.get("delayed"),
        "expiries_count": len(expiries),
        "strikes_count": len(clean_strikes),
        "atm_strike": clean_strikes[atm_index] if clean_strikes and atm_index < len(clean_strikes) else None,
        "selected_expiry": selected_expiry,
        "front_slice": {
            "expiry": selected_expiry,
            "atm_iv": _surface_value(iv_grid, selected_expiry_index, atm_index),
            "min_iv": min((row["iv"] for row in front_slice if row["iv"] is not None), default=None),
            "max_iv": max((row["iv"] for row in front_slice if row["iv"] is not None), default=None),
            "points": front_slice[:8],
        },
        "atm_term_structure": term_structure[:8],
        "session": {
            "running": bool((session or {}).get("running")),
            "status_text": (session or {}).get("status_text"),
            "active_symbol": (session or {}).get("active_symbol"),
            "market_data_mode": (session or {}).get("market_data_mode"),
            "messages": list((session or {}).get("messages", []) or []),
        },
        "warnings": dedupe_warnings(
            active_surface.get("warnings", []),
            (session or {}).get("messages", []),
        ),
    }


def summarize_commodities_workspace(
    workspace: dict[str, Any] | None,
    *,
    summary_limit: int = 8,
    spread_limit: int = 8,
    inventory_limit: int = 8,
) -> dict[str, Any] | None:
    if not workspace:
        return None
    coverage = workspace.get("coverage") if isinstance(workspace.get("coverage"), dict) else {}
    market_summaries = [row for row in workspace.get("market_summaries", []) if isinstance(row, dict)]
    spreads = [row for row in workspace.get("spreads", []) if isinstance(row, dict)]
    inventories = [row for row in workspace.get("inventories", []) if isinstance(row, dict)]
    curves = [row for row in workspace.get("curves", []) if isinstance(row, dict)]
    events = [row for row in workspace.get("events", []) if isinstance(row, dict)]
    cross_domain_links = [row for row in workspace.get("cross_domain_links", []) if isinstance(row, dict)]

    selected_id = str(workspace.get("selected_instrument_id") or "")
    selected_summary = next(
        (
            _commodity_market_summary(row)
            for row in market_summaries
            if _as_dict(row.get("instrument")).get("instrument_id") == selected_id
        ),
        None,
    )
    selected_curve = next(
        (_commodity_curve_summary(row) for row in curves if str(row.get("instrument_id") or "") == selected_id),
        None,
    )

    return {
        "mode": workspace.get("mode"),
        "selected_instrument_id": selected_id or None,
        "provider": {
            "provider_id": coverage.get("provider_id"),
            "provider_label": coverage.get("provider_label"),
            "coverage_status": coverage.get("coverage_status"),
            "freshness_label": coverage.get("freshness_label"),
            "source_timestamp": _isoformat(coverage.get("source_timestamp")),
            "caveats": list(coverage.get("caveats", []) or []),
        },
        "counts": {
            "instruments": len(workspace.get("instruments", []) or []),
            "market_summaries": len(market_summaries),
            "curves": len(curves),
            "spreads": len(spreads),
            "inventories": len(inventories),
            "events": len(events),
            "cross_domain_links": len(cross_domain_links),
        },
        "selected_market": selected_summary,
        "selected_curve": selected_curve,
        "market_summaries": [_commodity_market_summary(row) for row in market_summaries[:summary_limit]],
        "spreads": [_commodity_spread_summary(row) for row in spreads[:spread_limit]],
        "inventories": [_commodity_inventory_summary(row) for row in inventories[:inventory_limit]],
        "events": [
            {
                "title": row.get("title"),
                "category": row.get("category"),
                "scheduled_at": _isoformat(row.get("scheduled_at")),
                "importance": row.get("importance"),
                "linked_instrument_ids": list(row.get("linked_instrument_ids", []) or []),
                "summary": row.get("summary"),
            }
            for row in events[:6]
        ],
        "cross_domain_links": [
            {
                "target_domain": row.get("target_domain"),
                "target_label": row.get("target_label"),
                "relationship": row.get("relationship"),
                "confidence": _as_float(row.get("confidence")),
                "linked_instrument_ids": list(row.get("linked_instrument_ids", []) or []),
                "summary": row.get("summary"),
            }
            for row in cross_domain_links[:6]
        ],
        "warnings": dedupe_warnings(workspace.get("warnings", []), coverage.get("caveats", [])),
    }


def resolve_iv_surface(
    surface: dict[str, Any] | None,
    session: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if surface and _surface_available(surface):
        return surface
    session_surface = (session or {}).get("surface")
    if isinstance(session_surface, dict) and _surface_available(session_surface):
        return session_surface
    return surface if surface else (session_surface if isinstance(session_surface, dict) else None)


def nearest_strike_index(strikes: list[float], spot: float | None) -> int:
    if not strikes or spot is None:
        return 0
    best_index = 0
    best_distance = float("inf")
    for index, strike in enumerate(strikes):
        distance = abs(strike - spot)
        if distance < best_distance:
            best_index = index
            best_distance = distance
    return best_index


def _surface_available(surface: dict[str, Any]) -> bool:
    if bool(surface.get("snapshot_available")):
        return True
    return (_as_int(surface.get("points")) or 0) > 0


def _position_summary(position: dict[str, Any] | None) -> dict[str, Any] | None:
    if not position:
        return None
    return {
        "symbol": position.get("display_symbol") or position.get("symbol"),
        "sec_type": position.get("sec_type"),
        "currency": position.get("currency"),
        "instrument_id": position.get("instrument_id"),
        "quantity": _as_float(position.get("quantity")),
        "weight": _as_float(position.get("weight")),
        "market_value": _as_float(position.get("market_value")),
        "base_market_value": _as_float(position.get("base_market_value")),
        "unrealized_pnl": _as_float(position.get("unrealized_pnl")),
    }


def _research_weight_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "symbol": row.get("display_symbol") or row.get("symbol"),
        "instrument_id": row.get("instrument_id"),
        "weight": _as_float(row.get("weight")),
    }


def _research_constituent_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "symbol": row.get("display_symbol") or row.get("symbol"),
        "instrument_id": row.get("instrument_id"),
        "weight": _as_float(row.get("weight")),
        "total_return": _as_float(row.get("total_return")),
        "annual_vol": _as_float(row.get("annual_vol")),
        "max_drawdown": _as_float(row.get("max_drawdown")),
        "weighted_return": _as_float(row.get("weighted_return")),
    }


def _risk_contribution_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "symbol": row.get("display_symbol") or row.get("symbol"),
        "instrument_id": row.get("instrument_id"),
        "weight": _as_float(row.get("weight")),
        "daily_vol": _as_float(row.get("daily_vol")),
        "variance_contribution_pct": _as_float(row.get("variance_contribution_pct")),
        "marginal_contribution_to_risk": _as_float(row.get("marginal_contribution_to_risk")),
        "component_var": _as_float(row.get("component_var")),
    }


def _commodity_market_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    instrument = _as_dict(row.get("instrument"))
    return {
        "instrument_id": instrument.get("instrument_id"),
        "symbol": instrument.get("symbol"),
        "name": instrument.get("name"),
        "family": instrument.get("family"),
        "latest_price": _as_float(row.get("latest_price")),
        "latest_change": _as_float(row.get("latest_change")),
        "latest_change_pct": _as_float(row.get("latest_change_pct")),
        "curve_state": row.get("curve_state"),
        "front_spread": _as_float(row.get("front_spread")),
        "inventory_signal": row.get("inventory_signal"),
        "summary": row.get("summary"),
        "warnings": list(row.get("warnings", []) or []),
    }


def _commodity_curve_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    nodes = [node for node in row.get("nodes", []) if isinstance(node, dict)]
    return {
        "instrument_id": row.get("instrument_id"),
        "as_of": _isoformat(row.get("as_of")),
        "shape_label": row.get("shape_label"),
        "front_spread": _as_float(row.get("front_spread")),
        "m1_m6_spread": _as_float(row.get("m1_m6_spread")),
        "curve_slope": _as_float(row.get("curve_slope")),
        "roll_yield_proxy_pct": _as_float(row.get("roll_yield_proxy_pct")),
        "summary": row.get("summary"),
        "front_nodes": [
            {
                "contract_month": _as_dict(node.get("contract")).get("contract_month"),
                "symbol": _as_dict(node.get("contract")).get("symbol"),
                "price": _as_float(node.get("price")),
                "change": _as_float(node.get("change")),
            }
            for node in nodes[:6]
        ],
        "warnings": list(row.get("warnings", []) or []),
    }


def _commodity_spread_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    definition = _as_dict(row.get("definition"))
    return {
        "spread_id": definition.get("spread_id"),
        "label": definition.get("label"),
        "spread_type": definition.get("spread_type"),
        "formula": definition.get("formula"),
        "value": _as_float(row.get("value")),
        "change": _as_float(row.get("change")),
        "z_score": _as_float(row.get("z_score")),
        "percentile": _as_float(row.get("percentile")),
        "interpretation": row.get("interpretation"),
        "warnings": list(row.get("warnings", []) or []),
    }


def _commodity_inventory_summary(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    metadata = _as_dict(row.get("metadata"))
    return {
        "series_id": metadata.get("series_id"),
        "instrument_id": metadata.get("instrument_id"),
        "label": metadata.get("label"),
        "category": metadata.get("category"),
        "unit": metadata.get("unit"),
        "latest_value": _as_float(row.get("latest_value")),
        "latest_change": _as_float(row.get("latest_change")),
        "seasonal_percentile": _as_float(row.get("seasonal_percentile")),
        "interpretation": row.get("interpretation"),
        "provider_series_id": metadata.get("provider_series_id"),
        "warnings": list(row.get("warnings", []) or []),
    }


def _best_position(
    positions: list[dict[str, Any]],
    *,
    key: str,
    absolute: bool,
) -> dict[str, Any] | None:
    return _best_row(positions, key=key, absolute=absolute)


def _worst_position(
    positions: list[dict[str, Any]],
    *,
    key: str,
    absolute: bool,
) -> dict[str, Any] | None:
    return _worst_row(positions, key=key, absolute=absolute)


def _best_row(rows: list[dict[str, Any]], *, key: str, absolute: bool) -> dict[str, Any] | None:
    winner: dict[str, Any] | None = None
    winner_score = float("-inf")
    for row in rows:
        value = _as_float(row.get(key))
        if value is None:
            continue
        score = abs(value) if absolute else value
        if score > winner_score:
            winner_score = score
            winner = row
    return winner


def _worst_row(rows: list[dict[str, Any]], *, key: str, absolute: bool) -> dict[str, Any] | None:
    winner: dict[str, Any] | None = None
    winner_score = float("inf")
    for row in rows:
        value = _as_float(row.get(key))
        if value is None:
            continue
        score = abs(value) if absolute else value
        if score < winner_score:
            winner_score = score
            winner = row
    return winner


def _bucket_counts(values: list[str], *, limit: int) -> list[dict[str, Any]]:
    counter = Counter(value for value in values if value)
    rows = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [{"key": key, "count": count} for key, count in rows[:limit]]


def _is_cash_position(position: dict[str, Any]) -> bool:
    symbol = str(position.get("symbol") or "")
    sec_type = str(position.get("sec_type") or "")
    return sec_type == "CASH" or symbol.startswith("CASH")


def _drawdown_from_values(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak) - 1.0)
    return max_drawdown


def _drawdown_from_index_points(points: list[dict[str, Any]]) -> float | None:
    values = [_point_value(point, "value") for point in points]
    clean_values = [value for value in values if value is not None]
    return _drawdown_from_values(clean_values)


def _surface_value(iv_grid: list[Any], row_index: int, column_index: int) -> float | None:
    if row_index < 0 or column_index < 0:
        return None
    if row_index >= len(iv_grid):
        return None
    row = iv_grid[row_index]
    if not isinstance(row, list) or column_index >= len(row):
        return None
    return _as_float(row[column_index])


def _point_value(point: dict[str, Any], key: str) -> float | None:
    return _as_float(point.get(key)) if point else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, percentile)) * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    weight = position - lower_index
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    return lower + (upper - lower) * weight


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:
        return None
    return numeric


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_int(value: Any) -> int | None:
    numeric = _as_float(value)
    if numeric is None:
        return None
    return int(numeric)
