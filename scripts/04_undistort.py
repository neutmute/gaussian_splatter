"""
04_undistort.py — COLMAP image undistortion for Lichtfield Studio

Runs colmap image_undistorter to produce a dense/ folder that Lichtfield Studio
can load directly.

Usage:
    python scripts/04_undistort.py <project_name> [--overwrite]

Examples:
    python scripts/04_undistort.py 20260411-house
    python scripts/04_undistort.py 20260411-house --overwrite

Expected project layout (output of 03_run_colmap.py):
    projects/<name>/
        images/         <- culled frames (COLMAP input)
        sparse/0/       <- sparse model (cameras.bin, images.bin, points3D.bin)
        dense/          <- created by this script, Lichtfield Studio input

After this script:
    projects/<name>/dense/
        images/         <- undistorted images
        sparse/         <- undistorted sparse model
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_paths(projects_root: Path, project_name: str) -> dict:
    proj = projects_root / project_name
    return {
        "project": proj,
        "images":  proj / "images",
        "sparse":  proj / "sparse" / "0",
        "dense":   proj / "dense",
    }


def preflight(projects_root: Path, project_name: str, overwrite: bool = False):
    paths = resolve_paths(projects_root, project_name)

    if not paths["project"].exists():
        sys.exit(
            f"Project not found: {paths['project']}\n"
            f"Create it first with: .\\scripts\\01-create-project.ps1 -ProjectName {project_name}"
        )

    if not paths["images"].exists():
        sys.exit(f"images/ folder not found: {paths['images']}\n"
                 f"Run 02_cull_frames.py first.")

    if not paths["sparse"].exists():
        sys.exit(f"sparse/0/ folder not found: {paths['sparse']}\n"
                 f"Run 03_run_colmap.py first.")

    # Check if dense/ already has output
    dense_images = paths["dense"] / "images"
    if dense_images.exists() and any(dense_images.iterdir()):
        if not overwrite:
            sys.exit(
                f"dense/ already contains output. Use --overwrite to re-run."
            )
        shutil.rmtree(paths["dense"])
        paths["dense"].mkdir()
