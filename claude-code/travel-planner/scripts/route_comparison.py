"""Compare independently retrieved travel modes without inventing missing metrics."""

from __future__ import annotations

import math
from typing import Callable

from map_common import MODES, PUBLIC_MODES, MapError, call_safely, optional_number


PREFERENCES = {
    "fastest": "duration_minutes",
    "cheapest": "fare_cny",
    "least-walking": "walking_distance_m",
    "fewest-transfers": "transfers",
}
METRICS = ("duration_minutes", "fare_cny", "walking_distance_m", "transfers")


def _metric(value, field: str) -> float | None:
    if isinstance(value, bool):
        raise MapError("invalid_response", f"Invalid comparison metric: {field}")
    return optional_number(value, field)


def _metrics(mode: str, route: dict) -> dict:
    metrics = dict.fromkeys(METRICS)
    metrics["duration_minutes"] = _metric(route.get("duration_minutes"), "duration_minutes")
    if mode == "walking":
        distance = _metric(route.get("distance_km"), "distance_km")
        metrics.update(fare_cny=0, walking_distance_m=None if distance is None else round(distance * 1000, 3), transfers=0)
    elif mode in {"taxi", "driving"}:
        # Road tolls are not the fare; driving distance is not a walking estimate.
        metrics["transfers"] = 0
    else:
        details = route.get("details")
        if details is None:
            details = {}
        if not isinstance(details, dict):
            raise MapError("invalid_response", "Invalid route details for comparison")
        for field in ("cost_cny", "price_cny"):
            fare = _metric(details.get(field), field)
            if fare is not None:
                metrics["fare_cny"] = fare
                break
        metrics["walking_distance_m"] = _metric(details.get("walking_distance_m"), "walking_distance_m")
        transfers = _metric(details.get("transfers"), "transfers")
        if transfers is not None and not transfers.is_integer():
            raise MapError("invalid_response", "Transfer count must be a whole number")
        metrics["transfers"] = None if transfers is None else int(transfers)
    return metrics


def _option(mode: str, route: dict, objective: str, max_total_walk_km: float | None) -> dict:
    status = route.get("status", "ok")
    option = {
        "mode": mode,
        "status": status,
        "resolved_mode": route.get("resolved_mode"),
        "provider_used": route.get("provider_used"),
        "metrics": dict.fromkeys(METRICS),
        "eligibility": {"status": "excluded", "reasons": []},
        "notes": [],
        "route": route,
    }
    if status != "ok":
        option["eligibility"]["reasons"].append("Route unavailable; inspect the original route error")
        return option
    if mode in PUBLIC_MODES and route.get("resolved_mode") == "walking":
        # Defensive check if an adapter ignores the explicitly disabled fallback.
        option["status"] = "no_route"
        option["eligibility"]["reasons"].append("A walking replacement does not satisfy the requested public transport mode")
        return option
    try:
        metrics = _metrics(mode, route)
    except MapError as exc:
        option["status"] = "error"
        option["error"] = {"code": exc.code, "message": str(exc)}
        option["eligibility"]["reasons"].append("Route metrics need correction before comparison")
        return option
    option["metrics"] = metrics
    option["eligibility"]["status"] = "eligible"
    missing = [field for field, value in metrics.items() if value is None]
    if missing:
        option["notes"].append("Unknown metrics: " + ", ".join(missing))
    if mode in {"taxi", "driving"}:
        option["notes"].append("Map driving time excludes taxi waiting and access/egress; fare and walking access are unknown")
    elif mode in PUBLIC_MODES:
        option["notes"].append("Public transport details describe the returned route; inspect actual legs and any connections")
    if max_total_walk_km is not None:
        walked = metrics["walking_distance_m"]
        if walked is None:
            option["eligibility"]["status"] = "needs_verification"
            option["eligibility"]["reasons"].append("Total walking distance is unknown; compliance with the walking limit is unverified")
        elif walked > max_total_walk_km * 1000:
            option["eligibility"]["status"] = "excluded"
            option["eligibility"]["reasons"].append("Total walking distance exceeds the requested limit")
    if metrics[objective] is None:
        if option["eligibility"]["status"] == "eligible":
            option["eligibility"]["status"] = "needs_verification"
        option["eligibility"]["reasons"].append(f"The ranking metric {objective} is unknown")
    return option


