"""
03_run_colmap.py — Run the COLMAP SfM pipeline for gsplat.

Runs COLMAP headlessly in three stages:
  1. Feature extraction       (GPU-accelerated)
  2. Feature matching         (sequential by default; exhaustive with --exhaustive)
  3. Sparse reconstruction    (mapper)

Outputs sparse/0/ only. Run 04_undistort.py next to produce the dense/ folder
required by Lichtfield Studio.

Usage:
    python scripts/03_run_colmap.py <project_name_or_dir> [options]

Examples:
    python scripts/03_run_colmap.py 20260411-house
    python scripts/03_run_colmap.py 20260411-house --exhaustive
    python scripts/03_run_colmap.py 20260411-house --exhaustive --guided-matching --relaxed
    python scripts/03_run_colmap.py 20260411-house --overlap 25
    python scripts/03_run_colmap.py 20260411-house --overwrite
    python scripts/03_run_colmap.py projects/20260411-house  (full path also accepted)

Expected project layout (output of 02_cull_frames.py):
    <project_dir>/
        images/         <- culled frames copied here by 02_cull_frames.py

After this script:
    <project_dir>/
        colmap.db
        sparse/0/       <- sparse model (cameras.bin, images.bin, points3D.bin)
"""

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd: list[str], step: str, log_fh) -> None:
    """Run a COLMAP sub-command, streaming output to console and log file. Exit on failure."""
    header = f"\n{'='*60}\n  STEP: {step}\n  CMD : {' '.join(cmd)}\n{'='*60}\n"
    print(header)
    log_fh.write(header + "\n")
    log_fh.flush()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        print(line, end="")
        log_fh.write(line)
    proc.wait()
    log_fh.flush()

    if proc.returncode != 0:
        sys.exit(f"\nERROR: COLMAP failed at step '{step}' (exit code {proc.returncode}).\n"
                 f"Full log: {log_fh.name}")


def count_images(image_dir: Path) -> int:
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    return sum(1 for p in image_dir.iterdir() if p.suffix.lower() in exts)


