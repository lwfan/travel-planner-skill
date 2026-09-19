"""Regression tests for visual-plan content and portable local image delivery."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote


SCRIPT = Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts/visual_plan.py"
SPEC = importlib.util.spec_from_file_location("visual_plan", SCRIPT)
visual_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(visual_plan)

TINY_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="red"/></svg>'


class VisualPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="visual-plan-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec_dir = self.root / "specs"
        self.spec_dir.mkdir()

    def run_cli(self, data, output: Path) -> subprocess.CompletedProcess:
        spec_path = self.spec_dir / "plan.json"
        spec_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(spec_path), "--output", str(output)],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def test_unpictured_anchor_keeps_place_activity_and_reason(self) -> None:
        rendered = visual_plan.build_html({"visual_anchors": [{
            "name": "雨林步道", "description": "轻松徒步", "note": "未找到可靠图源"
        }]})
        for value in ("雨林步道", "轻松徒步", "未找到可靠图源", "未配图"):
            self.assertIn(value, rendered)
        self.assertNotIn('<img src=""', rendered)

    def test_source_only_credits_survive_in_all_image_positions(self) -> None:
        def photo(position):
            return {"src": "https://example.com/photo.jpg", "source_url": f"https://example.com/{position}"}

        rendered = visual_plan.build_html({
            "hero_image": photo("hero-source"),
            "days": [{"area": "城区", "image": photo("day-source")}],
            "visual_anchors": [{"name": "景点", "image": photo("anchor-source")}],
        })
        for position in ("hero-source", "day-source", "anchor-source"):
            self.assertIn(f'href="https://example.com/{position}">图片来源</a>', rendered)

    def test_missing_image_does_not_invent_a_search_failure(self) -> None:
        rendered = visual_plan.build_html({"visual_anchors": [{"name": "景点"}]})
        self.assertIn("未配图", rendered)
        self.assertNotIn("未找到可靠图源", rendered)

    def test_valid_summaries_do_not_require_days(self) -> None:
        for data in (
            {"route": ["京都", "大阪"]},
            {"visual_anchors": [{"name": "公园"}]},
            {"budget": [{"label": "餐饮", "value": 300}]},
            {"checklist": ["预订车票"]},
            {"meta": [{"label": "天数", "value": "3 天"}]},
        ):
            with self.subTest(data=data):
                self.assertIn("<!doctype html>", visual_plan.build_html(data))

    def test_bad_types_and_blank_plans_report_field_paths(self) -> None:
        for data, path in (
            ({}, "$"),
            ({"title": "只有标题", "sources": ["官方页面"]}, "$"),
            ({"days": ["误填的文本"]}, "days[0]"),
            ({"days": [{"morning": ["A", "B"]}]}, "days[0].morning"),
            ({"visual_anchors": [None]}, "visual_anchors[0]"),
            ({"days": [{"day": "Day 1"}]}, "days[0]"),
            ({"route": [""]}, "route[0]"),
            ({"route": ["城区"], "hero_image": {"src": []}}, "hero_image.src"),
            ({"budget": [{"label": "餐饮", "value": {"cost": 300}}]}, "budget[0].value"),
        ):
            with self.subTest(data=data):
                with self.assertRaisesRegex(ValueError, re.escape(path)):
                    visual_plan.build_html(data)

    def test_cli_validation_failure_preserves_existing_html(self) -> None:
        output = self.root / "existing.html"
        output.write_text("previous complete page", encoding="utf-8")
        result = self.run_cli({"days": [{"morning": []}]}, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("days[0].morning", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(output.read_text(), "previous complete page")

    def test_cli_packages_local_assets_and_still_works_after_move(self) -> None:
        source_dir = self.spec_dir / "assets"
        source_dir.mkdir()
        source = source_dir / "a picture's name.svg"
        source.write_bytes(TINY_SVG)
        output = self.root / "exports" / "我的行程.html"
        data = {
            "hero_image": {"src": "assets/a picture's name.svg", "source_url": "https://example.com/source"},
            "days": [{"area": "城区", "image": str(source)}],
            "visual_anchors": [{"name": "景点", "image": source.as_uri()}],
        }
        result = self.run_cli(data, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://example.com/source", output.read_text())
        assets = list((output.parent / "我的行程-assets").iterdir())
        self.assertEqual(len(assets), 1, "Repeated images should reuse the same packaged file")
        self.assertEqual(assets[0].read_bytes(), TINY_SVG)
        shared = self.root / "shared"
        shutil.copytree(output.parent, shared)
        shutil.rmtree(source_dir)
        moved_html = (shared / output.name).read_text()
        sources = re.findall(r'<img src="([^"]+)"', moved_html)
        self.assertEqual(len(sources), 2)
        for src in sources:
            self.assertEqual((shared / unquote(src)).read_bytes(), TINY_SVG)
        self.assertNotIn(str(self.spec_dir), moved_html)
        # The hero uses the same packaged image through CSS.
        self.assertEqual(moved_html.count(assets[0].name), 3)

    def test_missing_local_asset_does_not_leave_partial_output(self) -> None:
        (self.spec_dir / "good.svg").write_bytes(TINY_SVG)
        output = self.root / "not-yet-created" / "plan.html"
        result = self.run_cli({
            "hero_image": "good.svg",
            "days": [{"area": "城区", "image": "missing.svg"}],
        }, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("days[0].image", result.stderr)
        self.assertFalse(output.parent.exists())

    def test_remote_images_are_left_untouched_without_asset_directory(self) -> None:
        output = self.root / "remote.html"
        remote_images = [
            "https://example.invalid/image.jpg",
            "//example.invalid/image.jpg",
            "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'/%3E",
        ]
        data = {"days": [{"area": "城区", "image": src} for src in remote_images]}
        before = copy.deepcopy(data)
        visual_plan.write_plan(data, self.spec_dir, output)
        self.assertEqual(data, before)
        self.assertFalse((self.root / "remote-assets").exists())
        for src in remote_images:
            self.assertIn(visual_plan.escape(src), output.read_text())

    def test_single_entry_forms_and_aliases_remain_supported(self) -> None:
        rendered = visual_plan.build_html({
            "route": "城区", "highlights": {"title": "公园", "note": "休息"},
            "days": {"day": 1, "area": "城区", "notes": "公交往返"},
        })
        self.assertIn("公园", rendered)
        self.assertIn("公交往返", rendered)


if __name__ == "__main__":
    unittest.main()
