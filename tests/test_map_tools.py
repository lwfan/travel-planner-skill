"""Offline regressions: no real API requests and no local credential reads."""

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts"))
import amap_tools as amap
import baidu_tools as baidu
import map_tools
from map_common import MapError, call_safely


def geocode(query, city):
    return {"query": query, "city": city or "北京市", "citycode": "010",
            "location": {"lng": 116.4, "lat": 39.9}}


def path(distance=1000, duration=900):
    return {"distance": str(distance), "duration": str(duration), "steps": []}


def transit(*types):
    result = path(8000, 1800)
    result["walking_distance"] = "300"
    result["cost"] = "5"
    result["segments"] = [{"bus": {"buslines": [{
        "type": line_type, "name": f"line-{index}",
        "departure_stop": {"name": "上车站"}, "arrival_stop": {"name": "下车站"},
    }]}} for index, line_type in enumerate(types)]
    return result


class MapToolsTests(unittest.TestCase):
    def setUp(self):
        for target in ("urllib.request.urlopen", "amap_tools.load_api_key", "baidu_tools.load_config"):
            guard = patch(target, side_effect=AssertionError("Offline tests must not access network or credentials"))
            guard.start()
            self.addCleanup(guard.stop)
        for module in (amap, baidu):
            mock = patch.object(module, "geocode", side_effect=geocode)
            mock.start()
            self.addCleanup(mock.stop)

    def test_transit_passes_city_and_cityd(self):
        with patch.object(amap, "fetch_json", return_value={"route": {"transits": [transit("地铁线路")]}}) as fetch:
            amap.route("A", "B", "transit", "北京")
        params = fetch.call_args.args[1]
        self.assertEqual((params["city"], params["cityd"]), ("北京", "北京"))

    def test_cross_city_hints_and_inferred_citycodes(self):
        payload = {"route": {"transits": [transit("地铁线路")]}}
        with patch.object(amap, "fetch_json", return_value=payload) as fetch:
            amap.route("A", "B", "transit", None, origin_city="北京", destination_city="天津")
            params = fetch.call_args.args[1]
            self.assertEqual((params["city"], params["cityd"]), ("北京", "天津"))
            self.assertEqual(amap.geocode.call_args_list[-2].args, ("A", "北京"))
            self.assertEqual(amap.geocode.call_args_list[-1].args, ("B", "天津"))
            amap.route("A", "B", "transit", None)
            self.assertEqual(fetch.call_args.args[1]["city"], "010")

    def test_empty_routes_are_structured_no_route(self):
        for module, payload in ((amap, {"route": {"paths": []}}), (baidu, {"result": {"routes": []}})):
            for mode in ("walking", "driving", "taxi"):
                with self.subTest(provider=module.__name__, mode=mode), patch.object(module, "fetch_json", return_value=payload):
                    result = call_safely(module.route, "A", "B", mode, "北京")
                    self.assertEqual(result["status"], "no_route")
                    self.assertIsNone(result["duration_minutes"])

    def test_missing_route_list_is_invalid_not_empty(self):
        for module, payload in ((amap, {"route": {}}), (baidu, {"result": {}})):
            with self.subTest(provider=module.__name__), patch.object(module, "fetch_json", return_value=payload) as fetch:
                result = call_safely(module.route, "A", "B", "transit", "北京")
                self.assertEqual(result["error"]["code"], "invalid_response")
                self.assertEqual(fetch.call_count, 1)

    def test_api_errors_never_trigger_walking(self):
        for module in (amap, baidu):
            for code in ("api_error", "network_error"):
                with self.subTest(provider=module.__name__, code=code), patch.object(
                    module, "fetch_json", side_effect=MapError(code, "permission denied or unavailable")
                ) as fetch:
                    result = call_safely(module.route, "A", "B", "transit", "北京")
                    self.assertEqual(result["error"]["code"], code)
                    self.assertEqual(fetch.call_count, 1)

    def test_short_walk_fallback_is_bounded_and_explicit(self):
        for module, container, route_key in ((amap, "route", "paths"), (baidu, "result", "routes")):
            empty_key = "transits" if module is amap else "routes"
            for distance, duration, expected in ((1000, 900, "ok"), (20000, 18000, "no_route"), (1000, 1800, "no_route")):
                payloads = [{container: {empty_key: []}}, {container: {route_key: [path(distance, duration)]}}]
                with self.subTest(provider=module.__name__, distance=distance, duration=duration), patch.object(module, "fetch_json", side_effect=payloads):
                    result = call_safely(module.route, "A", "B", "transit", "北京")
                    self.assertEqual(result["status"], expected)
                    if expected == "ok":
                        self.assertEqual(result["resolved_mode"], "walking")
                        self.assertEqual(result["details"]["fallback_from"], "transit")

    def test_custom_and_disabled_walking_limits(self):
        empty = {"route": {"transits": []}}
        for options in ({"max_walk_km": 0}, {"max_walk_minutes": 0}):
            with patch.object(amap, "fetch_json", return_value=empty) as fetch:
                result = call_safely(amap.route, "A", "B", "transit", "北京", **options)
                self.assertEqual(result["status"], "no_route")
                self.assertEqual(fetch.call_count, 1)
        with patch.object(amap, "fetch_json", side_effect=[empty, {"route": {"paths": [path(2000, 1800)]}}]):
            result = amap.route("A", "B", "subway", "北京", max_walk_km=2.1, max_walk_minutes=31)
            self.assertEqual(result["resolved_mode"], "walking")
            self.assertEqual(result["details"]["fallback_from"], "subway")

    def test_subway_selects_verified_candidate_and_retains_mixed_modes(self):
        candidates = [transit("普通公交线路"), transit("地铁线路", "普通公交线路")]
        with patch.object(amap, "fetch_json", return_value={"route": {"transits": candidates}}):
            result = amap.route("A", "B", "subway", "北京")
        self.assertEqual(result["resolved_mode"], "transit")
        self.assertEqual(result["details"]["actual_modes"], ["bus", "subway"])
        self.assertEqual(result["details"]["legs"][0]["departure_stop"], "上车站")

    def test_bus_only_route_is_not_relabelled_subway(self):
        with patch.object(amap, "fetch_json", return_value={"route": {"transits": [transit("普通公交线路")]}}) as fetch:
            result = call_safely(amap.route, "A", "B", "subway", "北京")
        self.assertEqual(result["status"], "no_route")
        self.assertEqual(fetch.call_count, 1)

    def test_bus_strategy_and_railway_are_honest(self):
        candidate = transit("普通公交线路")
        candidate["segments"].append({"railway": {"name": "城际铁路", "type": "2013"}})
        with patch.object(amap, "fetch_json", return_value={"route": {"transits": [candidate]}}) as fetch:
            result = amap.route("A", "B", "bus", "北京")
        self.assertEqual(fetch.call_args.args[1]["strategy"], "5")
        self.assertEqual(result["resolved_mode"], "transit")
        self.assertIn("railway", result["details"]["actual_modes"])

    def test_taxi_connection_does_not_look_like_pure_subway(self):
        candidate = transit("地铁线路")
        candidate["segments"].append({"taxi": {"distance": "1000"}})
        with patch.object(amap, "fetch_json", return_value={"route": {"transits": [candidate]}}):
            result = amap.route("A", "B", "subway", "北京")
        self.assertEqual(result["resolved_mode"], "transit")
        self.assertIn("taxi", result["details"]["actual_modes"])

    def test_taxi_is_a_driving_estimate(self):
        with patch.object(amap, "fetch_json", return_value={"route": {"paths": [path()]}}) as fetch:
            result = amap.route("A", "B", "taxi", "北京")
        self.assertEqual(fetch.call_args.args[0], "/v3/direction/driving")
        self.assertEqual((result["mode"], result["resolved_mode"]), ("taxi", "driving"))
        self.assertIn("excludes waiting", result["details"]["estimate_note"])

    def test_baidu_unsupported_modes_do_not_fetch_or_geocode(self):
        for mode in ("subway", "bus"):
            result = map_tools.run_with_fallback("baidu", "route", "A", "B", mode, "北京")
            self.assertEqual(result["status"], "unsupported")
        baidu.geocode.assert_not_called()
        self.assertEqual(map_tools.provider_order("auto"), ["amap"])

    def test_partial_comparison_preserves_success_without_false_ranking(self):
        def fake_route(area, anchor, mode, city, **options):
            if area == "partial" and anchor == "B":
                raise MapError("no_route", "unreachable")
            return {"resolved_mode": "walking", "duration_minutes": 1 if area == "partial" else 20,
                    "distance_km": 1, "details": {}}
        with patch.object(amap, "route", side_effect=fake_route):
            result = map_tools.compare_areas(["partial", "complete"], ["A", "B"], "walking", "北京", "auto")
        self.assertEqual([row["area"] for row in result["ranked_areas"]], ["complete"])
        partial = result["incomplete_areas"][0]
        self.assertEqual(partial["coverage"], 0.5)
        self.assertIsNone(partial["average_duration_minutes"])
        self.assertEqual(partial["anchors"][0]["duration_minutes"], 1)
        self.assertEqual(partial["anchors"][1]["error"]["code"], "no_route")

    def test_cli_preserves_options_and_emits_no_route_json(self):
        argv = ["map_tools.py", "route", "--origin", "A", "--destination", "B", "--mode", "subway",
                "--origin-city", "北京", "--destination-city", "天津", "--max-walk-km", "0"]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(amap, "fetch_json", return_value={"route": {"transits": []}}) as fetch, contextlib.redirect_stdout(output):
            exit_code = map_tools.main()
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["status"], "no_route")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[1]["cityd"], "天津")


if __name__ == "__main__":
    unittest.main()
