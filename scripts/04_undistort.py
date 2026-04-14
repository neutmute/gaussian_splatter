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


def preflight(projects_root: Path, project_name: str, overwrite: bool = False) -> dict:
    paths = resolve_paths(projects_root, project_name)

    if not paths["project"].exists():
        sys.exit(
            f"ERROR: Project not found: {paths['project']}\n"
            f"Create it first with: .\\scripts\\01-create-project.ps1 -ProjectName {project_name}"
        )

    if not paths["images"].exists():
        sys.exit(f"ERROR: images/ folder not found: {paths['images']}\n"
                 f"Run 02_cull_frames.py first.")

    if not paths["sparse"].exists():
        sys.exit(f"ERROR: sparse/0/ folder not found: {paths['sparse']}\n"
                 f"Run 03_run_colmap.py first.")

    # Check if dense/ already has output
    if paths["dense"].exists() and any(paths["dense"].iterdir()):
        if not overwrite:
            sys.exit(
                "ERROR: dense/ already contains output. Use --overwrite to re-run."
            )
        shutil.rmtree(paths["dense"])

    paths["dense"].mkdir(exist_ok=True)
    return paths


def validate_output(dense: Path) -> int:
    """Check dense/ has images and sparse. Returns image count."""
    dense_images = dense / "images"
    dense_sparse = dense / "sparse"

    if not dense_images.exists():
        sys.exit(f"ERROR: Output validation failed: {dense_images} not found. "
                 f"COLMAP may have crashed — check output above.")

    image_files = list(dense_images.iterdir())
    if not image_files:
        sys.exit(f"ERROR: Output validation failed: {dense_images} is empty. "
                 f"COLMAP may have crashed — check output above.")

    if not dense_sparse.exists():
        sys.exit(f"ERROR: Output validation failed: {dense_sparse} not found.")

    return len(image_files)


def build_colmap_cmd(paths: dict) -> list:
    return [
        "colmap", "image_undistorter",
        "--image_path",     str(paths["images"]),
        "--input_path",     str(paths["sparse"]),
        "--output_path",    str(paths["dense"]),
        "--output_type",    "COLMAP",
        "--max_image_size", "1600",
    ]


def main():
    scripts_dir = Path(__file__).parent
    projects_root = scripts_dir.parent / "projects"

    parser = argparse.ArgumentParser(description="COLMAP undistortion for Lichtfield Studio")
    parser.add_argument("project_name",
                        help="Project folder name under projects\\ (e.g. 20260411-house)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Delete existing dense/ output and re-run")
    args = parser.parse_args()

    paths = preflight(projects_root, args.project_name, overwrite=args.overwrite)

    print(f"\nProject    : {args.project_name}")
    print(f"Images in  : {paths['images']}")
    print(f"Sparse in  : {paths['sparse']}")
    print(f"Dense out  : {paths['dense']}")
    print()

    cmd = build_colmap_cmd(paths)
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"\nERROR: COLMAP exited with code {result.returncode}. Check output above.")

    count = validate_output(paths["dense"])

    print(f"\nDone. Undistorted {count} images -> {paths['dense']}")
    print(f"Next step: open Lichtfield Studio and load {paths['dense']}")


if __name__ == "__main__":
    main()
