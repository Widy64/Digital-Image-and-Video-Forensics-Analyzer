"""Tests for Steps 1-3 of the metadata analysis (src/metadata/metadata_extraction.py).

Unit tests use hand-written tag dictionaries and need nothing installed.
Integration tests create real files and run ExifTool; they are skipped when
ExifTool (or OpenCV, for the video tests) is not available.

Run from the multimedia-forensics-analyzer folder:  python -m pytest
"""

import shutil
from datetime import datetime, timedelta, timezone

import pytest

from src.metadata.metadata_extraction import (
    RawMetadata,
    UnsupportedMediaError,
    _collect_software,
    _find,
    _float,
    _int,
    _parse_date,
    _parse_offset,
    _text,
    _track,
    detect_media_type,
    extract_metadata,
    extract_metadata_batch,
    normalize,
)

requires_exiftool = pytest.mark.skipif(
    shutil.which("exiftool") is None, reason="ExifTool is not installed or not on PATH"
)


# ---------------------------------------------------------------------------
# Step 1: identify the file type
# ---------------------------------------------------------------------------

class TestDetectMediaType:
    @pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/heic"])
    def test_images(self, mime):
        assert detect_media_type({"File:MIMEType": mime}) == "image"

    @pytest.mark.parametrize("mime", ["video/mp4", "video/quicktime", "video/x-msvideo"])
    def test_videos(self, mime):
        assert detect_media_type({"File:MIMEType": mime}) == "video"

    def test_other_file_type_is_rejected(self):
        with pytest.raises(UnsupportedMediaError, match="text/plain"):
            detect_media_type({"File:MIMEType": "text/plain"})

    def test_missing_mime_type_is_rejected(self):
        with pytest.raises(UnsupportedMediaError, match="unknown"):
            detect_media_type({})

    def test_exiftool_error_is_rejected(self):
        with pytest.raises(UnsupportedMediaError, match="Unknown file type"):
            detect_media_type({"ExifTool:Error": "Unknown file type", "File:MIMEType": "image/jpeg"})


# ---------------------------------------------------------------------------
# Step 2: extract the metadata (no ExifTool needed)
# ---------------------------------------------------------------------------

def test_missing_file_raises_before_starting_exiftool(tmp_path):
    with pytest.raises(FileNotFoundError):
        extract_metadata(tmp_path / "does_not_exist.jpg")


# ---------------------------------------------------------------------------
# Step 3 helpers: dates and time zones
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_date_without_time_zone_stays_naive(self):
        assert _parse_date("2024:05:01 10:00:00") == datetime(2024, 5, 1, 10, 0, 0)

    def test_utc_marker(self):
        assert _parse_date("2024:05:01 09:00:00Z") == datetime(2024, 5, 1, 9, tzinfo=timezone.utc)

    def test_offset_in_value(self):
        parsed = _parse_date("2024:05:01 10:00:00+01:00")
        assert parsed.utcoffset() == timedelta(hours=1)

    def test_separate_offset_tag_is_applied(self):
        parsed = _parse_date("2024:05:01 10:00:00", "-05:00")
        assert parsed.utcoffset() == timedelta(hours=-5)

    def test_offset_in_value_wins_over_separate_tag(self):
        parsed = _parse_date("2024:05:01 10:00:00Z", "+03:00")
        assert parsed.utcoffset() == timedelta(0)

    def test_subseconds(self):
        assert _parse_date("2024:05:01 10:00:00.25").microsecond == 250_000

    def test_same_moment_in_different_zones_compares_equal(self):
        assert _parse_date("2024:05:01 10:00:00+01:00") == _parse_date("2024:05:01 09:00:00Z")

    @pytest.mark.parametrize("value", [
        "0000:00:00 00:00:00",    # placeholder written by many encoders
        "2024:13:45 10:00:00",    # impossible month/day
        "not a date",
        "",
        None,
        1714557600,
    ])
    def test_invalid_values_return_none(self, value):
        assert _parse_date(value) is None

    def test_invalid_separate_offset_is_ignored(self):
        assert _parse_date("2024:05:01 10:00:00", "garbage").tzinfo is None


