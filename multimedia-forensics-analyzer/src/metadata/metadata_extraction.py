"""Metadata extraction: Steps 1-3 of the metadata analysis pipeline.

    1. Identify the file type
    2. Extract the metadata (ExifTool)
    3. Normalise into a common format

Turns a file on disk into NormalizedMetadata. Knows nothing about checks or scores
(see metadata_checks.py for Step 4 and metadata_analysis.py for Steps 5-7).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


# Step 3: normalise into a common format

# Tag names (in any group) that record which program wrote or edited the file.
SOFTWARE_TAGS = (
    "Software", "CreatorTool", "HistorySoftwareAgent", "ProcessingSoftware",
    "Encoder", "EncodingTool", "WritingApp", "MuxingApp",
)


@dataclass
class NormalizedMetadata:
    """The same set of fields for photos and videos, so checks can be shared.

    Dates keep their time zone when the file records one (aware datetime) and
    are left without one when it doesn't (naive datetime). Any field the file
    doesn't contain is None.
    """

    path: str
    media_type: str
    make: str | None
    model: str | None
    software: list[str]                 # every program name found, in priority order
    created: datetime | None            # capture time
    modified: datetime | None           # last-modified time recorded inside the file
    file_modified: datetime | None      # the computer's file-system modified time
    declared_width: int | None          # size the metadata claims
    declared_height: int | None
    actual_width: int | None            # size of the encoded image / video stream
    actual_height: int | None
    gps_latitude: float | None
    gps_longitude: float | None
    gps_time: datetime | None           # always UTC
    duration: float | None              # video only, seconds
    video_duration: float | None        # video only, length of the video track
    audio_duration: float | None        # video only, length of the audio track
    frame_rate: float | None            # video only, frames per second
    frame_count: int | None             # video only, when the container records it
    tags: dict                          # full original tag list


def normalize(raw: RawMetadata) -> NormalizedMetadata:
    """Translate ExifTool's format-specific tags into the shared fields."""
    tags = raw.tags

    if raw.media_type == "image":
        created = (
            _parse_date(tags.get("ExifIFD:DateTimeOriginal"), tags.get("ExifIFD:OffsetTimeOriginal"))
            or _parse_date(tags.get("ExifIFD:CreateDate"), tags.get("ExifIFD:OffsetTimeDigitized"))
            or _parse_date(_find(tags, "XMP-xmp:CreateDate", "XMP-photoshop:DateCreated",
                                 "DateTimeOriginal", "CreateDate"))
        )
        modified = (
            _parse_date(tags.get("IFD0:ModifyDate"), tags.get("ExifIFD:OffsetTime"))
            or _parse_date(_find(tags, "XMP-xmp:ModifyDate", "ModifyDate"))
        )
        declared = (_find(tags, "ExifIFD:ExifImageWidth"), _find(tags, "ExifIFD:ExifImageHeight"))
        actual = (_find(tags, "File:ImageWidth", "ImageWidth"), _find(tags, "File:ImageHeight", "ImageHeight"))
        video_track, audio_track = {}, {}
    else:
        created = _parse_date(_find(tags, "Keys:CreationDate", "QuickTime:CreateDate",
                                    "XMP-xmp:CreateDate", "DateTimeOriginal", "CreateDate"))
        modified = _parse_date(_find(tags, "QuickTime:ModifyDate", "XMP-xmp:ModifyDate", "ModifyDate"))
        video_track = _track(tags, "vide")
        audio_track = _track(tags, "soun")
        declared = (video_track.get("ImageWidth") or _find(tags, "ImageWidth"),
                    video_track.get("ImageHeight") or _find(tags, "ImageHeight"))
        actual = (video_track.get("SourceImageWidth"), video_track.get("SourceImageHeight"))

    return NormalizedMetadata(
        path=raw.path,
        media_type=raw.media_type,
        make=_text(_find(tags, "IFD0:Make", "Keys:Make", "UserData:Make", "Make")),
        model=_text(_find(tags, "IFD0:Model", "Keys:Model", "UserData:Model", "Model")),
        software=_collect_software(tags),
        created=created,
        modified=modified,
        file_modified=_parse_date(tags.get("System:FileModifyDate")),
        declared_width=_int(declared[0]),
        declared_height=_int(declared[1]),
        actual_width=_int(actual[0]),
        actual_height=_int(actual[1]),
        gps_latitude=_float(_find(tags, "GPS:GPSLatitude", "Composite:GPSLatitude", "GPSLatitude")),
        gps_longitude=_float(_find(tags, "GPS:GPSLongitude", "Composite:GPSLongitude", "GPSLongitude")),
        gps_time=_parse_date(tags.get("Composite:GPSDateTime")),
        duration=_float(_find(tags, "QuickTime:Duration", "Duration")) if raw.media_type == "video" else None,
        video_duration=_float(video_track.get("TrackDuration") or video_track.get("MediaDuration")),
        audio_duration=_float(audio_track.get("TrackDuration") or audio_track.get("MediaDuration")),
        frame_rate=_float(video_track.get("VideoFrameRate") or _find(tags, "VideoFrameRate", "FrameRate"))
        if raw.media_type == "video" else None,
        frame_count=_int(_find(tags, "FrameCount", "TotalFrameCount")) if raw.media_type == "video" else None,
        tags=tags,
    )


