"""Metadata consistency checks: Step 4 of the metadata analysis pipeline.

    4. Run consistency checks

Decides what looks inconsistent in NormalizedMetadata and produces Findings.
Imports from metadata_extraction.py only; metadata_analysis.py (Steps 5-7) imports from here.

Planned contents (see plan/metadata_analysis_plan.md):
    - Finding, the Check interface and the check registry
    - tunable settings: editing-software / re-encoder names, tolerances
    - shared checks, photo-only checks, video-only checks
    - content helpers: frame timestamps (OpenCV), embedded preview comparison (Pillow)
"""

from __future__ import annotations
