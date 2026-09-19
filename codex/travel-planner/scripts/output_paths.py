#!/usr/bin/env python3
"""Resolve travel output directories using explicit context, without moving files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unicodedata


MARKER_NAME = ".travel-planner.json"
DEFAULT_COLLECTION = "旅行计划"
COLLECTION_NAMES = {"旅行计划", "旅游", "旅行", "travel", "trips", "travel-plans", "itineraries"}
WORKSPACE_TYPES = ("auto", "general", "travel")
MAX_ANCESTORS = 6
MAX_MARKER_BYTES = 8192


class MissingTripNameError(ValueError):
    """No explicit trip name and no marked current trip are available."""


def safe_trip_name(trip_name: str) -> str:
    """Keep meaningful Unicode names, but require exactly one visible directory."""
    if not isinstance(trip_name, str):
        raise ValueError("trip_name must be text")
    name = unicodedata.normalize("NFC", trip_name.strip())
    if (not name or name.startswith(".") or "/" in name or "\\" in name
            or any(unicodedata.category(char).startswith("C") for char in name)):
        raise ValueError("trip_name must be a non-hidden single directory name without separators or control characters")
    if len(name.encode("utf-8")) > 240:
        raise ValueError("trip_name is too long for a directory name")
    return name


def _workspace(workspace: Path) -> Path:
    directory = Path(workspace).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise NotADirectoryError(f"Workspace is not a directory: {directory}")
    return directory


def _marker(directory: Path) -> dict | None:
    path = directory / MARKER_NAME
    if path.is_symlink():
        raise ValueError(f"Refusing a symlink marker: {path}")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_MARKER_BYTES:
        raise ValueError(f"Invalid travel marker: {path}")
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.loads(stream.read(MAX_MARKER_BYTES + 1))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f"Invalid travel marker: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Invalid travel marker: {path}")
    if data.get("kind") == "collection":
        return {"kind": "collection"}
    if data.get("kind") == "trip":
        try:
            name = safe_trip_name(data.get("trip_name"))
        except ValueError as exc:
            raise ValueError(f"Invalid trip name in travel marker: {path}") from exc
        return {"kind": "trip", "trip_name": name}
    raise ValueError(f"Unknown travel marker kind: {path}")


def _context(workspace: Path) -> tuple[tuple[Path, dict] | None, tuple[Path, str] | None]:
    """Inspect only fixed markers/names on at most six current/ancestor directories."""
    trip = None
    collection = None
    directory = workspace
    for _ in range(MAX_ANCESTORS):
        marker = _marker(directory)
        if marker and marker["kind"] == "trip" and trip is None:
            trip = (directory, marker)
            if collection and collection[0].is_relative_to(directory):
                # A folder named "trips" inside one marked trip is not its
                # enclosing collection. Continue looking above the trip itself.
                collection = None
        if collection is None:
            if marker and marker["kind"] == "collection":
                collection = (directory, "collection_marker")
            elif marker is None and directory.name.casefold() in COLLECTION_NAMES:
                collection = (directory, "collection_name")
        # Check the boundary itself first: a travel collection may be versioned.
        if (directory / ".git").exists() or directory == Path.home() or directory.parent == directory:
            break
        directory = directory.parent
    return trip, collection


def find_current_trip(workspace: Path) -> dict | None:
    """Return a current/ancestor trip marker; do not infer identity from filenames."""
    trip, _ = _context(_workspace(workspace))
    if trip is None:
        return None
    return {"path": str(trip[0]), "trip_name": trip[1]["trip_name"]}


def _check_collection(directory: Path) -> None:
    if directory.is_symlink():
        raise FileExistsError(f"Refusing a symlink output collection: {directory}")
    if directory.exists():
        if not directory.is_dir():
            raise FileExistsError(f"Output collection path is occupied by a file: {directory}")
        marker = _marker(directory)
        if marker is not None and marker["kind"] != "collection":
            raise FileExistsError(f"Output collection path belongs to a trip: {directory}")


def _check_target(directory: Path, trip_name: str) -> None:
    if directory.is_symlink():
        raise FileExistsError(f"Refusing a symlink trip directory: {directory}")
    if not directory.exists():
        return
    if not directory.is_dir():
        raise FileExistsError(f"Trip output path is occupied by a file: {directory}")
    marker = _marker(directory)
    if marker == {"kind": "trip", "trip_name": trip_name}:
        return
    if marker is not None:
        raise FileExistsError(f"Trip output directory has a different travel marker: {directory}")
    if next(directory.iterdir(), None) is not None:
        raise FileExistsError(f"Refusing to adopt a nonempty unmarked trip directory: {directory}")


def resolve_trip_directory(workspace: Path, trip_name: str | None = None, *, workspace_type: str = "auto") -> dict:
    """Resolve without creating anything; an omitted name requires a trip marker.

    Existing trip/collection context takes precedence to avoid nesting. Otherwise,
    ``travel`` treats the current workspace as a collection and ``general`` adds
    the default collection. No plan contents or unrelated directories are scanned.
    """
    if workspace_type not in WORKSPACE_TYPES:
        raise ValueError("workspace_type must be auto, general, or travel")
    workspace = _workspace(workspace)
    name = safe_trip_name(trip_name) if trip_name is not None else None
    trip, collection = _context(workspace)
    if trip and (name is None or name == trip[1]["trip_name"]):
        return {
            "path": str(trip[0]), "trip_name": trip[1]["trip_name"],
            "workspace": str(workspace), "workspace_type": "trip",
            "requested_workspace_type": workspace_type, "reason": "existing_trip_marker",
            "collection_path": str(collection[0]) if collection else None,
        }
    if name is None:
        raise MissingTripNameError("trip_name is required when there is no current trip marker")
    if trip and (collection is None or collection[0] == trip[0] or collection[0].is_relative_to(trip[0])):
        raise FileExistsError("Workspace belongs to another trip with no enclosing travel collection; choose a collection workspace")
    if collection is not None:
        base, reason = collection
        actual_type = "travel"
    elif workspace_type == "travel":
        base, reason, actual_type = workspace, "explicit_travel_workspace", "travel"
    else:
        base, reason, actual_type = workspace / DEFAULT_COLLECTION, "general_workspace", "general"
    _check_collection(base)
    target = base / name
    _check_target(target, name)
    return {
        "path": str(target), "trip_name": name, "workspace": str(workspace),
        "workspace_type": actual_type, "requested_workspace_type": workspace_type,
        "reason": reason, "collection_path": str(base),
    }


def _write_marker(directory: Path, data: dict, created_markers: list[Path]) -> None:
    existing = _marker(directory)
    if existing is not None:
        if existing != data:
            raise FileExistsError(f"Travel marker conflict: {directory / MARKER_NAME}")
        return
    path = directory / MARKER_NAME
    try:
        with path.open("x", encoding="utf-8") as stream:
            created_markers.append(path)
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError:
        if _marker(directory) != data:
            raise FileExistsError(f"Travel marker conflict: {path}")


def ensure_trip_directory(workspace: Path, trip_name: str | None = None, *, workspace_type: str = "auto") -> dict:
    """Create only the resolved collection/trip and minimal identity markers."""
    result = resolve_trip_directory(workspace, trip_name, workspace_type=workspace_type)
    target = Path(result["path"])
    if result["reason"] == "existing_trip_marker":
        return {**result, "created": False}
    collection = Path(result["collection_path"])
    created_directories: list[Path] = []
    created_markers: list[Path] = []
    try:
        for directory in (collection, target):
            if not directory.exists():
                directory.mkdir()
                created_directories.append(directory)
        # Recheck before claiming existing empty directories; never replace a marker.
        _check_collection(collection)
        _check_target(target, result["trip_name"])
        _write_marker(collection, {"kind": "collection"}, created_markers)
        _write_marker(target, {"kind": "trip", "trip_name": result["trip_name"]}, created_markers)
    except (OSError, ValueError):
        for marker in reversed(created_markers):
            marker.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            try:
                directory.rmdir()  # Never remove files or a directory populated by another writer.
            except OSError:
                pass
        raise
    return {**result, "created": bool(created_directories or created_markers)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--trip-name", help="Required unless already inside a marked trip")
    parser.add_argument("--workspace-type", choices=WORKSPACE_TYPES, default="auto")
    parser.add_argument("--create", action="store_true", help="Create directories and markers; otherwise only resolve")
    args = parser.parse_args()
    try:
        fn = ensure_trip_directory if args.create else resolve_trip_directory
        result = fn(args.workspace, args.trip_name, workspace_type=args.workspace_type)
    except (OSError, ValueError) as exc:
        json.dump({"status": "error", "error": str(exc)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 1
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
