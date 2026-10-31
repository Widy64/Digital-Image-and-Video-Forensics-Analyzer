"""Metadata analysis for images and videos: Steps 5-7 and the public entry point.

Pipeline (see plan/metadata_analysis_plan.md):
    1-3. Identify, extract and normalise   -> metadata_extraction.py
    4.   Run consistency checks             -> metadata_checks.py
    5.   Record findings                    -> this file (not yet implemented)
    6.   Calculate a suspicion score        -> this file (not yet implemented)
    7.   Provide output for the app and evaluation -> this file (not yet implemented)
"""

from __future__ import annotations

try:  # imported as part of the src package (app.py, tests)
    from .metadata.metadata_extraction import extract_metadata_batch, normalize
except ImportError:  # run directly: python src/metadata_analysis.py <file>
    from metadata.metadata_extraction import extract_metadata_batch, normalize


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sys.exit("Usage: python metadata_analysis.py <file> [<file> ...]")

    found, failed = extract_metadata_batch(sys.argv[1:])
    for raw in found:
        meta = normalize(raw)
        print(f"\n{meta.path}: {meta.media_type} ({raw.mime_type}), {len(raw.tags)} tags")
        for field, value in vars(meta).items():
            if field not in ("path", "media_type", "tags"):
                print(f"  {field:16} {value}")
    for path, error in failed.items():
        print(f"\n{path}: FAILED - {error}")
