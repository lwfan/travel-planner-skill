#!/usr/bin/env python3
"""Unified map tools with AMap primary and Baidu fallback."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Callable

import amap_tools
import baidu_tools


ProviderCall = Callable[..., dict]


def provider_order(preferred: str) -> list[str]:
    if preferred == "amap":
        return ["amap"]
    if preferred == "baidu":
        return ["baidu"]
    return ["amap"]


def provider_ready(provider: str) -> bool:
    if provider == "amap":
        try:
            amap_tools.load_api_key()
            return True
        except SystemExit:
            return False
    if provider == "baidu":
        return baidu_tools.is_configured()
    return False


def run_with_fallback(
    preferred: str,
    call_name: str,
    *args,
) -> dict:
    errors: list[str] = []
    order = provider_order(preferred)
    for index, provider in enumerate(order):
        if not provider_ready(provider):
            if preferred != "auto":
                try:
                    if provider == "amap":
                        provider_fn = getattr(amap_tools, call_name)
                    else:
                        provider_fn = getattr(baidu_tools, call_name)
                    provider_fn(*args)
                except SystemExit as exc:
                    raise SystemExit(str(exc)) from exc
            errors.append(f"{provider}: not configured")
            continue
        try:
            if provider == "amap":
                provider_fn: ProviderCall = getattr(amap_tools, call_name)
            else:
                provider_fn = getattr(baidu_tools, call_name)
            result = provider_fn(*args)
            result["provider_used"] = provider
            if preferred == "auto" and index > 0:
                result["fallback_used"] = True
            return result
        except SystemExit as exc:
            errors.append(f"{provider}: {exc}")
            continue
    raise SystemExit(" ; ".join(errors) or "No map provider available")


def compare_areas(
    areas: list[str],
    anchors: list[str],
    mode: str,
    city: str | None,
    provider: str,
) -> dict:
    if len(areas) < 2:
        raise SystemExit("compare-areas requires at least two areas")
    if not anchors:
        raise SystemExit("compare-areas requires at least one anchor")

    ranked_areas = []
    for area in areas:
        anchor_routes = []
        total_minutes = 0.0
        for anchor in anchors:
            route_result = run_with_fallback(provider, "route", area, anchor, mode, city)
            anchor_routes.append(
                {
                    "anchor": anchor,
                    "provider_used": route_result["provider_used"],
                    "resolved_mode": route_result["resolved_mode"],
                    "duration_minutes": route_result["duration_minutes"],
                    "distance_km": route_result["distance_km"],
                }
            )
            total_minutes += route_result["duration_minutes"]
        ranked_areas.append(
            {
                "area": area,
                "average_duration_minutes": round(total_minutes / len(anchors), 1),
                "anchors": anchor_routes,
            }
        )

    ranked_areas.sort(key=lambda item: item["average_duration_minutes"])
    return {
        "mode": mode,
        "city": city,
        "provider_order": provider_order(provider),
        "anchors": anchors,
        "ranked_areas": ranked_areas,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified map tools with AMap primary and Baidu fallback"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    geocode_parser = subparsers.add_parser("geocode")
    geocode_parser.add_argument("--query", required=True)
    geocode_parser.add_argument("--city")
    geocode_parser.add_argument(
        "--provider",
        choices=("auto", "amap", "baidu"),
        default="auto",
    )

    route_parser = subparsers.add_parser("route")
    route_parser.add_argument("--origin", required=True)
    route_parser.add_argument("--destination", required=True)
    route_parser.add_argument(
        "--mode",
        choices=("walking", "driving", "transit"),
        default="transit",
    )
    route_parser.add_argument("--city")
    route_parser.add_argument(
        "--provider",
        choices=("auto", "amap", "baidu"),
        default="auto",
    )

    compare_parser = subparsers.add_parser("compare-areas")
    compare_parser.add_argument("--areas", nargs="+", required=True)
    compare_parser.add_argument("--anchors", nargs="+", required=True)
    compare_parser.add_argument(
        "--mode",
        choices=("walking", "driving", "transit"),
        default="transit",
    )
    compare_parser.add_argument("--city")
    compare_parser.add_argument(
        "--provider",
        choices=("auto", "amap", "baidu"),
        default="auto",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "geocode":
        result = run_with_fallback(args.provider, "geocode", args.query, args.city)
    elif args.command == "route":
        result = run_with_fallback(
            args.provider,
            "route",
            args.origin,
            args.destination,
            args.mode,
            args.city,
        )
    elif args.command == "compare-areas":
        result = compare_areas(
            args.areas,
            args.anchors,
            args.mode,
            args.city,
            args.provider,
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
