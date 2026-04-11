"""
02_cull_frames.py - Frame QC and culling for Gaussian Splat pipeline

Scores every frame for sharpness (Laplacian variance) and flags near-duplicates
(structural similarity to the previous kept frame). Produces a cull_report.txt
and optionally moves or deletes flagged frames.

Usage:
    python scripts/02_cull_frames.py [options]

Options:
    --frames-dir DIR        Input frames folder (default: ./frames)
    --output-dir DIR        Destination for kept frames (default: ./input)
    --blur-threshold FLOAT  Laplacian variance below this = blurry (default: 100)
    --sim-threshold FLOAT   Normalised similarity above this = duplicate (default: 0.985)
    --dry-run               Report only, do not move or delete anything
    --auto-cull             Move flagged frames to frames/culled/ without prompting
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

try:
    import cv2
    import numpy as np
    from tqdm import tqdm
except ImportError:
    sys.exit("Missing dependency: pip install opencv-python numpy tqdm")


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def normalised_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute difference converted to a 0-1 similarity score."""
    diff = np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32)))
    return 1.0 - diff / 255.0


def score_frame(path: Path, thumb_size=(320, 180)):
    img = cv2.imread(str(path))
    if img is None:
        return None, None
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur_score = laplacian_variance(gray)
    thumb = cv2.resize(gray, thumb_size, interpolation=cv2.INTER_AREA)
    return blur_score, thumb


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Cull blurry / duplicate frames")
    parser.add_argument("--frames-dir", default="frames",
                        help="Folder containing extracted frames (default: ./frames)")
    parser.add_argument("--output-dir", default="input",
                        help="Folder to copy kept frames into (default: ./input)")
    parser.add_argument("--blur-threshold", type=float, default=100.0,
                        help="Laplacian variance threshold; below = blurry (default: 100)")
    parser.add_argument("--sim-threshold", type=float, default=0.985,
                        help="Similarity threshold; above = duplicate (default: 0.985)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report only, do not move or delete files")
    parser.add_argument("--auto-cull", action="store_true",
                        help="Move flagged frames to frames/culled/ without prompting")
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    output_dir = Path(args.output_dir)
    culled_dir = frames_dir / "culled"

    if not frames_dir.exists():
        sys.exit(f"Frames directory not found: {frames_dir}")

    frames = sorted(frames_dir.glob("*.jpg"))
    if not frames:
        sys.exit(f"No JPG frames found in {frames_dir}")

    print(f"\nScanning {len(frames)} frames in {frames_dir}/")
    print(f"  Blur threshold : {args.blur_threshold}  (Laplacian variance)")
    print(f"  Sim threshold  : {args.sim_threshold}  (duplicate detection)")
    print()

    results = []          # (path, blur_score, reason_flagged_or_None)
    prev_thumb = None

    for path in tqdm(frames, desc="Scoring frames", unit="frame"):
        blur_score, thumb = score_frame(path)
        if blur_score is None:
            print(f"  [WARN] Could not read {path.name}, skipping")
            continue

        flag = None

        if blur_score < args.blur_threshold:
            flag = f"blurry (score={blur_score:.1f})"
        elif prev_thumb is not None:
            sim = normalised_similarity(prev_thumb, thumb)
            if sim > args.sim_threshold:
                flag = f"duplicate (sim={sim:.4f})"

        results.append((path, blur_score, flag))

        if flag is None:
            prev_thumb = thumb  # only update reference on a kept frame

    # Summary
    total      = len(results)
    flagged    = [r for r in results if r[2] is not None]
    kept_count = total - len(flagged)

    print(f"Results: {total} scanned, {len(flagged)} flagged, {kept_count} to keep")
    print()

    # Write report
    report_path = frames_dir / "cull_report.txt"
    if not args.dry_run:
        with open(report_path, "w") as f:
            f.write(f"Total frames : {total}\n")
            f.write(f"Flagged      : {len(flagged)}\n")
            f.write(f"Kept         : {kept_count}\n")
            f.write(f"Blur thresh  : {args.blur_threshold}\n")
            f.write(f"Sim thresh   : {args.sim_threshold}\n\n")
            for path, score, flag in results:
                status = f"FLAGGED  {flag}" if flag else f"ok       score={score:.1f}"
                f.write(f"{path.name}  {status}\n")
        print(f"Report written: {report_path}")

    if args.dry_run:
        print("[DRY RUN] Flagged files:")
        for path, _, flag in flagged:
            print(f"  {path.name}  -- {flag}")
        print(f"\n[DRY RUN] {len(flagged)} frames would be moved to {culled_dir}/")
        print(f"[DRY RUN] {kept_count} frames would be copied to {output_dir}/")
        return

    # Decide what to do with flagged frames
    if flagged:
        if args.auto_cull:
            do_cull = True
        else:
            ans = input(f"Move {len(flagged)} flagged frames to {culled_dir}/? [y/N] ").strip()
            do_cull = ans.lower() == "y"

        if do_cull:
            culled_dir.mkdir(parents=True, exist_ok=True)
            for path, _, _ in flagged:
                shutil.move(str(path), culled_dir / path.name)
            print(f"Moved {len(flagged)} flagged frames to {culled_dir}/")
        else:
            print("Flagged frames left in place.")

    # Copy kept frames to output dir
    kept = [r for r in results if r[2] is None]
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, _, _ in kept:
        shutil.copy2(str(path), output_dir / path.name)
    print(f"Copied {len(kept)} kept frames to {output_dir}/")
    print("\nNext step: run 03_run_colmap.py")


if __name__ == "__main__":
    main()
