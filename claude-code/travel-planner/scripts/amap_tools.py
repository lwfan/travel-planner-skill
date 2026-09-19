#!/usr/bin/env python3
"""Minimal AMap helpers for travel-planner skill."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from map_common import (
    DEFAULT_MAX_WALK_KM, DEFAULT_MAX_WALK_MINUTES, MODES, PUBLIC_MODES, MapError,
    call_safely, check_fallback_walk, compare_routes, first_route, number,
    optional_number, options_from_args, route_list, route_options, validate_walk_limits,
)


SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_CANDIDATES = (
    SKILL_ROOT / "amap-config.local.json",
    SKILL_ROOT / "amap-config.json",
)
GEOCODE_CACHE: dict[tuple[str, str | None], dict] = {}


def load_api_key() -> str:
    for path in CONFIG_CANDIDATES:
        if path.exists():
            data = json.loads(path.read_text())
            api_key = str(data.get("api_key", "")).strip()
            if api_key:
                return api_key
    api_key = str(__import__("os").environ.get("AMAP_API_KEY", "")).strip()
    if api_key:
        return api_key
    raise SystemExit(
        "Missing AMap API key. Put it in amap-config.local.json or AMAP_API_KEY."
    )


def fetch_json(endpoint: str, params: dict[str, str]) -> dict:
    params = dict(params)
    params["key"] = load_api_key()
    url = f"https://restapi.amap.com{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "travel-planner-skill/1.0",
            "Accept": "application/json",
        },
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as exc:
            raise MapError("network_error", f"AMap request failed: {exc}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MapError("invalid_response", "AMap returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise MapError("invalid_response", "AMap returned a non-object response")
        if payload.get("status") == "1":
            return payload

        info = str(payload.get("info") or payload.get("infocode") or "Unknown error")
        if "EXCEEDED_THE_LIMIT" in info and attempt < 3:
            time.sleep(0.6 * (attempt + 1))
            continue
        raise MapError("api_error", f"AMap API error: {info}")

    raise MapError("api_error", "AMap API error: retry limit exceeded")


def parse_location(location: str) -> tuple[str, str]:
    lng, lat = location.split(",", 1)
    return lng, lat


def geocode(query: str, city: str | None) -> dict:
    cache_key = (query, city)
    if cache_key in GEOCODE_CACHE:
        return GEOCODE_CACHE[cache_key]

    params = {"address": query}
    if city:
        params["city"] = city
    payload = fetch_json("/v3/geocode/geo", params)
    geocodes = payload.get("geocodes", [])
    if not geocodes:
        raise MapError("no_location", f"No geocode result for: {query}")
    top = geocodes[0]
    lng, lat = parse_location(top["location"])
    result = {
        "query": query,
        "matched_address": top.get("formatted_address"),
        "country": top.get("country"),
        "province": top.get("province"),
        "city": top.get("city"),
        "citycode": top.get("citycode"),
        "district": top.get("district"),
        "adcode": top.get("adcode"),
        "location": {"lng": float(lng), "lat": float(lat)},
    }
    GEOCODE_CACHE[cache_key] = result
    return result


def _city(geo: dict, hint: str | None) -> str:
    # City codes are suitable for the transit API; district adcodes are not.
    for value in (hint, geo.get("citycode"), geo.get("city")):
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise MapError("invalid_input", "Public transport requires an origin/destination city hint")


def _transit_details(transit: dict) -> dict:
    """Summarize selected legs; transfers are known boardings minus the first boarding.

    Walking never counts as a boarding. Both metrics stay unknown (None) if a
    segment cannot be interpreted, a selected mode is unknown, or there is no
    verified vehicle leg. Segment containers and busline alternatives are not
    transfer counts.
    """
    segments = transit.get("segments", [])
    if not isinstance(segments, list) or any(not isinstance(seg, dict) for seg in segments):
        raise MapError("invalid_response", "Invalid public transport segments")
    legs = []
    complete_legs = bool(segments)
    for segment in segments:
        first_leg = len(legs)
        # Non-empty, unrecognized payloads may hide a connection. Do not turn
        # partial leg evidence into a falsely low transfer count.
        known_fields = {"walking", "bus", "railway", "taxi", "entrance", "exit"}
        if any(value and key not in known_fields for key, value in segment.items()):
            complete_legs = False
        if any(segment.get(key) and not isinstance(segment[key], dict)
               for key in ("walking", "bus", "railway", "taxi")):
            complete_legs = False
        walking = segment.get("walking")
        if isinstance(walking, dict) and walking:
            legs.append({"mode": "walking", "distance_m": optional_number(walking.get("distance"), "walking.distance")})
        bus = segment.get("bus")
        if isinstance(bus, dict):
            if bus and "buslines" not in bus:
                complete_legs = False
            buslines = bus.get("buslines", [])
            if not isinstance(buslines, list) or any(not isinstance(line, dict) for line in buslines):
                raise MapError("invalid_response", "Invalid public transport buslines")
            # A busline list contains alternatives for a leg; retain the selected first option.
            if buslines:
                line = buslines[0]
                line_type = line.get("type")
                actual_mode = "subway" if line_type == "地铁线路" else (
                    "bus" if isinstance(line_type, str) and "公交" in line_type else "unknown"
                )
                legs.append({
                    "mode": actual_mode, "name": line.get("name"), "type": line_type,
                    "departure_stop": line["departure_stop"].get("name") if isinstance(line.get("departure_stop"), dict) else None,
                    "arrival_stop": line["arrival_stop"].get("name") if isinstance(line.get("arrival_stop"), dict) else None,
                })
        railway = segment.get("railway")
        if isinstance(railway, dict) and railway:
            legs.append({"mode": "railway", "name": railway.get("name"), "type": railway.get("type")})
        taxi = segment.get("taxi")
        if isinstance(taxi, dict) and taxi:
            legs.append({"mode": "taxi", "distance_m": optional_number(taxi.get("distance"), "taxi.distance")})
        if len(legs) == first_leg:
            complete_legs = False
    actual_modes = sorted({leg["mode"] for leg in legs})
    verified_boardings = sum(leg["mode"] in {"subway", "bus", "railway", "taxi"} for leg in legs)
    boarding_count = verified_boardings if complete_legs and "unknown" not in actual_modes and verified_boardings else None
    return {
        "walking_distance_m": optional_number(transit.get("walking_distance"), "walking_distance"),
        "cost_cny": optional_number(transit.get("cost"), "cost"),
        "segments": len(segments), "legs": legs, "actual_modes": actual_modes,
        "boarding_count": boarding_count,
        "transfers": boarding_count - 1 if boarding_count is not None else None,
    }


def route(origin: str, destination: str, mode: str, city: str | None,
          *, origin_city: str | None = None, destination_city: str | None = None,
          max_walk_km: float = DEFAULT_MAX_WALK_KM,
          max_walk_minutes: float = DEFAULT_MAX_WALK_MINUTES) -> dict:
    if mode not in MODES:
        raise MapError("unsupported", f"Unsupported mode: {mode}")
    validate_walk_limits(max_walk_km, max_walk_minutes)
    origin_hint, destination_hint = origin_city or city, destination_city or city
    origin_geo = geocode(origin, origin_hint)
    destination_geo = geocode(destination, destination_hint)
    params = {
        "origin": f"{origin_geo['location']['lng']},{origin_geo['location']['lat']}",
        "destination": (
            f"{destination_geo['location']['lng']},"
            f"{destination_geo['location']['lat']}"
        ),
    }

    if mode == "walking":
        payload = fetch_json("/v3/direction/walking", params)
        path = first_route(payload, "route", "paths")
        details = {
            "steps": len(path.get("steps", [])),
        }
        resolved_mode = "walking"
    elif mode in {"driving", "taxi"}:
        payload = fetch_json("/v3/direction/driving", params)
        path = first_route(payload, "route", "paths")
        details = {
            "tolls_cny": optional_number(path.get("tolls"), "tolls"),
            "strategy": payload.get("route", {}).get("strategy"),
            "traffic_lights": optional_number(path.get("traffic_lights"), "traffic_lights"),
        }
        if mode == "taxi":
            details["estimate_note"] = "Driving-time estimate for a taxi; excludes waiting and does not quote a fare"
        resolved_mode = "driving"
    elif mode in PUBLIC_MODES:
        transit_params = {
            **params,
            "city": _city(origin_geo, origin_hint),
            "cityd": _city(destination_geo, destination_hint),
            "strategy": "5" if mode == "bus" else "0",
        }
        payload = fetch_json("/v3/direction/transit/integrated", transit_params)
        transits = route_list(payload, "route", "transits")
        if transits:
            candidates = [(candidate, _transit_details(candidate)) for candidate in transits]
            if mode == "subway":
                candidates = [pair for pair in candidates if "subway" in pair[1]["actual_modes"]]
                if not candidates:
                    raise MapError("no_route", "No returned public transport candidate contains a verified subway leg")
            elif mode == "bus":
                candidates = [pair for pair in candidates if "subway" not in pair[1]["actual_modes"]]
                if not candidates:
                    raise MapError("invalid_response", "AMap returned subway routes despite the no-subway strategy")
            path, details = candidates[0]
            details["selection"] = {
                "subway": "First returned candidate with a verified subway leg; may include bus or rail connections",
                "bus": "No-subway strategy (5); inspect actual legs for other public transport",
                "transit": "Public transport mix selected by the provider",
            }[mode]
            motor_modes = set(details["actual_modes"]) - {"walking"}
            resolved_mode = "transit"
            if motor_modes == {"subway"}:
                resolved_mode = "subway"
            elif motor_modes == {"bus"}:
                resolved_mode = "bus"
        else:
            if max_walk_km == 0 or max_walk_minutes == 0:
                raise MapError("no_route", "No public transport route; walking fallback is disabled")
            payload = fetch_json("/v3/direction/walking", params)
            path = first_route(payload, "route", "paths")
            check_fallback_walk(path, max_walk_km, max_walk_minutes)
            details = {
                "steps": len(path.get("steps", [])),
                "fallback_reason": "no public transport route found; short walk offered as an alternative",
                "fallback_from": mode,
                "max_walk_km": max_walk_km, "max_walk_minutes": max_walk_minutes,
            }
            resolved_mode = "walking"

    return {
        "status": "ok",
        "mode": mode,
        "resolved_mode": resolved_mode,
        "origin": origin_geo,
        "destination": destination_geo,
        "duration_minutes": round(number(path.get("duration"), "duration") / 60, 1),
        "distance_km": round(number(path.get("distance"), "distance") / 1000, 2),
        "details": details,
    }


def compare_areas(areas: list[str], anchors: list[str], mode: str, city: str | None, **options) -> dict:
    return compare_routes(areas, anchors, mode, city,
                          lambda area, anchor: call_safely(route, area, anchor, mode, city, **options))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AMap tools for travel-planner skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    geocode_parser = subparsers.add_parser("geocode")
    geocode_parser.add_argument("--query", required=True)
    geocode_parser.add_argument("--city")

    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("--origin", required=True)
    route_parser.add_argument("--destination", required=True)
    route_options(route_parser)

    compare_parser = subparsers.add_parser("compare-areas")
    compare_parser.add_argument("--areas", nargs="+", required=True)
    compare_parser.add_argument("--anchors", nargs="+", required=True)
    route_options(compare_parser)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "geocode":
        result = call_safely(geocode, args.query, args.city)
    elif args.command == "route":
        result = call_safely(route, args.origin, args.destination, args.mode, args.city, **options_from_args(args))
    elif args.command == "compare-areas":
        result = call_safely(compare_areas, args.areas, args.anchors, args.mode, args.city, **options_from_args(args))
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
