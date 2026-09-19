"""Offline route metrics regressions; no network calls or credential reads."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts"))
import amap_tools as amap


def vehicle(line_type="地铁线路", name="selected line"):
    return {"bus": {"buslines": [{"type": line_type, "name": name}]}}


def walking(distance="100"):
    return {"walking": {"distance": distance}}


class TransitMetricsTests(unittest.TestCase):
    def setUp(self):
        for target in ("urllib.request.urlopen", "amap_tools.load_api_key"):
            guard = patch(target, side_effect=AssertionError("Offline tests must not use network or credentials"))
            guard.start()
            self.addCleanup(guard.stop)

    def test_two_subway_legs_mean_one_transfer(self):
        result = amap._transit_details({"segments": [vehicle(), vehicle(name="second line")]})
        self.assertEqual(result["boarding_count"], 2)
        self.assertEqual(result["transfers"], 1)
        self.assertEqual(result["actual_modes"], ["subway"])

    def test_walking_before_between_and_after_rides_does_not_count(self):
        result = amap._transit_details({"segments": [
            walking(), {**walking(), **vehicle()}, walking(), vehicle(), walking(),
        ]})
        self.assertEqual(result["segments"], 5)
        self.assertEqual(result["boarding_count"], 2)
        self.assertEqual(result["transfers"], 1)

    def test_busline_alternatives_count_only_the_selected_first_line(self):
        result = amap._transit_details({"segments": [{"bus": {"buslines": [
            {"type": "普通公交线路", "name": "selected bus"},
            {"type": "地铁线路", "name": "alternative subway"},
            {"type": "未知线路", "name": "unselected unknown"},
        ]}}]})
        self.assertEqual(result["boarding_count"], 1)
        self.assertEqual(result["transfers"], 0)
        self.assertEqual(result["actual_modes"], ["bus"])
        self.assertEqual(result["legs"][0]["name"], "selected bus")

    def test_unknown_selected_mode_leaves_metrics_unknown(self):
        for line_type in (None, "未知线路"):
            with self.subTest(line_type=line_type):
                result = amap._transit_details({"segments": [vehicle(), vehicle(line_type)]})
                self.assertIsNone(result["boarding_count"])
                self.assertIsNone(result["transfers"])
                self.assertIn("unknown", result["actual_modes"])

    def test_missing_uninterpreted_and_walk_only_legs_are_unknown(self):
        cases = [
            {},
            {"segments": []},
            {"segments": [{}]},
            {"segments": [walking()]},
            {"segments": [vehicle(), {}]},
            {"segments": [vehicle(), {"unsupported_connection": {"name": "connection"}}]},
            {"segments": [vehicle(), {**walking(), "bus": {"name": "missing buslines"}}]},
            {"segments": [vehicle(), {**walking(), "railway": ["uninterpreted train"]}]},
            {"segments": [vehicle(), {**walking(), "unsupported_connection": {"name": "connection"}}]},
        ]
        for transit in cases:
            with self.subTest(transit=transit):
                result = amap._transit_details(transit)
                self.assertIsNone(result["boarding_count"])
                self.assertIsNone(result["transfers"])

    def test_railway_bus_subway_and_taxi_connections_count_actual_legs(self):
        result = amap._transit_details({"segments": [
            {**walking(), **vehicle("普通公交线路"),
             "railway": {"name": "城际铁路", "type": "2013"}},
            {**vehicle(), "taxi": {"distance": "1000"}},
        ]})
        self.assertEqual(result["segments"], 2)
        self.assertEqual(result["boarding_count"], 4)
        self.assertEqual(result["transfers"], 3)
        self.assertEqual(result["actual_modes"], ["bus", "railway", "subway", "taxi", "walking"])

    def test_empty_optional_fields_and_entrance_metadata_are_not_connections(self):
        result = amap._transit_details({"segments": [
            {**vehicle(), "railway": [], "taxi": {}, "entrance": {"name": "A口"}, "exit": {"name": "B口"}},
            {**walking(), "bus": {"buslines": []}},
        ]})
        self.assertEqual(result["boarding_count"], 1)
        self.assertEqual(result["transfers"], 0)

    def test_optional_cost_and_walking_metrics_stay_uninvented(self):
        unknown = amap._transit_details({"segments": [vehicle()]})
        self.assertIsNone(unknown["cost_cny"])
        self.assertIsNone(unknown["walking_distance_m"])
        known = amap._transit_details({"segments": [vehicle()], "cost": "5", "walking_distance": "300"})
        self.assertEqual(known["cost_cny"], 5)
        self.assertEqual(known["walking_distance_m"], 300)


if __name__ == "__main__":
    unittest.main()
