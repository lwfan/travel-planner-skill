"""Directory resolution tests use isolated temporary workspaces only."""

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "codex/travel-planner/scripts"))
import output_paths as paths


def mark(directory, kind, trip_name=None):
    directory.mkdir(parents=True, exist_ok=True)
    data = {"kind": kind}
    if trip_name is not None:
        data["trip_name"] = trip_name
    (directory / paths.MARKER_NAME).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class OutputPathsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        # Bound ancestor checks inside the test workspace without user metadata reads.
        (self.root / ".git").mkdir()

    def test_general_resolution_does_not_create_anything(self):
        result = paths.resolve_trip_directory(self.workspace, "2026-10-北京")
        self.assertEqual(Path(result["path"]), self.workspace / "旅行计划" / "2026-10-北京")
        self.assertEqual(result["workspace_type"], "general")
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_travel_substring_does_not_classify_software_repository(self):
        software = self.workspace / "travel-planner-skill"
        software.mkdir()
        result = paths.resolve_trip_directory(software, "北京")
        self.assertEqual(Path(result["path"]), software / "旅行计划" / "北京")

    def test_explicit_collection_names_and_ancestor_avoid_nested_collections(self):
        for name in ("旅行计划", "旅游", "travel", "Trips", "travel-plans", "itineraries"):
            with self.subTest(name=name):
                collection = self.workspace / name
                child = collection / "素材"
                child.mkdir(parents=True)
                result = paths.resolve_trip_directory(child, "北京")
                self.assertEqual(Path(result["path"]), collection / "北京")

    def test_explicit_travel_handles_nonstandard_collection_name(self):
        result = paths.resolve_trip_directory(self.workspace, "北京", workspace_type="travel")
        self.assertEqual(Path(result["path"]), self.workspace / "北京")
        self.assertEqual(result["reason"], "explicit_travel_workspace")

    def test_collection_marker_identifies_nonstandard_name(self):
        mark(self.workspace, "collection")
        result = paths.resolve_trip_directory(self.workspace, "北京")
        self.assertEqual(Path(result["path"]), self.workspace / "北京")
        self.assertEqual(result["reason"], "collection_marker")

    def test_same_trip_and_nested_workspace_reuse_marker_even_without_name(self):
        collection = self.workspace / "旅行计划"
        trip = collection / "北京"
        mark(trip, "trip", "北京")
        child = trip / "素材" / "图片"
        child.mkdir(parents=True)
        for requested in ("北京", None):
            result = paths.resolve_trip_directory(child, requested)
            self.assertEqual(Path(result["path"]), trip)
            self.assertEqual(result["workspace_type"], "trip")
        self.assertEqual(paths.find_current_trip(child), {"path": str(trip), "trip_name": "北京"})

    def test_no_name_requires_a_current_trip_marker(self):
        self.assertIsNone(paths.find_current_trip(self.workspace))
        with self.assertRaises(paths.MissingTripNameError):
            paths.resolve_trip_directory(self.workspace)

    def test_other_trip_uses_known_collection_but_never_guesses_parent(self):
        collection = self.workspace / "旅行计划"
        mark(collection / "北京", "trip", "北京")
        result = paths.resolve_trip_directory(collection / "北京", "上海")
        self.assertEqual(Path(result["path"]), collection / "上海")
        mark(self.workspace / "单趟项目", "trip", "杭州")
        with self.assertRaises(FileExistsError):
            paths.resolve_trip_directory(self.workspace / "单趟项目", "上海")

    def test_collection_named_subfolder_does_not_override_enclosing_trip(self):
        collection = self.workspace / "旅行计划"
        trip = collection / "北京"
        mark(trip, "trip", "北京")
        child = trip / "trips"
        child.mkdir()
        result = paths.resolve_trip_directory(child, "上海")
        self.assertEqual(Path(result["path"]), collection / "上海")

    def test_date_place_name_or_plan_file_is_not_identity_evidence(self):
        trip = self.workspace / "2026-10-北京"
        trip.mkdir()
        (trip / "plan.json").write_text('{"title":"北京旅行", "days":[{"area":"故宫"}]}')
        result = paths.resolve_trip_directory(trip, "上海")
        self.assertEqual(Path(result["path"]), trip / "旅行计划" / "上海")

    def test_occupied_file_or_unmarked_nonempty_directory_is_not_adopted(self):
        collection = self.workspace / "旅行计划"
        collection.mkdir()
        (collection / "北京").write_text("user file")
        with self.assertRaises(FileExistsError):
            paths.ensure_trip_directory(self.workspace, "北京")
        (collection / "上海").mkdir()
        (collection / "上海" / "plan.json").write_text('{"title":"上海"}')
        with self.assertRaises(FileExistsError):
            paths.ensure_trip_directory(self.workspace, "上海")
        self.assertEqual((collection / "北京").read_text(), "user file")

    def test_different_marker_is_not_overwritten(self):
        target = self.workspace / "旅行计划" / "北京"
        mark(target, "trip", "另一趟北京")
        before = (target / paths.MARKER_NAME).read_text()
        with self.assertRaises(FileExistsError):
            paths.ensure_trip_directory(self.workspace, "北京")
        self.assertEqual((target / paths.MARKER_NAME).read_text(), before)

    def test_create_marks_collection_and_trip_and_repeated_call_reuses(self):
        result = paths.ensure_trip_directory(self.workspace, "北京")
        target = Path(result["path"])
        self.assertTrue(result["created"])
        self.assertEqual(json.loads((target.parent / paths.MARKER_NAME).read_text()), {"kind": "collection"})
        marker_text = (target / paths.MARKER_NAME).read_text()
        self.assertEqual(json.loads(marker_text), {"kind": "trip", "trip_name": "北京"})
        (target / "notes.md").write_text("keep me")
        again = paths.ensure_trip_directory(self.workspace, "北京")
        self.assertEqual(again["path"], result["path"])
        self.assertFalse(again["created"])
        self.assertEqual((target / "notes.md").read_text(), "keep me")
        self.assertEqual((target / paths.MARKER_NAME).read_text(), marker_text)

    def test_empty_existing_target_can_be_marked(self):
        target = self.workspace / "旅行计划" / "北京"
        target.mkdir(parents=True)
        result = paths.ensure_trip_directory(self.workspace, "北京")
        self.assertEqual(Path(result["path"]), target)
        self.assertTrue((target / paths.MARKER_NAME).is_file())

    def test_git_boundary_blocks_unrelated_parent_collection(self):
        collection = self.workspace / "trips"
        project = collection / "software"
        child = project / "src"
        child.mkdir(parents=True)
        (project / ".git").write_text("gitdir: /unused")
        result = paths.resolve_trip_directory(child, "北京")
        self.assertEqual(Path(result["path"]), child / "旅行计划" / "北京")

    def test_ancestor_inspection_is_bounded(self):
        collection = self.workspace / "trips"
        collection.mkdir()
        child = collection
        for index in range(paths.MAX_ANCESTORS):
            child = child / f"level-{index}"
            child.mkdir()
        result = paths.resolve_trip_directory(child, "北京")
        self.assertEqual(Path(result["path"]), child / "旅行计划" / "北京")

    def test_explicit_travel_marker_or_name_survives_its_own_git_boundary(self):
        for name, marker in (("trips", False), ("出游项目", True)):
            directory = self.workspace / name
            directory.mkdir()
            (directory / ".git").mkdir()
            if marker:
                mark(directory, "collection")
            result = paths.resolve_trip_directory(directory, "北京")
            self.assertEqual(Path(result["path"]), directory / "北京")

    def test_collection_context_wins_over_general_override_to_avoid_nesting(self):
        directory = self.workspace / "旅行计划"
        directory.mkdir()
        result = paths.resolve_trip_directory(directory, "北京", workspace_type="general")
        self.assertEqual(Path(result["path"]), directory / "北京")

    def test_invalid_names_and_marker_do_not_create_or_overwrite(self):
        for name in ("", " ", ".", "..", "../北京", "北京/上海", "北京\\上海", ".git", "北京\x00"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                paths.ensure_trip_directory(self.workspace, name)
        marker = self.workspace / paths.MARKER_NAME
        marker.write_text("{broken")
        with self.assertRaises(ValueError):
            paths.resolve_trip_directory(self.workspace, "北京")
        with self.assertRaises(ValueError) as error:
            paths.resolve_trip_directory(self.workspace, None)
        self.assertNotIsInstance(error.exception, paths.MissingTripNameError)
        self.assertEqual(marker.read_text(), "{broken")

    def test_failed_marker_creation_rolls_back_only_new_empty_directories(self):
        original = paths._write_marker
        def fail_trip(directory, data, created_markers):
            if data["kind"] == "trip":
                raise OSError("simulated write failure")
            return original(directory, data, created_markers)
        with patch.object(paths, "_write_marker", side_effect=fail_trip), self.assertRaises(OSError):
            paths.ensure_trip_directory(self.workspace, "北京")
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_target_and_marker_symlinks_are_refused(self):
        destination = self.workspace / "outside"
        destination.mkdir()
        collection = self.workspace / "旅行计划"
        collection.mkdir()
        (collection / "北京").symlink_to(destination, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            paths.ensure_trip_directory(self.workspace, "北京")
        (self.workspace / paths.MARKER_NAME).symlink_to(destination / "missing.json")
        with self.assertRaises(ValueError):
            paths.resolve_trip_directory(self.workspace, "上海")

    def test_cli_default_only_returns_json(self):
        output = io.StringIO()
        argv = ["output_paths.py", "--workspace", str(self.workspace), "--trip-name", "北京"]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(output):
            result = paths.main()
        self.assertEqual(result, 0)
        self.assertEqual(Path(json.loads(output.getvalue())["path"]), self.workspace / "旅行计划" / "北京")
        self.assertEqual(list(self.workspace.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
