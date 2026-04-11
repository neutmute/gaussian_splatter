"""
03_run_colmap.py — Run the full COLMAP SfM pipeline for Gaussian Splat.

Runs COLMAP headlessly in four stages:
  1. Feature extraction
  2. Feature matching  (sequential by default, exhaustive with --exhaustive)
  3. Sparse reconstruction (mapper)
  4. Image undistortion

Usage:
    python scripts/03_run_colmap.py <project_dir> [options]

Examples:
    python scripts/03_run_colmap.py projects/house_01
    python scripts/03_run_colmap.py projects/house_01 --exhaustive
    python scripts/03_run_colmap.py projects/house_01 --overlap 25 --colmap-bin "C:/COLMAP/colmap.exe"

Expected project layout (matches 02_cull_frames.py output):
    <project_dir>/
        input/          <- undistorted/culled frames (COLMAP input)
    After this script:
        <project_dir>/
            database.db
            distorted/sparse/0/   <- sparse model
            sparse/               <- undistorted sparse
            images/               <- undistorted images
"""

import argparse
import shutil
import struct
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# COLMAP helpers
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


def count_images_in_input(input_dir: Path) -> int:
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    return sum(1 for p in input_dir.iterdir() if p.suffix.lower() in exts)


def parse_registration_stats(sparse_dir: Path) -> tuple[int, int]:
    """
    Return (registered, registered) by reading the sparse model output.
    Prefers images.bin (COLMAP's default binary output); falls back to images.txt.
    """
    images_bin = sparse_dir / "images.bin"
    images_txt = sparse_dir / "images.txt"

    if images_bin.exists():
        # Binary format: first 8 bytes are a uint64 image count.
        with open(images_bin, "rb") as f:
            num_images = struct.unpack("<Q", f.read(8))[0]
        return num_images, num_images

    if images_txt.exists():
        # Text format: two non-comment lines per registered image.
        image_lines = sum(
            1 for line in images_txt.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        )
        return image_lines // 2, image_lines // 2

    return 0, 0


