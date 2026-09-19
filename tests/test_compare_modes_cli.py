"""Offline integration tests for the multi-mode command and provider dispatch."""

import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts"))
import map_tools


def route_result(provider, command, origin, destination, mode, city, **options):
    if mode == "bus":
        return {"status": "no_route", "mode": mode, "provider_used": provider,
                "error": {"code": "no_route", "message": "No bus candidate"}}
    values = {
        "subway": (30, 4, "subway", {"cost_cny": 5, "walking_distance_m": 400, "transfers": 1}),
        "taxi": (20, 4, "driving", {"tolls_cny": 2}),
        "walking": (60, 4, "walking", {}),
    }
    duration, distance, resolved, details = values[mode]
    return {"status": "ok", "mode": mode, "provider_used": provider,
            "resolved_mode": resolved, "duration_minutes": duration,
            "distance_km": distance, "details": details}


class CompareModesCommandTests(unittest.TestCase):
    def run_command(self, extra):
        argv = ["map_tools.py", "compare-modes", "--origin", "A", "--destination", "B", *extra]
        output = io.StringIO()
        with patch.object(sys, "argv", argv), patch.object(
            map_tools, "run_with_fallback", side_effect=route_result
        ) as dispatch, contextlib.redirect_stdout(output):
            exit_code = map_tools.main()
        return exit_code, json.loads(output.getvalue()), dispatch.call_args_list

    def test_defaults_keep_all_options_and_partial_failures(self):
        exit_code, result, calls = self.run_command(["--city", "北京"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual([row["mode"] for row in result["options"]], ["subway", "taxi", "walking", "bus"])
        self.assertEqual(result["options"][-1]["status"], "no_route")
        self.assertIsNone(result["options"][1]["metrics"]["fare_cny"])
        self.assertEqual(result["recommendation"]["mode"], "taxi")
        self.assertEqual(result["recommendation"]["kind"], "suggestion")
        for call in calls:
            self.assertEqual(call.args[2:4], ("A", "B"))
            if call.args[4] in ("subway", "bus"):
                self.assertEqual(call.kwargs["max_walk_km"], 0)
                self.assertEqual(call.kwargs["max_walk_minutes"], 0)

    def test_preference_and_walking_constraint_reach_comparison(self):
        exit_code, result, calls = self.run_command([
            "--modes", "subway", "taxi", "--preference", "cheapest",
            "--max-total-walk-km", "1.2", "--origin-city", "北京", "--destination-city", "天津",
        ])
        self.assertEqual(exit_code, 0)
        self.assertEqual(result["recommendation"]["mode"], "subway")
        self.assertEqual(len(result["options"]), 2)
        self.assertEqual(result["preference"], "cheapest")
        for call in calls:
            self.assertEqual(call.kwargs["origin_city"], "北京")
            self.assertEqual(call.kwargs["destination_city"], "天津")


if __name__ == "__main__":
    unittest.main()
