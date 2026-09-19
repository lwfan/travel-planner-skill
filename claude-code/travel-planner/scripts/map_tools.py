#!/usr/bin/env python3
"""Unified map tools; auto uses AMap and Baidu remains opt-in."""

from __future__ import annotations

import argparse
import json
import sys
import amap_tools
import baidu_tools
from map_common import MODES, MapError, call_safely, compare_routes, error_result, nonnegative, options_from_args, route_options
from route_comparison import PREFERENCES, compare_modes as compare_route_modes


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
    **options,
) -> dict:
    failures: list[dict] = []
    order = provider_order(preferred)
    for index, provider in enumerate(order):
        provider_fn = getattr(amap_tools if provider == "amap" else baidu_tools, call_name)
        # The provider validates configuration when it needs to fetch data. This also
        # allows unsupported modes to fail before reading credentials or making calls.
        result = call_safely(provider_fn, *args, **options)
        result["provider_used"] = provider
        if call_name == "route" and len(args) >= 3:
            result.setdefault("mode", args[2])
        if result["status"] == "ok":
            if preferred == "auto" and index > 0:
                result["fallback_used"] = True
            return result
        failures.append(result)
    return failures[-1] if failures else error_result(MapError("configuration_error", "No map provider available"))


def compare_areas(
    areas: list[str],
    anchors: list[str],
    mode: str,
    city: str | None,
    provider: str,
    **options,
) -> dict:
    result = compare_routes(areas, anchors, mode, city, lambda area, anchor:
                            run_with_fallback(provider, "route", area, anchor, mode, city, **options))
    result["provider_order"] = provider_order(provider)
    return result


def compare_modes(
    origin: str,
    destination: str,
    modes: list[str] | None = None,
    city: str | None = None,
    provider: str = "auto",
    *,
    preference: str = "fastest",
    max_total_walk_km: float | None = None,
    origin_city: str | None = None,
    destination_city: str | None = None,
) -> dict:
    return compare_route_modes(
        origin, destination,
        modes if modes is not None else ["subway", "taxi", "walking", "bus"],
        city, provider,
        lambda mode, **options: run_with_fallback(
            provider, "route", origin, destination, mode, city, **options
        ),
        preference=preference,
        max_total_walk_km=max_total_walk_km,
        origin_city=origin_city,
        destination_city=destination_city,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified map tools; auto uses AMap, Baidu is opt-in"
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
    route_options(route_parser)
    route_parser.add_argument(
        "--provider",
        choices=("auto", "amap", "baidu"),
        default="auto",
    )

    compare_parser = subparsers.add_parser("compare-areas")
    compare_parser.add_argument("--areas", nargs="+", required=True)
    compare_parser.add_argument("--anchors", nargs="+", required=True)
    route_options(compare_parser)
    compare_parser.add_argument(
        "--provider",
        choices=("auto", "amap", "baidu"),
        default="auto",
    )

    modes_parser = subparsers.add_parser(
        "compare-modes", help="Compare travel modes for the same origin and destination"
    )
    modes_parser.add_argument("--origin", required=True)
    modes_parser.add_argument("--destination", required=True)
    modes_parser.add_argument("--modes", nargs="+", choices=MODES,
                              default=["subway", "taxi", "walking", "bus"])
    modes_parser.add_argument("--city", help="Common city hint for both endpoints")
    modes_parser.add_argument("--origin-city", help="Overrides --city for origin")
    modes_parser.add_argument("--destination-city", help="Overrides --city for destination")
    modes_parser.add_argument("--provider", choices=("auto", "amap", "baidu"), default="auto")
    modes_parser.add_argument("--preference", choices=tuple(PREFERENCES),
                              default="fastest", help="Criterion for a suggestion; all options remain visible")
    modes_parser.add_argument("--max-total-walk-km", type=nonnegative,
                              help="Optional walking limit per route, including transit connections")
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
            **options_from_args(args),
        )
    elif args.command == "compare-areas":
        result = call_safely(compare_areas,
            args.areas,
            args.anchors,
            args.mode,
            args.city,
            args.provider,
            **options_from_args(args),
        )
    elif args.command == "compare-modes":
        result = call_safely(
            compare_modes, args.origin, args.destination, args.modes, args.city, args.provider,
            preference=args.preference, max_total_walk_km=args.max_total_walk_km,
            origin_city=args.origin_city, destination_city=args.destination_city,
        )
    else:
        raise SystemExit(f"Unknown command: {args.command}")

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