class TestParseOffset:
    @pytest.mark.parametrize("text, expected", [
        ("+01:00", timedelta(hours=1)),
        ("-05:30", -timedelta(hours=5, minutes=30)),
        ("+0200", timedelta(hours=2)),
        ("Z", timedelta(0)),
    ])
    def test_valid(self, text, expected):
        assert _parse_offset(text).utcoffset(None) == expected

    @pytest.mark.parametrize("text", ["", "UTC+1", "1:00", None])
    def test_invalid(self, text):
        assert _parse_offset(text) is None


# ---------------------------------------------------------------------------
# Step 3 helpers: tag lookup and value conversion
# ---------------------------------------------------------------------------

class TestFind:
    tags = {
        "IFD0:Make": "Canon",
        "Keys:Make": "Apple",
        "IFD0:Software": "",
        "XMP-xmp:CreatorTool": "Adobe Photoshop",
    }

    def test_exact_group_name(self):
        assert _find(self.tags, "Keys:Make") == "Apple"

    def test_bare_name_matches_any_group(self):
        assert _find(self.tags, "CreatorTool") == "Adobe Photoshop"

    def test_first_name_listed_wins(self):
        assert _find(self.tags, "IFD0:Make", "Keys:Make") == "Canon"

    def test_empty_values_are_skipped(self):
        assert _find(self.tags, "IFD0:Software", "CreatorTool") == "Adobe Photoshop"

    def test_missing_returns_none(self):
        assert _find(self.tags, "Model", "IFD0:Model") is None


def test_track_selects_video_and_audio_tracks():
    tags = {
        "Track1:HandlerType": "vide", "Track1:TrackDuration": 2.0,
        "Track2:HandlerType": "soun", "Track2:TrackDuration": 3.0,
        "QuickTime:Duration": 3.0,
    }
    assert _track(tags, "vide") == {"HandlerType": "vide", "TrackDuration": 2.0}
    assert _track(tags, "soun")["TrackDuration"] == 3.0
    assert _track(tags, "subt") == {}


def test_collect_software_dedupes_and_flattens_lists():
    tags = {
        "IFD0:Software": "Adobe Photoshop 25.0",
        "XMP-xmpMM:HistorySoftwareAgent": ["Adobe Photoshop 25.0", "Adobe Lightroom"],
        "ItemList:Encoder": "Lavf61.7.100",
        "IFD0:Make": "Canon",                  # not a software tag
    }
    assert _collect_software(tags) == ["Adobe Photoshop 25.0", "Adobe Lightroom", "Lavf61.7.100"]


@pytest.mark.parametrize("value, text, number, integer", [
    ("  Canon ", "Canon", None, None),
    ("", None, None, None),
    (None, None, None, None),
    (30, "30", 30.0, 30),
    ("29.97", "29.97", 29.97, 29),
])
def test_value_conversions(value, text, number, integer):
    assert _text(value) == text
    assert _float(value) == number
    assert _int(value) == integer


# ---------------------------------------------------------------------------
# Step 3: normalise (hand-written tags, no ExifTool needed)
# ---------------------------------------------------------------------------

def _raw(media_type, tags):
    return RawMetadata(path="sample", media_type=media_type, mime_type="", tags=tags)