def compare_modes(origin: str, destination: str, modes: list[str], city: str | None,
                  provider: str, route_call: Callable[..., dict], *, preference: str = "fastest",
                  max_total_walk_km: float | None = None, **route_options) -> dict:
    """Return all options in request order and an optional, explicitly scoped suggestion.

    ``route_call(mode, **route_options)`` must return the usual route result. Expected
    MapError/SystemExit failures are converted per mode; programming errors propagate.
    ``max_total_walk_km`` limits actual walking in every option, independently of the
    short-walk fallback limits used by single-route requests.
    """
    if preference not in PREFERENCES:
        raise MapError("invalid_input", f"Unknown comparison preference: {preference}")
    if not modes or isinstance(modes, str):
        raise MapError("invalid_input", "compare-modes requires at least one travel mode")
    if any(mode not in MODES for mode in modes):
        raise MapError("invalid_input", "Comparison modes must be supported travel modes")
    modes = list(dict.fromkeys(modes))
    if max_total_walk_km is not None:
        if isinstance(max_total_walk_km, bool) or not isinstance(max_total_walk_km, (int, float)) or not math.isfinite(max_total_walk_km) or max_total_walk_km < 0:
            raise MapError("invalid_input", "Total walking limit must be a finite nonnegative number")
    objective = PREFERENCES[preference]
    options = []
    for mode in modes:
        request_options = dict(route_options)
        if mode in PUBLIC_MODES:
            request_options.update(max_walk_km=0, max_walk_minutes=0)
        route = call_safely(route_call, mode, **request_options)
        options.append(_option(mode, route, objective, max_total_walk_km))

    candidates = [option for option in options if option["eligibility"]["status"] == "eligible"]
    candidates.sort(key=lambda option: option["metrics"][objective])
    if preference == "fastest":
        scope = "Among successful options satisfying the stated constraints with known map-returned durations; not complete door-to-door time"
    elif preference == "cheapest":
        scope = "Among successful options satisfying the stated constraints with known fares only; unknown fares are not zero and this is not an overall cheapest claim"
    else:
        scope = f"Among successful options satisfying the stated constraints with known {objective}; options with unknown values are not ranked"
    ranking_basis = {"metric": objective, "direction": "ascending", "scope": scope,
                     "tie_break": "Request order; tied options remain available", "weighted_score": False}
    recommendation = None
    reason = None
    if candidates:
        best = candidates[0]
        best_value = best["metrics"][objective]
        recommendation = {
            "kind": "suggestion",
            "mode": best["mode"],
            "metric": objective,
            "value": best_value,
            "reason": f"Lowest known {objective} in the eligible comparison set. {scope}",
            "tied_modes": [option["mode"] for option in candidates if option["metrics"][objective] == best_value],
        }
    else:
        succeeded = [option for option in options if option["status"] == "ok"]
        if not succeeded:
            reason = "No mode returned a usable route; all requested options and their errors are retained"
        elif all(option["metrics"][objective] is None for option in succeeded):
            reason = f"All successful options have unknown {objective}; no evidence-based suggestion is available"
        else:
            reason = "No successful option has both a known ranking metric and verified compliance with the stated walking limit"
    successes = sum(option["status"] == "ok" for option in options)
    status = "ok" if successes == len(options) else "partial"
    if not successes:
        statuses = {option["status"] for option in options}
        status = next(iter(statuses)) if statuses in ({"no_route"}, {"unsupported"}) else "error"
    notes = [
        "All requested options remain available for the user to choose; the recommendation is only a suggestion",
        "Public transport walking fallback is disabled during mode comparison",
        "Unknown metrics remain null; estimates and actual connections should be reviewed before choosing",
    ]
    if len(modes) == 1:
        notes.append("Only one distinct mode was requested; no alternative modes were compared")
    return {
        "status": status,
        "origin": origin, "destination": destination, "city": city, "provider": provider,
        "modes": modes, "preference": preference,
        "constraints": {"max_total_walk_km": max_total_walk_km},
        "options": options,
        "ranking_basis": ranking_basis,
        "ranking": [option["mode"] for option in candidates],
        "recommendation": recommendation,
        "recommendation_reason": reason,
        "notes": notes,
    }
