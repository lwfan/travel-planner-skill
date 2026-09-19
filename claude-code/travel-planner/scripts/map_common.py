"""Shared route validation and comparison helpers; no API calls or credentials."""

from __future__ import annotations

import argparse
import math
from typing import Callable


MODES = ("subway", "taxi", "walking", "bus", "transit", "driving")
PUBLIC_MODES = {"subway", "bus", "transit"}
DEFAULT_MAX_WALK_KM = 1.5
DEFAULT_MAX_WALK_MINUTES = 25.0


class MapError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def error_result(exc: MapError) -> dict:
    return {
        "status": exc.code if exc.code in {"no_route", "unsupported"} else "error",
        "error": {"code": exc.code, "message": str(exc)},
        "duration_minutes": None,
        "distance_km": None,
    }


def call_safely(fn: Callable, *args, **kwargs) -> dict:
    try:
        return {"status": "ok", **fn(*args, **kwargs)}
    except MapError as exc:
        return error_result(exc)
    except SystemExit as exc:
        return error_result(MapError("configuration_error", str(exc)))


def route_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=MODES, default="transit")
    parser.add_argument("--city", help="Common city hint for both endpoints")
    parser.add_argument("--origin-city", help="Origin city; overrides --city for origin")
    parser.add_argument("--destination-city", help="Destination city; overrides --city for destination")
    parser.add_argument("--max-walk-km", type=nonnegative, default=DEFAULT_MAX_WALK_KM,
                        help="Maximum fallback walk distance; 0 disables walking fallback")
    parser.add_argument("--max-walk-minutes", type=nonnegative, default=DEFAULT_MAX_WALK_MINUTES,
                        help="Maximum fallback walk duration; 0 disables walking fallback")


def nonnegative(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Must be a finite nonnegative number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("Must be a finite nonnegative number")
    return parsed


def options_from_args(args: argparse.Namespace) -> dict:
    return {name: getattr(args, name) for name in (
        "origin_city", "destination_city", "max_walk_km", "max_walk_minutes"
    )}


def route_list(payload: dict, container: str, key: str) -> list[dict]:
    parent = payload.get(container)
    if not isinstance(parent, dict) or not isinstance(parent.get(key), list):
        raise MapError("invalid_response", f"Missing or invalid {container}.{key} route list")
    routes = parent[key]
    if any(not isinstance(item, dict) for item in routes):
        raise MapError("invalid_response", f"Invalid item in {container}.{key}")
    return routes


def first_route(payload: dict, container: str, key: str) -> dict:
    routes = route_list(payload, container, key)
    if not routes:
        raise MapError("no_route", "No route found for the requested travel mode")
    return routes[0]


def number(value, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise MapError("invalid_response", f"Invalid route field: {field}") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise MapError("invalid_response", f"Invalid route field: {field}")
    return parsed


def optional_number(value, field: str) -> float | None:
    if value in (None, "", []):
        return None
    return number(value, field)


def validate_walk_limits(max_walk_km: float, max_walk_minutes: float) -> None:
    for value in (max_walk_km, max_walk_minutes):
        if not math.isfinite(value) or value < 0:
            raise MapError("invalid_input", "Walking fallback limits must be finite and nonnegative")


def check_fallback_walk(path: dict, max_walk_km: float, max_walk_minutes: float) -> None:
    distance = number(path.get("distance"), "distance")
    duration = number(path.get("duration"), "duration")
    if distance > max_walk_km * 1000 or duration > max_walk_minutes * 60:
        raise MapError("no_route", "No public transport route; walking exceeds the configured fallback limits")


def compare_routes(areas: list[str], anchors: list[str], mode: str,
                   city: str | None, route_call: Callable[[str, str], dict]) -> dict:
    if len(areas) < 2:
        raise MapError("invalid_input", "compare-areas requires at least two areas")
    if not anchors:
        raise MapError("invalid_input", "compare-areas requires at least one anchor")
    ranked, incomplete = [], []
    for area in areas:
        routes = []
        durations = []
        for anchor in anchors:
            result = route_call(area, anchor)
            entry = {"anchor": anchor, "status": result.get("status", "ok")}
            for field in ("provider_used", "resolved_mode", "duration_minutes", "distance_km", "details", "error"):
                if field in result:
                    entry[field] = result[field]
            if entry["status"] == "ok":
                durations.append(number(result.get("duration_minutes"), "duration_minutes"))
            routes.append(entry)
        complete = len(durations) == len(anchors)
        row = {
            "area": area,
            "status": "complete" if complete else ("partial" if durations else "unavailable"),
            "valid_routes": len(durations),
            "total_routes": len(anchors),
            "coverage": round(len(durations) / len(anchors), 3),
            "average_duration_minutes": round(sum(durations) / len(anchors), 1) if complete else None,
            "anchors": routes,
        }
        (ranked if complete else incomplete).append(row)
    ranked.sort(key=lambda row: row["average_duration_minutes"])
    return {
        "status": "ok" if not incomplete else "partial",
        "mode": mode,
        "city": city,
        "anchors": anchors,
        "ranking_policy": "Only areas with a valid route to every anchor are ranked",
        "ranked_areas": ranked,
        "incomplete_areas": incomplete,
    }