class TestNormalizeImage:
    tags = {
        "IFD0:Make": "Canon",
        "IFD0:Model": "EOS 80D",
        "IFD0:Software": "Adobe Photoshop 25.0",
        "IFD0:ModifyDate": "2024:06:10 15:30:00",
        "ExifIFD:DateTimeOriginal": "2024:05:01 10:00:00",
        "ExifIFD:OffsetTimeOriginal": "+01:00",
        "ExifIFD:OffsetTime": "+01:00",
        "ExifIFD:ExifImageWidth": 640,
        "ExifIFD:ExifImageHeight": 480,
        "File:ImageWidth": 600,
        "File:ImageHeight": 480,
        "GPS:GPSLatitude": 51.5,
        "GPS:GPSLongitude": -0.1,
        "Composite:GPSDateTime": "2024:05:01 09:00:00Z",
        "System:FileModifyDate": "2024:06:10 15:31:00+01:00",
    }

    def test_fields(self):
        meta = normalize(_raw("image", self.tags))
        assert (meta.make, meta.model) == ("Canon", "EOS 80D")
        assert meta.software == ["Adobe Photoshop 25.0"]
        assert meta.created == datetime(2024, 5, 1, 10, tzinfo=timezone(timedelta(hours=1)))
        assert meta.modified == datetime(2024, 6, 10, 15, 30, tzinfo=timezone(timedelta(hours=1)))
        assert meta.file_modified is not None
        assert (meta.declared_width, meta.declared_height) == (640, 480)
        assert (meta.actual_width, meta.actual_height) == (600, 480)
        assert (meta.gps_latitude, meta.gps_longitude) == (51.5, -0.1)
        assert meta.gps_time == meta.created          # same moment, different zones
        assert meta.tags is self.tags

    def test_video_fields_are_empty_for_images(self):
        meta = normalize(_raw("image", self.tags))
        assert meta.duration is meta.frame_rate is meta.frame_count is None
        assert meta.video_duration is meta.audio_duration is None

    def test_created_falls_back_to_xmp(self):
        meta = normalize(_raw("image", {"XMP-xmp:CreateDate": "2024:05:01 10:00:00"}))
        assert meta.created == datetime(2024, 5, 1, 10)

    def test_no_metadata(self):
        meta = normalize(_raw("image", {"File:ImageWidth": 80, "File:ImageHeight": 50}))
        assert meta.make is meta.model is meta.created is meta.modified is None
        assert meta.software == []
        assert (meta.declared_width, meta.actual_width) == (None, 80)


class TestNormalizeVideo:
    tags = {
        "Keys:Make": "Apple",
        "Keys:Model": "iPhone 15",
        "Keys:CreationDate": "2024:05:01 10:00:00+01:00",
        "QuickTime:CreateDate": "2024:05:01 09:00:02Z",
        "QuickTime:ModifyDate": "2024:05:01 09:00:02Z",
        "QuickTime:Duration": 3.0,
        "ItemList:Encoder": "Lavf63.1.102",
        "Track1:HandlerType": "vide",
        "Track1:TrackDuration": 2.0,
        "Track1:ImageWidth": 1920,
        "Track1:ImageHeight": 1080,
        "Track1:SourceImageWidth": 1920,
        "Track1:SourceImageHeight": 1080,
        "Track1:VideoFrameRate": 30,
        "Track2:HandlerType": "soun",
        "Track2:TrackDuration": 3.0,
    }

    def test_fields(self):
        meta = normalize(_raw("video", self.tags))
        assert (meta.make, meta.model) == ("Apple", "iPhone 15")
        assert meta.software == ["Lavf63.1.102"]
        assert meta.created.utcoffset() == timedelta(hours=1)   # capture start (Keys) preferred
        assert meta.modified == datetime(2024, 5, 1, 9, 0, 2, tzinfo=timezone.utc)
        assert (meta.declared_width, meta.declared_height) == (1920, 1080)
        assert (meta.actual_width, meta.actual_height) == (1920, 1080)
        assert meta.duration == 3.0
        assert (meta.video_duration, meta.audio_duration) == (2.0, 3.0)
        assert meta.frame_rate == 30.0
        assert meta.frame_count is None               # MP4 doesn't store one

    def test_created_falls_back_to_container_date(self):
        tags = {k: v for k, v in self.tags.items() if k != "Keys:CreationDate"}
        assert normalize(_raw("video", tags)).created == datetime(2024, 5, 1, 9, 0, 2, tzinfo=timezone.utc)

    def test_placeholder_dates_become_none(self):
        meta = normalize(_raw("video", {
            "QuickTime:CreateDate": "0000:00:00 00:00:00",
            "QuickTime:ModifyDate": "0000:00:00 00:00:00",
        }))
        assert meta.created is None and meta.modified is None

    def test_video_without_audio(self):
        tags = {k: v for k, v in self.tags.items() if not k.startswith("Track2:")}
        assert normalize(_raw("video", tags)).audio_duration is None

    def test_frame_count_from_container(self):
        assert normalize(_raw("video", {"RIFF:FrameCount": 300})).frame_count == 300


