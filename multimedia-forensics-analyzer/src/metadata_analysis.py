"""Metadata analysis for images and videos.

Pipeline (see plan/metadata_analysis_plan.md):
    1. Identify the file type          <- implemented
    2. Extract the metadata (ExifTool) <- implemented
    3. Normalise into a common format
    4. Run consistency checks
    5. Record findings
    6. Calculate a suspicion score
    7. Provide output for the app and evaluation
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolException

EXIFTOOL_ARGS = ["-G1", "-n", "-api", "QuickTimeUTC=1"]


class UnsupportedMediaError(ValueError):
    """The file is not an image or video that ExifTool can read."""


@dataclass
class RawMetadata:
    """Everything ExifTool reported about one file, before normalisation."""

    path: str
    media_type: str  # "image" or "video"
    mime_type: str
    tags: dict  # keys look like "Group:Tag", e.g. "ExifIFD:DateTimeOriginal"

# ExifTool process
def open_exiftool() -> ExifToolHelper:
    return ExifToolHelper(common_args=EXIFTOOL_ARGS)

def detect_media_type(tags: dict) -> str:
    """Return "image" or "video" based on the file's contents."""
    if "ExifTool:Error" in tags:
        raise UnsupportedMediaError(f"ExifTool could not read the file: {tags['ExifTool:Error']}")

    mime = str(tags.get("File:MIMEType", ""))
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    raise UnsupportedMediaError(f"Not an image or video (detected type: {mime or 'unknown'})")

def extract_metadata(path: str | os.PathLike, et: ExifToolHelper | None = None) -> RawMetadata:
    """Read every metadata tag from one image or video.

    Pass an already-open ExifTool process as `et` when analysing many files;
    otherwise a temporary one is started for this file.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {path}")

    if et is None:
        with open_exiftool() as temp_et:
            return extract_metadata(path, temp_et)

    try:
        tags = et.get_metadata(str(path))[0]
    except ExifToolException as exc:
        raise UnsupportedMediaError(f"ExifTool failed to read {path}: {exc}") from exc

    media_type = detect_media_type(tags)
    return RawMetadata(
        path=str(path),
        media_type=media_type,
        mime_type=tags.get("File:MIMEType", ""),
        tags=tags,
    )


def extract_metadata_batch(
    paths: Iterable[str | os.PathLike],
) -> tuple[list[RawMetadata], dict[str, str]]:
    """Extract metadata from many files using a single ExifTool process.

    Returns (results, failures). One unreadable file does not stop the batch;
    its error message is recorded in `failures` under its path.
    """
    results: list[RawMetadata] = []
    failures: dict[str, str] = {}
    with open_exiftool() as et:
        for path in paths:
            try:
                results.append(extract_metadata(path, et))
            except (FileNotFoundError, UnsupportedMediaError) as exc:
                failures[str(path)] = str(exc)
    return results, failures


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sys.exit("Usage: python metadata_analysis.py <file> [<file> ...]")

    found, failed = extract_metadata_batch(sys.argv[1:])
    for raw in found:
        print(f"{raw.path}: {raw.media_type} ({raw.mime_type}), {len(raw.tags)} tags")
    for path, error in failed.items():
        print(f"{path}: FAILED - {error}")
