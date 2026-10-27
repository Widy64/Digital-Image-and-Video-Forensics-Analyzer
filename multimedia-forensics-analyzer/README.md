# Digital-Image-and-Video-Forensics-Analyzer

## Overview

A Python-based multimedia forensics system for analyzing digital images and videos to identify measurable technical indicators of editing or manipulation.

The project focuses on detecting potential signs of modification rather than determining whether media is inherently true or false. The system will analyze forensic features, highlight suspicious regions or video frames where possible, and evaluate detection performance using a controlled dataset.

## Objectives

The project aims to:

- Analyze media metadata for inconsistencies.
- Investigate JPEG compression artifacts and recompression indicators.
- Detect potential copied or duplicated image regions.
- Examine unusual edge and texture patterns.
- Identify duplicated or potentially removed video frames and suspicious temporal changes.
- Visually highlight suspicious regions or frames where feasible.
- Compare forensic techniques using quantitative evaluation metrics.
- Investigate which features are most effective for detecting different types of manipulation.

A combined confidence score may be explored as an optional extension.

## Planned Architecture

The repository is organized by forensic analysis category, with evaluation and application logic separated from the underlying detection methods.

```text
multimedia-forensics-analyzer/
├── app.py
├── requirements.txt
├── README.md
├── src/
│   ├── metadata_analysis.py
│   ├── compression_analysis.py
│   ├── image_analysis.py
│   ├── video_analysis.py
│   └── evaluation.py
├── tests/
│   └── test_analysis.py
├── data/
│   ├── originals/
│   ├── manipulated/
│   └── labels.csv
├── results/
│   ├── metrics.csv
│   └── figures/
└── notebooks/
    └── initial_experiments.ipynb
```

### Module Responsibilities

- **`app.py`**: Application entry point for submitting media, coordinating analysis, and presenting results.
- **`src/metadata_analysis.py`**: Extracts image and video metadata and checks for potentially suspicious inconsistencies.
- **`src/compression_analysis.py`**: Investigates JPEG compression artifacts, recompression, and related compression-based indicators.
- **`src/image_analysis.py`**: Implements image-specific analysis, including copied-region detection, feature matching, and edge or texture analysis.
- **`src/video_analysis.py`**: Handles video frame extraction, duplicated-frame detection, and temporal anomaly analysis.
- **`src/evaluation.py`**: Calculates evaluation metrics, compares techniques, and generates quantitative results.
- **`tests/test_analysis.py`**: Tests analysis functions, expected outputs, and relevant edge cases.
- **`data/`**: Stores original and manipulated media, together with labels describing the ground truth and manipulation types.
- **`results/`**: Stores evaluation metrics, tables, and generated figures.
- **`notebooks/initial_experiments.ipynb`**: Supports preliminary experiments and exploratory analysis before techniques are integrated into the main codebase.

The modules represent the intended final organization. Individual algorithms and their implementation details will be selected and refined during development.

## Dataset and Experimental Design

The evaluation will use a controlled dataset containing original media and intentionally manipulated versions.

The initial target dataset is:

- **Images**: 50 original images and 50 corresponding manipulated versions.
- **Videos**: 5 to 10 short original videos and corresponding modified versions containing inserted, duplicated, or removed frames.

The [NIST Media Forensics Challenge (MFC)](https://mfc.nist.gov/) resources and the [NIST Public Data Repository](https://data.nist.gov/pdr/lps/ark:/88434/mds2-2410) will be investigated as potential supplementary sources. Additional media may be collected or created for controlled experiments.

Each sample should be associated with ground-truth labels describing whether it is original or manipulated and, where applicable, the manipulation type and affected region or frames.

The dataset will be organized to support reproducible experiments and comparisons between detection methods.

## Evaluation

The system will be evaluated against the dataset's ground-truth labels using:

- **Precision**: The proportion of detected manipulations that are actual manipulations.
- **Recall**: The proportion of actual manipulations successfully detected.
- **Accuracy**: The proportion of correctly classified samples.
- **False-positive rate**: The proportion of original samples incorrectly flagged as manipulated.

Results will be compared across forensic techniques and manipulation types to investigate which indicators are most effective and which are more difficult to detect.

Where suitable ground-truth annotations are available, region-level or frame-level detection performance may also be evaluated.

## Technology and References

The project will use Python and relevant multimedia-processing and scientific-computing libraries. Candidate tools include:

- [ExifTool](https://exiftool.org/) and [PyExifTool](https://pypi.org/project/PyExifTool/): Image and video metadata extraction.
- [FFprobe](https://ffmpeg.org/ffprobe.html): Media metadata inspection.
- [OpenCV](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html): Image processing and video frame handling.
- [scikit-image](https://scikit-image.org/docs/stable/api/skimage.metrics.html): Image comparison and similarity metrics.
- [scikit-image ORB feature matching](https://scikit-image.org/docs/stable/auto_examples/features_detection/plot_orb.html): Feature-based image comparison.
- [NIST Media Forensics Challenge](https://mfc.nist.gov/): Potential forensic datasets.
- [NIST Public Data Repository](https://data.nist.gov/pdr/lps/ark:/88434/mds2-2410): Additional dataset resource.

The final dependency list will be maintained in `requirements.txt`.

## Setup

### 1. Install ExifTool (required for metadata analysis)

`src/metadata_analysis.py` uses [ExifTool](https://exiftool.org/) to read metadata from both images and videos. The Python package `PyExifTool` is only a wrapper, so the ExifTool program itself must also be installed and on your `PATH`.

**Windows**

1. Download the Windows 64-bit executable (`exiftool-<version>_64.zip`) from [exiftool.org](https://exiftool.org/).
2. Extract the zip to a permanent location outside the repository, for example `C:\exiftool-13.59_64`. The folder must contain both `exiftool.exe` and the `exiftool_files` folder.
3. Make sure the program is named exactly `exiftool.exe`. Windows can hide file extensions, so check that it hasn't become `exiftool.exe.exe` or `exiftool(-k).exe`.
4. Add the **folder** (for example `C:\exiftool-13.59_64`) to your `PATH`: search for *Edit the system environment variables* → **Environment Variables** → select **Path** → **Edit** → **New**. Add the folder path, not the path to `exiftool.exe`.
5. Close and reopen every terminal and VS Code window so they pick up the new `PATH`.

**macOS:** `brew install exiftool`

**Linux (Debian/Ubuntu):** `sudo apt install libimage-exiftool-perl`

**Check the installation** in a new terminal:

```bash
exiftool -ver
```

This should print a version number, such as `13.59`.

> Do not place ExifTool inside the repository folder; it would be committed to Git.

### 2. Install the Python dependencies

```bash
python -m pip install -U pyexiftool
```

### 3. Check that Python can reach ExifTool

```bash
python src/metadata_analysis.py path/to/photo.jpg path/to/video.mp4
```

Each file should be reported as `image` or `video` with a tag count. An error saying `exiftool.exe is not found` means ExifTool isn't on your `PATH`; recheck step 1.