def _find(tags: dict, *names: str):
    """Return the first non-empty value among `names`.

    "Group:Tag" names must match exactly; a bare "Tag" name matches that tag in any group.
    """
    for name in names:
        if ":" in name:
            value = tags.get(name)
        else:
            value = next((v for k, v in tags.items()
                          if k.rpartition(":")[2] == name and v not in (None, "")), None)
        if value not in (None, ""):
            return value
    return None


def _track(tags: dict, handler: str) -> dict:
    """Tags of the first video ("vide") or audio ("soun") track, without the group prefix."""
    tracks: dict[str, dict] = {}
    for key, value in tags.items():
        group, _, name = key.partition(":")
        if group.startswith("Track"):
            tracks.setdefault(group, {})[name] = value
    return next((t for t in tracks.values() if t.get("HandlerType") == handler), {})


def _collect_software(tags: dict) -> list[str]:
    found: list[str] = []
    for key, value in tags.items():
        if key.rpartition(":")[2] in SOFTWARE_TAGS:
            for item in value if isinstance(value, list) else [value]:
                text = _text(item)
                if text and text not in found:
                    found.append(text)
    return found


_DATE_RE = re.compile(
    r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(\.\d+)?\s*(Z|[+-]\d{2}:?\d{2})?"
)


def _parse_date(value, offset=None) -> datetime | None:
    """Parse an ExifTool date such as "2024:05:01 10:00:00+01:00".

    `offset` is a separate time-zone tag (e.g. EXIF OffsetTimeOriginal) used when the
    date itself has none. Placeholder dates like "0000:00:00 00:00:00" return None.
    """
    if not isinstance(value, str):
        return None
    match = _DATE_RE.match(value.strip())
    if not match:
        return None
    year, month, day, hour, minute, second, fraction, zone = match.groups()
    try:
        parsed = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second),
                          round(float(fraction) * 1_000_000) if fraction else 0)
    except ValueError:
        return None
    tz = _parse_offset(zone or offset)
    return parsed.replace(tzinfo=tz) if tz else parsed


def _parse_offset(text) -> timezone | None:
    if not isinstance(text, str):
        return None
    if text.strip() == "Z":
        return timezone.utc
    match = re.fullmatch(r"([+-])(\d{2}):?(\d{2})", text.strip())
    if not match:
        return None
    sign = 1 if match[1] == "+" else -1
    return timezone(sign * timedelta(hours=int(match[2]), minutes=int(match[3])))


def _text(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None