def count_sparse_models(distorted_sparse: Path) -> int:
    """Return the number of sub-models produced by the mapper (0, 1, 2, …)."""
    if not distorted_sparse.exists():
        return 0
    return sum(1 for p in distorted_sparse.iterdir() if p.is_dir())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full COLMAP SfM pipeline (feature extraction → undistortion).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project_dir", type=Path,
                        help="Project root directory (must contain an 'input/' subfolder with frames).")
    parser.add_argument("--overlap", type=int, default=15,
                        help="Sequential matcher overlap (default: 15). "
                             "Increase to 20–30 for fast-moving or tricky footage.")
    parser.add_argument("--exhaustive", action="store_true",
                        help="Use exhaustive matcher instead of sequential. "
                             "Much slower but more robust for non-sequential or difficult footage.")
    parser.add_argument("--colmap-bin", default="colmap",
                        help="Path to the COLMAP executable (default: 'colmap', assumed on PATH).")
    parser.add_argument("--overwrite", action="store_true",
                        help="Automatically delete an existing database.db and start fresh. "
                             "Without this flag you will be prompted interactively.")
    parser.add_argument("--camera-model", default="OPENCV",
                        help="COLMAP camera model (default: OPENCV). "
                             "Use SIMPLE_RADIAL for GoPro or wide-angle lenses.")
    args = parser.parse_args()

    project   = args.project_dir.resolve()
    colmap    = args.colmap_bin
    input_dir = project / "input"
    db        = project / "database.db"
    dist_sparse = project / "distorted" / "sparse"

    # --- Pre-flight checks ---
    if not project.exists():
        sys.exit(f"ERROR: project directory not found: {project}")
    if not input_dir.exists():
        sys.exit(
            f"ERROR: input/ folder not found inside {project}\n"
            "Run 02_cull_frames.py first to populate it."
        )

    n_input = count_images_in_input(input_dir)
    if n_input == 0:
        sys.exit(f"ERROR: No images found in {input_dir}")
    print(f"Project  : {project}")
    print(f"Images   : {n_input} frames in input/")
    print(f"Matcher  : {'exhaustive' if args.exhaustive else f'sequential (overlap={args.overlap})'}")

    # Handle existing database and sparse output from a previous run
    stale = [p for p in [db, dist_sparse] if p.exists()]
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
                sys.exit(
                    "Aborted. Remove stale files manually or re-run with --overwrite."
                )

    # Verify COLMAP is reachable
    try:
        subprocess.run([colmap, "help"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        sys.exit(
            f"ERROR: COLMAP not found at '{colmap}'.\n"
            "Install COLMAP and ensure it is on your PATH, or pass --colmap-bin <path>."
        )

    # Create output directories
    dist_sparse.mkdir(parents=True, exist_ok=True)

    log_path = project / "colmap.log"
    print(f"Logging COLMAP output to: {log_path}\n")

    with open(log_path, "w") as log_fh:

        # -----------------------------------------------------------------------
        # Stage 1: Feature extraction
        # -----------------------------------------------------------------------
        run(
            [
                colmap, "feature_extractor",
                "--database_path", str(db),
                "--image_path",    str(input_dir),
                "--ImageReader.camera_model",  args.camera_model,
                "--ImageReader.single_camera", "1",
            ],
            step="1/4 — Feature extraction",
            log_fh=log_fh,
        )

        # -----------------------------------------------------------------------
        # Stage 2: Feature matching
        # -----------------------------------------------------------------------
        if args.exhaustive:
            run(
                [colmap, "exhaustive_matcher", "--database_path", str(db)],
                step="2/4 — Exhaustive matching",
                log_fh=log_fh,
            )
        else:
            run(
                [
                    colmap, "sequential_matcher",
                    "--database_path", str(db),
                    "--SequentialMatching.overlap", str(args.overlap),
                ],
                step=f"2/4 — Sequential matching (overlap={args.overlap})",
                log_fh=log_fh,
            )

        # -----------------------------------------------------------------------
        # Stage 3: Sparse reconstruction (mapper)
        # -----------------------------------------------------------------------
        run(
            [
                colmap, "mapper",
                "--database_path", str(db),
                "--image_path",    str(input_dir),
                "--output_path",   str(dist_sparse),
            ],
            step="3/4 — Sparse reconstruction (mapper)",
            log_fh=log_fh,
        )

    # Validate registration
    n_models = count_sparse_models(dist_sparse)
    print(f"\nSparse models produced: {n_models}")

    if n_models == 0:
        sys.exit(
            "ERROR: Mapper produced no sparse model. "
            "Check that frames have sufficient overlap and try --exhaustive."
        )

    if n_models > 1:
        print(
            f"WARNING: {n_models} separate sparse models were produced — reconstruction is fragmented.\n"
            "  Causes: insufficient frame overlap between passes, scene gaps, or too many blurry frames.\n"
            "  Try: --exhaustive matching, increase --overlap, or re-shoot with more bridging frames.\n"
            "  Continuing with model 0 for undistortion (largest is usually 0)."
        )

    sparse_model_0 = dist_sparse / "0"
    registered, _ = parse_registration_stats(sparse_model_0)
    pct = 100 * registered / n_input if n_input else 0
    print(f"Registered: {registered} / {n_input} images ({pct:.1f}%)")

    if registered == 0:
        sys.exit(
            "ERROR: 0 images were registered — reconstruction completely failed.\n"
            "  Common causes:\n"
            "    • Frames too blurry or lacking distinct features\n"
            "    • Insufficient overlap between consecutive frames\n"
            "    • Sequential matcher couldn't link clips (try --exhaustive)\n"
            "    • Wrong camera model for your lens\n"
            "  Try:\n"
            "    • Re-run with --exhaustive\n"
            "    • Re-run 02_cull_frames.py with a higher --blur-threshold\n"
            "    • Increase extraction fps in 01_extract_frames.py for more overlap\n"
            "    • Check COLMAP's output above for specific matching errors"
        )

    if pct < 70:
        print(
            f"WARNING: Only {pct:.1f}% of images were registered (recommend ≥70%).\n"
            "  Try:\n"
            "    • Re-run with --exhaustive for more thorough matching\n"
            "    • Increase --overlap (e.g. --overlap 25)\n"
            "    • Re-run 02_cull_frames.py with a higher --blur-threshold to keep more frames\n"
            "    • Check that input frames cover the scene without large gaps"
        )

        # -----------------------------------------------------------------------
        # Stage 4: Image undistortion
        # -----------------------------------------------------------------------
        run(
            [
                colmap, "image_undistorter",
                "--image_path",  str(input_dir),
                "--input_path",  str(sparse_model_0),
                "--output_path", str(project),
                "--output_type", "COLMAP",
            ],
            step="4/4 — Image undistortion",
            log_fh=log_fh,
        )

    # -----------------------------------------------------------------------
    # Done
    # -----------------------------------------------------------------------
    print("\n" + "="*60)
    print("  COLMAP pipeline complete.")
    print(f"  Registered : {registered} / {n_input} images ({pct:.1f}%)")
    print(f"  Sparse model : {sparse_model_0}")
    print(f"  Undistorted  : {project / 'images'}")
    print(f"  Full log     : {log_path}")
    print("  Next step    : run 04_train_splat.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
