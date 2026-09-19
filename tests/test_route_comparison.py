"""Offline tests for transparent mode comparison and constrained suggestions."""

from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts"))
from map_common import MapError, error_result
from route_comparison import compare_modes


def success(mode, *, minutes=20, km=5, fare=None, walk=None, transfers=None):
    return {
        "status": "ok", "mode": mode, "resolved_mode": "driving" if mode == "taxi" else mode,
        "provider_used": "amap", "duration_minutes": minutes, "distance_km": km,
        "details": {"cost_cny": fare, "walking_distance_m": walk, "transfers": transfers},
    }


def compare(routes, modes=None, **options):
    if modes is None:
        modes = list(routes)
    return compare_modes("起点", "终点", modes, "北京", "auto",
                         lambda mode, **kwargs: routes[mode], **options)


class RouteComparisonTests(unittest.TestCase):
    def test_partial_failure_preserves_order_original_results_and_choice(self):
        subway = success("subway", minutes=30, fare=5, walk=600, transfers=1)
        taxi = success("taxi", minutes=15)
        failure = error_result(MapError("no_route", "No bus route"))
        result = compare({"subway": subway, "taxi": taxi, "bus": failure})
        self.assertEqual(result["status"], "partial")
        self.assertEqual([option["mode"] for option in result["options"]], ["subway", "taxi", "bus"])
        self.assertEqual(result["options"][0]["route"], subway)
        self.assertEqual(result["options"][2]["route"], failure)
        self.assertEqual(result["recommendation"]["mode"], "taxi")
        self.assertEqual(result["recommendation"]["kind"], "suggestion")
        self.assertIn("not complete door-to-door", result["recommendation"]["reason"])
        self.assertIn("waiting", " ".join(result["options"][1]["notes"]))

    def test_unknown_taxi_fare_and_tolls_are_not_zero(self):
        taxi = success("taxi", minutes=10)
        taxi["details"]["tolls_cny"] = 2
        taxi["details"]["cost_cny"] = 7  # A driving/taxi adapter cost is not a fare contract.
        result = compare({"taxi": taxi, "bus": success("bus", fare=3, walk=300, transfers=0)}, preference="cheapest")
        self.assertIsNone(result["options"][0]["metrics"]["fare_cny"])
        self.assertEqual(result["recommendation"]["mode"], "bus")
        self.assertEqual(result["ranking"], ["bus"])
        self.assertIn("known fares only", result["recommendation"]["reason"])
        self.assertIn("not an overall cheapest claim", result["ranking_basis"]["scope"])

    def test_pure_walking_has_known_fare_distance_and_transfers(self):
        result = compare({"walking": success("walking", km=1.2)})
        self.assertEqual(result["options"][0]["metrics"], {
            "duration_minutes": 20.0, "fare_cny": 0, "walking_distance_m": 1200.0, "transfers": 0,
        })
        self.assertTrue(any("one distinct mode" in note for note in result["notes"]))

    def test_public_transport_fallback_is_disabled_without_mutating_other_options(self):
        route_call = Mock(side_effect=lambda mode, **kwargs: success(mode))
        compare_modes("A", "B", ["subway", "bus", "transit", "walking", "taxi"], "北京", "auto", route_call,
                      origin_city="北京", max_walk_km=8, max_walk_minutes=120)
        for call in route_call.call_args_list:
            self.assertEqual(call.kwargs["origin_city"], "北京")
            if call.args[0] in {"subway", "bus", "transit"}:
                self.assertEqual((call.kwargs["max_walk_km"], call.kwargs["max_walk_minutes"]), (0, 0))
            else:
                self.assertEqual((call.kwargs["max_walk_km"], call.kwargs["max_walk_minutes"]), (8, 120))

    def test_adapter_walking_replacement_is_retained_but_not_recommended(self):
        route = success("subway")
        route["resolved_mode"] = "walking"
        result = compare({"subway": route})
        self.assertEqual(result["status"], "no_route")
        self.assertEqual(result["options"][0]["route"], route)
        self.assertIsNone(result["recommendation"])

    def test_total_walking_limit_applies_to_all_options_and_unknown_is_unverified(self):
        routes = {
            "subway": success("subway", minutes=20, walk=600),
            "taxi": success("taxi", minutes=5),
            "walking": success("walking", minutes=10, km=1.2),
            "bus": success("bus", minutes=30, walk=400),
        }
        result = compare(routes, max_total_walk_km=0.5)
        eligibility = {option["mode"]: option["eligibility"]["status"] for option in result["options"]}
        self.assertEqual(eligibility, {"subway": "excluded", "taxi": "needs_verification", "walking": "excluded", "bus": "eligible"})
        self.assertEqual(result["recommendation"]["mode"], "bus")
        self.assertEqual(len(result["options"]), 4)

    def test_zero_total_walking_limit_is_a_constraint_not_no_constraint(self):
        result = compare({"bus": success("bus", walk=0), "walking": success("walking", km=0.01)}, max_total_walk_km=0)
        self.assertEqual(result["ranking"], ["bus"])

    def test_all_unknown_walking_prevents_recommendation_when_limit_is_set(self):
        result = compare({"taxi": success("taxi"), "bus": success("bus")}, max_total_walk_km=1)
        self.assertIsNone(result["recommendation"])
        self.assertEqual(result["ranking"], [])
        self.assertTrue(all(option["eligibility"]["status"] == "needs_verification" for option in result["options"]))
        self.assertIn("verified compliance", result["recommendation_reason"])

    def test_deduplication_keeps_first_requested_order_and_calls_once(self):
        route_call = Mock(side_effect=lambda mode, **kwargs: success(mode))
        result = compare_modes("A", "B", ["bus", "walking", "bus", "taxi", "walking"], None, "baidu", route_call)
        self.assertEqual(result["modes"], ["bus", "walking", "taxi"])
        self.assertEqual([call.args[0] for call in route_call.call_args_list], result["modes"])
        self.assertEqual(result["provider"], "baidu")

    def test_all_unknown_fares_gives_no_suggestion(self):
        result = compare({"taxi": success("taxi"), "subway": success("subway")}, preference="cheapest")
        self.assertIsNone(result["recommendation"])
        self.assertIn("unknown fare_cny", result["recommendation_reason"])

    def test_known_zero_fare_is_eligible(self):
        result = compare({"bus": success("bus", fare=0), "subway": success("subway", fare=5)}, preference="cheapest")
        self.assertEqual(result["recommendation"]["mode"], "bus")
        self.assertEqual(result["recommendation"]["value"], 0)

    def test_baidu_price_and_unknown_transfers_are_preserved(self):
        route = success("transit")
        route["provider_used"] = "baidu"
        route["details"] = {"price_cny": "6", "steps": 2}
        result = compare({"transit": route}, preference="fewest-transfers")
        self.assertEqual(result["options"][0]["metrics"]["fare_cny"], 6)
        self.assertIsNone(result["options"][0]["metrics"]["transfers"])
        self.assertIsNone(result["recommendation"])

    def test_preference_uses_only_stated_metric_and_keeps_tied_choices(self):
        routes = {"bus": success("bus", minutes=20, walk=400, transfers=1),
                  "subway": success("subway", minutes=10, walk=800, transfers=1)}
        walking = compare(routes, preference="least-walking")
        self.assertEqual(walking["recommendation"]["mode"], "bus")
        transfers = compare(routes, preference="fewest-transfers")
        self.assertEqual(transfers["recommendation"]["tied_modes"], ["bus", "subway"])
        self.assertEqual(transfers["options"][1]["mode"], "subway")
        self.assertFalse(transfers["ranking_basis"]["weighted_score"])

    def test_all_failures_keep_error_semantics(self):
        for codes, expected in ((["api_error", "no_route"], "error"), (["unsupported", "unsupported"], "unsupported"), (["no_route", "no_route"], "no_route")):
            with self.subTest(codes=codes):
                routes = {mode: error_result(MapError(code, code)) for mode, code in zip(("bus", "subway"), codes)}
                result = compare(routes)
                self.assertEqual(result["status"], expected)
                self.assertIsNone(result["recommendation"])
                self.assertEqual(len(result["options"]), 2)

    def test_expected_exception_only_affects_its_mode(self):
        def route_call(mode, **options):
            if mode == "bus":
                raise MapError("network_error", "offline")
            return success(mode)
        result = compare_modes("A", "B", ["bus", "walking"], None, "auto", route_call)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["recommendation"]["mode"], "walking")
        self.assertEqual(result["options"][0]["route"]["error"]["code"], "network_error")

    def test_programming_errors_are_not_silenced(self):
        def broken(mode, **options):
            raise KeyError("programming bug")
        with self.assertRaises(KeyError):
            compare_modes("A", "B", ["bus"], None, "auto", broken)

    def test_invalid_input_is_rejected_before_route_calls(self):
        for overrides in ({"modes": []}, {"modes": ["flight"]}, {"preference": "magic-score"}, {"max_total_walk_km": -1}, {"max_total_walk_km": float("nan")}):
            with self.subTest(overrides=overrides):
                route_call = Mock()
                args = dict(origin="A", destination="B", modes=["bus"], city=None, provider="auto", route_call=route_call)
                args.update(overrides)
                with self.assertRaises(MapError):
                    compare_modes(**args)
                route_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
