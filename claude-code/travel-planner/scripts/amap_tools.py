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
        except urllib.error.URLError as exc:
            raise SystemExit(f"AMap request failed: {exc}") from exc
        if payload.get("status") == "1":
            return payload

        info = str(payload.get("info") or payload.get("infocode") or "Unknown error")
        if "EXCEEDED_THE_LIMIT" in info and attempt < 3:
            time.sleep(0.6 * (attempt + 1))
            continue
        raise SystemExit(f"AMap API error: {info}")

    raise SystemExit("AMap API error: retry limit exceeded")


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
        raise SystemExit(f"No geocode result for: {query}")
    top = geocodes[0]
    lng, lat = parse_location(top["location"])
    result = {
        "query": query,
        "matched_address": top.get("formatted_address"),
        "country": top.get("country"),
        "province": top.get("province"),
        "city": top.get("city"),
        "district": top.get("district"),
        "adcode": top.get("adcode"),
        "location": {"lng": float(lng), "lat": float(lat)},
    }
    GEOCODE_CACHE[cache_key] = result
    return result


def route(origin: str, destination: str, mode: str, city: str | None) -> dict:
    origin_geo = geocode(origin, city)
    destination_geo = geocode(destination, city)
    params = {
        "origin": f"{origin_geo['location']['lng']},{origin_geo['location']['lat']}",
        "destination": (
            f"{destination_geo['location']['lng']},"
            f"{destination_geo['location']['lat']}"
        ),
    }

    if mode == "walking":
        payload = fetch_json("/v3/direction/walking", params)
        path = payload["route"]["paths"][0]
        duration_seconds = int(path["duration"])
        distance_meters = int(path["distance"])
        details = {
            "steps": len(path.get("steps", [])),
        }
        resolved_mode = "walking"
    elif mode == "driving":
        payload = fetch_json("/v3/direction/driving", params)
        path = payload["route"]["paths"][0]
        duration_seconds = int(path["duration"])
        distance_meters = int(path["distance"])
        details = {
            "tolls_cny": float(path.get("tolls", 0)),
            "strategy": payload.get("route", {}).get("strategy"),
            "traffic_lights": int(path.get("traffic_lights", 0)),
        }
        resolved_mode = "driving"
    elif mode == "transit":
        payload = fetch_json("/v3/direction/transit/integrated", params)
        transits = payload["route"].get("transits", [])
        if transits:
            top = transits[0]
            duration_seconds = int(top["duration"])
            distance_meters = int(top["distance"])
            details = {
                "walking_distance_m": int(top.get("walking_distance", 0)),
                "cost_cny": float(top.get("cost", 0)),
                "segments": len(top.get("segments", [])),
            }
            resolved_mode = "transit"
        else:
            payload = fetch_json("/v3/direction/walking", params)
            path = payload["route"]["paths"][0]
            duration_seconds = int(path["duration"])
            distance_meters = int(path["distance"])
            details = {
                "steps": len(path.get("steps", [])),
                "fallback_reason": "no transit route found",
            }
            resolved_mode = "walking"
    else:
        raise SystemExit(f"Unsupported mode: {mode}")

    return {
        "mode": mode,
        "resolved_mode": resolved_mode,
        "origin": origin_geo,
        "destination": destination_geo,
        "duration_minutes": round(duration_seconds / 60, 1),
        "distance_km": round(distance_meters / 1000, 2),
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
    parser = argparse.ArgumentParser(description="AMap tools for travel-planner skill")
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