def parse_registration_stats(sparse_0: Path) -> int:
    """
    Return number of registered images from sparse/0/.
    Reads images.bin (binary COLMAP format) or falls back to images.txt.
    """
    images_bin = sparse_0 / "images.bin"
    images_txt = sparse_0 / "images.txt"

    if images_bin.exists():
        with open(images_bin, "rb") as f:
            num_images = struct.unpack("<Q", f.read(8))[0]
        return num_images

    if images_txt.exists():
        lines = [l for l in images_txt.read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        return len(lines) // 2  # two lines per image in text format

    return 0


def count_sparse_models(sparse_dir: Path) -> int:
    if not sparse_dir.exists():
        return 0
    return sum(1 for p in sparse_dir.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the COLMAP SfM pipeline (feature extraction → sparse reconstruction).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project_dir",
                        help="Project name (e.g. 20260411-house) or full path to project root. "
                             "A bare name is resolved to projects/<name>/ relative to the repo root.")
    parser.add_argument("--overlap", type=int, default=15,
                        help="Sequential matcher overlap (default: 15). "
                             "Increase to 20–30 for fast-moving or multi-clip footage.")
    parser.add_argument("--exhaustive", action="store_true",
                        help="Use exhaustive matcher instead of sequential. "
                             "Slower but more robust for non-sequential or difficult footage.")
    parser.add_argument("--guided-matching", action="store_true",
                        help="Enable guided SIFT matching (geometric constraint filtering). "
                             "Helps with repetitive textures and difficult scenes.")
    parser.add_argument("--relaxed", action="store_true",
                        help="Relax mapper initialisation thresholds — useful when COLMAP "
                             "fails to find an initial pair. Lowers init_min_tri_angle (16→2), "
                             "init_min_num_inliers (100→4), abs_pose_min_num_inliers (30→3), "
                             "abs_pose_max_error (12→8).")
    parser.add_argument("--camera-model", default="OPENCV",
                        help="COLMAP camera model (default: OPENCV — standard wide-angle drone lenses). "
                             "Use OPENCV_FISHEYE for fisheye lenses such as the DJI Avata 2 (155° FOV). "
                             "Use PINHOLE for near-distortion-free lenses.")
    parser.add_argument("--colmap-bin", default="colmap",
                        help="Path to the COLMAP executable (default: 'colmap', assumed on PATH).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Delete existing colmap.db and sparse/ and start fresh.")
    args = parser.parse_args()

    # Accept bare project name (e.g. "20260411-house") or a full/relative path.
    # A bare name (no path separators) is resolved to projects/<name>/ from the repo root.
    raw = Path(args.project_dir)
    if raw.parts == (raw.name,):  # no directory component → bare name
        repo_root = Path(__file__).resolve().parent.parent
        project = (repo_root / "projects" / raw).resolve()
    else:
        project = raw.resolve()

    colmap     = args.colmap_bin
    images_dir = project / "images"
    db         = project / "colmap.db"
    sparse_dir = project / "sparse"

    # --- Pre-flight checks ---
    if not project.exists():
        sys.exit(f"ERROR: project directory not found: {project}")
    if not images_dir.exists():
        sys.exit(
            f"ERROR: images/ folder not found inside {project}\n"
            "Run 02_cull_frames.py first to populate it."
        )

    n_input = count_images(images_dir)
    if n_input == 0:
        sys.exit(f"ERROR: No images found in {images_dir}")

    print(f"Project  : {project}")
    print(f"Images   : {n_input} frames in images/")
    print(f"Matcher  : {'exhaustive' if args.exhaustive else f'sequential (overlap={args.overlap})'}"
          + (" + guided" if args.guided_matching else ""))
    print(f"Camera   : {args.camera_model}")
    if args.relaxed:
        print("Mapper   : relaxed initialisation thresholds")

    # Handle stale output from a previous run
    stale = [p for p in [db, sparse_dir] if p.exists()]
    if stale:
        if args.overwrite:
            for p in stale:
                print(f"Removing stale output: {p}")
                p.unlink() if p.is_file() else shutil.rmtree(p)
        else:
            stale_list = "\n  ".join(str(p) for p in stale)
            ans = input(
                f"\nStale output from a previous run exists:\n  {stale_list}\n"
                "Reusing these will corrupt results. Delete and start fresh? [Y/n] "
            ).strip().lower()
            if ans in ("", "y", "yes"):
                for p in stale:
                    print(f"Removing {p}")
                    p.unlink() if p.is_file() else shutil.rmtree(p)
            else:
                sys.exit("Aborted. Remove stale files manually or re-run with --overwrite.")

    # Verify COLMAP is reachable
    try:
        subprocess.run([colmap, "help"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit(
            f"ERROR: COLMAP not found at '{colmap}'.\n"
            "Download v3.11+ from https://github.com/colmap/colmap/releases\n"
            "and ensure it is on your PATH, or pass --colmap-bin <path>."
        )

    sparse_dir.mkdir(parents=True, exist_ok=True)

    log_path = project / "colmap.log"
    print(f"Logging to : {log_path}\n")

    with open(log_path, "w") as log_fh:

        # -------------------------------------------------------------------
        # Stage 1: Feature extraction
        # -------------------------------------------------------------------
        run(
            [
                colmap, "feature_extractor",
                "--database_path",             str(db),
                "--image_path",                str(images_dir),
                "--ImageReader.camera_model",  args.camera_model,
                "--ImageReader.single_camera", "1",
            ],
            step="1/3 — Feature extraction",
            log_fh=log_fh,
        )

        # -------------------------------------------------------------------
        # Stage 2: Feature matching
        # -------------------------------------------------------------------
        guided_flag = ["--SiftMatching.guided_matching", "1"] if args.guided_matching else []

        if args.exhaustive:
            run(
                [
                    colmap, "exhaustive_matcher",
                    "--database_path",          str(db),
                    *guided_flag,
                ],
                step="2/3 — Exhaustive matching" + (" (guided)" if args.guided_matching else ""),
                log_fh=log_fh,
            )
        else:
            run(
                [
                    colmap, "sequential_matcher",
                    "--database_path",                    str(db),
                    "--SequentialMatching.overlap",       str(args.overlap),
                    *guided_flag,
                ],
                step=f"2/3 — Sequential matching (overlap={args.overlap})"
                     + (" (guided)" if args.guided_matching else ""),
                log_fh=log_fh,
            )

        # -------------------------------------------------------------------
        # Stage 3: Sparse reconstruction (mapper)
        # -------------------------------------------------------------------
        mapper_cmd = [
            colmap, "mapper",
            "--database_path", str(db),
            "--image_path",    str(images_dir),
            "--output_path",   str(sparse_dir),
        ]
        if args.relaxed:
            mapper_cmd += [
                "--Mapper.init_min_tri_angle",       "2",   # default 16
                "--Mapper.init_min_num_inliers",     "4",   # default 100
                "--Mapper.abs_pose_min_num_inliers", "3",   # default 30
                "--Mapper.abs_pose_max_error",       "8",   # default 12
            ]
        run(
            mapper_cmd,
            step="3/3 — Sparse reconstruction (mapper)" + (" [relaxed]" if args.relaxed else ""),
            log_fh=log_fh,
        )

    # --- Validate output ---
    n_models = count_sparse_models(sparse_dir)
    print(f"\nSparse models produced: {n_models}")

    if n_models == 0:
        sys.exit(
            "ERROR: Mapper produced no sparse model.\n"
            "  Try: --exhaustive, --relaxed, or increase frame density (re-run 01_extract_frames.py)."
        )

    if n_models > 1:
        print(
            f"WARNING: {n_models} separate sparse models produced — reconstruction is fragmented.\n"
            "  Causes: gaps between passes, insufficient overlap, too many blurry frames.\n"
            "  Try: --exhaustive, --guided-matching, or re-shoot with more bridging frames.\n"
            "  Continuing with model 0 (usually the largest)."
        )

    sparse_0 = sparse_dir / "0"
    registered = parse_registration_stats(sparse_0)
    pct = 100 * registered / n_input if n_input else 0
    print(f"Registered : {registered} / {n_input} images ({pct:.1f}%)")

    if registered == 0:
        sys.exit(
            "ERROR: 0 images registered — reconstruction failed completely.\n"
            "  Common causes:\n"
            "    • Frames too blurry or lacking distinct features\n"
            "    • Insufficient overlap between consecutive frames\n"
            "    • Sequential matcher couldn't link multi-clip footage (try --exhaustive)\n"
            "  Try:\n"
            "    • Re-run with --exhaustive --relaxed\n"
            "    • Re-run 02_cull_frames.py with a higher --blur-threshold\n"
            "    • Increase fps in 01_extract_frames.py for more frame overlap"
        )

    if pct < 70:
        print(
            f"WARNING: Only {pct:.1f}% of images registered (recommend ≥70%).\n"
            "  Try: --exhaustive --guided-matching, or increase --overlap (e.g. --overlap 25)"
        )

    print("\n" + "="*60)
    print("  COLMAP pipeline complete.")
    print(f"  Registered  : {registered} / {n_input} images ({pct:.1f}%)")
    print(f"  Sparse model: {sparse_0}")
    print(f"  Full log    : {log_path}")
    print("  Next step   : python scripts/04_undistort.py <project_name>")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