# ---------------------------------------------------------------------------
# Integration: real files through ExifTool
# ---------------------------------------------------------------------------

@pytest.fixture
def camera_photo(tmp_path):
    """A JPEG tagged as coming from a camera, with a time-zone offset and GPS."""
    Image = pytest.importorskip("PIL.Image")
    from exiftool import ExifToolHelper

    path = tmp_path / "photo.jpg"
    Image.new("RGB", (640, 480), (120, 60, 30)).save(path, quality=90)
    with ExifToolHelper() as et:
        et.execute(
            "-overwrite_original",
            "-Make=Canon", "-Model=EOS 80D",
            "-DateTimeOriginal=2024:05:01 10:00:00", "-OffsetTimeOriginal=+01:00",
            "-ExifImageWidth=640", "-ExifImageHeight=480",
            "-GPSLatitude=51.5", "-GPSLatitudeRef=N",
            "-GPSDateStamp=2024:05:01", "-GPSTimeStamp=09:00:00",
            str(path),
        )
    return path


@pytest.fixture
def short_video(tmp_path):
    """A 1-second, 30 fps, 160x120 MP4 written by OpenCV (no capture dates)."""
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    path = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 120))
    for i in range(30):
        writer.write(np.full((120, 160, 3), i * 8, np.uint8))
    writer.release()
    return path


@requires_exiftool
class TestWithExifTool:
    def test_photo_is_detected_and_keeps_group_names(self, camera_photo):
        raw = extract_metadata(camera_photo)
        assert raw.media_type == "image"
        assert raw.mime_type == "image/jpeg"
        assert raw.tags["ExifIFD:DateTimeOriginal"] == "2024:05:01 10:00:00"
        assert raw.tags["GPS:GPSLatitude"] == 51.5            # plain number, not "51 deg 30' 0.00\" N"

    def test_photo_normalizes(self, camera_photo):
        meta = normalize(extract_metadata(camera_photo))
        assert (meta.make, meta.model) == ("Canon", "EOS 80D")
        assert meta.created == datetime(2024, 5, 1, 10, tzinfo=timezone(timedelta(hours=1)))
        assert meta.gps_time == meta.created
        assert (meta.actual_width, meta.actual_height) == (640, 480)

    def test_video_is_detected_and_normalizes(self, short_video):
        meta = normalize(extract_metadata(short_video))
        assert meta.media_type == "video"
        assert meta.duration == pytest.approx(1.0, abs=0.05)
        assert meta.frame_rate == pytest.approx(30.0)
        assert (meta.declared_width, meta.declared_height) == (160, 120)
        assert meta.created is None                           # OpenCV writes placeholder dates
        assert any(s.startswith("Lavf") for s in meta.software)

    def test_type_comes_from_contents_not_extension(self, short_video):
        disguised = short_video.with_name("holiday.jpg")
        short_video.rename(disguised)
        assert extract_metadata(disguised).media_type == "video"

    def test_text_file_is_rejected(self, tmp_path):
        notes = tmp_path / "notes.txt"
        notes.write_text("not media")
        with pytest.raises(UnsupportedMediaError):
            extract_metadata(notes)

    def test_batch_keeps_going_after_failures(self, camera_photo, tmp_path):
        notes = tmp_path / "notes.txt"
        notes.write_text("not media")
        missing = tmp_path / "missing.png"

        results, failures = extract_metadata_batch([camera_photo, notes, missing])

        assert [r.path for r in results] == [str(camera_photo)]
        assert set(failures) == {str(notes), str(missing)}
        assert "No such file" in failures[str(missing)]
