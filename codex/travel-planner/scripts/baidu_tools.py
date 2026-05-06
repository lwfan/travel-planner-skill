#!/usr/bin/env python3
"""Baidu Map helpers for travel-planner skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
CONFIG_CANDIDATES = (
    SKILL_ROOT / "baidu-config.local.json",
    SKILL_ROOT / "baidu-config.json",
)
GEOCODE_CACHE: dict[tuple[str, str | None], dict] = {}


def load_config() -> dict[str, str]:
    config: dict[str, str] = {"enabled": "false"}
    for path in CONFIG_CANDIDATES:
        if path.exists():
            raw = json.loads(path.read_text())
            config.update({k: str(v) for k, v in raw.items()})
            break

    config.setdefault("ak", os.environ.get("BAIDU_MAP_AK", ""))
    config.setdefault("sk", os.environ.get("BAIDU_MAP_SK", ""))
    config.setdefault("app_id", os.environ.get("BAIDU_MAP_APP_ID", ""))
    config.setdefault("app_name", os.environ.get("BAIDU_MAP_APP_NAME", ""))
    return {key: value.strip() for key, value in config.items()}


def is_enabled() -> bool:
    return load_config().get("enabled", "false").lower() == "true"


def is_configured() -> bool:
    config = load_config()
    return is_enabled() and bool(config.get("ak") and config.get("sk"))


def ensure_configured() -> dict[str, str]:
    config = load_config()
    if not is_enabled():
        raise SystemExit(
            "Baidu Map backend is disabled in baidu-config.local.json. "
            "Set `enabled` to true to re-enable it."
        )
    if not config.get("ak"):
        raise SystemExit(
            "Missing Baidu Map AK. Put it in baidu-config.local.json or BAIDU_MAP_AK."
        )
    if not config.get("sk"):
        raise SystemExit(
            "Missing Baidu Map SK for sn validation. Add `sk` to "
            "baidu-config.local.json or BAIDU_MAP_SK."
        )
    return config


def build_signed_query(
    uri: str,
    params: list[tuple[str, str]],
    config: dict[str, str],
) -> str:
    signed_params = list(params)
    signed_params.append(("ak", config["ak"]))
    signed_params.append(("timestamp", str(int(time.time()))))

    query = urllib.parse.urlencode(signed_params)
    raw = f"{uri}?{query}{config['sk']}"
    sn = hashlib.md5(urllib.parse.quote_plus(raw).encode("utf-8")).hexdigest()
    return f"{query}&sn={sn}"


def fetch_json(uri: str, params: list[tuple[str, str]]) -> dict:
    config = ensure_configured()
    query = build_signed_query(uri, params, config)
    url = f"https://api.map.baidu.com{uri}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "travel-planner-skill/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SystemExit(f"Baidu Map request failed: {exc}") from exc

    status = int(payload.get("status", -1))
    if status != 0:
        message = payload.get("message") or payload.get("msg") or f"status={status}"
        raise SystemExit(f"Baidu Map API error: {message}")
    return payload


def geocode(query: str, city: str | None) -> dict:
    cache_key = (query, city)
    if cache_key in GEOCODE_CACHE:
        return GEOCODE_CACHE[cache_key]

    address = f"{city}{query}" if city and not query.startswith(city) else query
    payload = fetch_json(
        "/geocoder/v2/",
        [
            ("address", address),
            ("output", "json"),
        ],
    )
    result = payload["result"]
    geo = {
        "query": query,
        "matched_address": result.get("formatted_address", address),
        "province": result.get("addressComponent", {}).get("province"),
        "city": result.get("addressComponent", {}).get("city") or city,
        "district": result.get("addressComponent", {}).get("district"),
        "location": {
            "lng": float(result["location"]["lng"]),
            "lat": float(result["location"]["lat"]),
        },
    }
    GEOCODE_CACHE[cache_key] = geo
    return geo


def _baidu_coord(geo: dict) -> str:
    return f"{geo['location']['lat']},{geo['location']['lng']}"


def route(origin: str, destination: str, mode: str, city: str | None) -> dict:
    origin_geo = geocode(origin, city)
    destination_geo = geocode(destination, city)
    base_params = [
        ("origin", _baidu_coord(origin_geo)),
        ("destination", _baidu_coord(destination_geo)),
        ("coord_type", "bd09ll"),
        ("ret_coordtype", "bd09ll"),
        ("output", "json"),
    ]

    if mode == "walking":
        payload = fetch_json("/directionlite/v1/walking", base_params)
        route_data = payload["result"]["routes"][0]
        details = {
            "steps": len(route_data.get("steps", [])),
        }
        resolved_mode = "walking"
    elif mode == "driving":
        payload = fetch_json("/directionlite/v1/driving", base_params)
        route_data = payload["result"]["routes"][0]
        details = {
            "toll_cny": float(route_data.get("toll", 0)),
            "traffic_condition": route_data.get("traffic_condition"),
        }
        resolved_mode = "driving"
    elif mode == "transit":
        transit_params = list(base_params)
        if city:
            transit_params.append(("origin_region", city))
            transit_params.append(("destination_region", city))
        try:
            payload = fetch_json("/directionlite/v1/transit", transit_params)
            route_data = payload["result"]["routes"][0]
            details = {
                "price_cny": float(route_data.get("price", 0)),
                "steps": len(route_data.get("steps", [])),
            }
            resolved_mode = "transit"
        except SystemExit as exc:
            payload = fetch_json("/directionlite/v1/walking", base_params)
            route_data = payload["result"]["routes"][0]
            details = {
                "steps": len(route_data.get("steps", [])),
                "fallback_reason": str(exc),
            }
            resolved_mode = "walking"
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    return {
        "mode": mode,
        "resolved_mode": resolved_mode,
        "origin": origin_geo,
        "destination": destination_geo,
        "duration_minutes": round(float(route_data["duration"]) / 60, 1),
        "distance_km": round(float(route_data["distance"]) / 1000, 2),
        "details": details,
    }


def compare_areas(areas: list[str], anchors: list[str], mode: str, city: str | None) -> dict:
    if len(areas) < 2:
        raise SystemExit("compare-areas requires at least two areas")
    if not anchors:
        raise SystemExit("compare-areas requires at least one anchor")

    results = []
    for area in areas:
        anchor_routes = []
        total_minutes = 0.0
        for anchor in anchors:
            route_result = route(area, anchor, mode, city)
            anchor_routes.append(
                {
                    "anchor": anchor,
                    "resolved_mode": route_result["resolved_mode"],
                    "duration_minutes": route_result["duration_minutes"],
                    "distance_km": route_result["distance_km"],
                }
            )
            total_minutes += route_result["duration_minutes"]
            if mode == "transit":
                time.sleep(0.2)
        results.append(
            {
                "area": area,
                "average_duration_minutes": round(total_minutes / len(anchors), 1),
                "anchors": anchor_routes,
            }
        )

    results.sort(key=lambda item: item["average_duration_minutes"])
    return {
        "mode": mode,
        "city": city,
        "anchors": anchors,
        "ranked_areas": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Baidu Map tools for travel-planner skill")
    subparsers = parser.add_subparsers(dest="command", required=True)

    geocode_parser = subparsers.add_parser("geocode")
    geocode_parser.add_argument("--query", required=True)
    geocode_parser.add_argument("--city")

    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("--origin", required=True)
    route_parser.add_argument("--destination", required=True)
    route_parser.add_argument(
        "--mode",
        choices=("walking", "driving", "transit"),
        default="transit",
    )
    route_parser.add_argument("--city")

    compare_parser = subparsers.add_parser("compare-areas")
    compare_parser.add_argument("--areas", nargs="+", required=True)
    compare_parser.add_argument("--anchors", nargs="+", required=True)
    compare_parser.add_argument(
        "--mode",
        choices=("walking", "driving", "transit"),
        default="transit",
    )
    compare_parser.add_argument("--city")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "geocode":
        result = geocode(args.query, args.city)
    elif args.command == "route":
        result = route(args.origin, args.destination, args.mode, args.city)
    elif args.command == "compare-areas":
        result = compare_areas(args.areas, args.anchors, args.mode, args.city)
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
