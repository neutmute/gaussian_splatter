"""
04_train_splat.py — Train a 3D Gaussian Splat from a COLMAP project.

Wraps the gaussian-splatting train.py with VRAM auto-detection, downsample
selection, real-time loss monitoring, and a clear summary on completion.

Usage:
    python scripts/04_train_splat.py <project_dir> [options]

Examples:
    python scripts/04_train_splat.py projects/house_01
    python scripts/04_train_splat.py projects/house_01 --iterations 10000
    python scripts/04_train_splat.py projects/house_01 --downsample 4
    python scripts/04_train_splat.py projects/house_01 --repo C:/gaussian-splatting

Expected project layout (output of 03_run_colmap.py):
    <project_dir>/
        images/          <- undistorted frames
        sparse/          <- COLMAP sparse model

Output:
    <project_dir>/output/point_cloud/iteration_<N>/point_cloud.ply
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# VRAM detection
# ---------------------------------------------------------------------------

def get_vram_gb() -> float | None:
    """Query the first NVIDIA GPU's total VRAM via nvidia-smi. Returns None on failure."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            line = result.stdout.strip().splitlines()[0]
            return float(line.strip()) / 1024  # MiB → GiB
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        pass
    return None


def recommend_downsample(vram_gb: float | None) -> int:
    """Return a suggested downsample factor based on available VRAM."""
    if vram_gb is None:
        return 2   # can't detect — be conservative
    if vram_gb >= 16:
        return 1   # full resolution
    if vram_gb >= 10:
        return 2
    if vram_gb >= 6:
        return 4
    return 8


def downsample_images_flag(factor: int) -> str:
    """Convert a numeric downsample factor to the gaussian-splatting --images argument."""
    return "images" if factor == 1 else f"images_{factor}"


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def validate_project(project: Path) -> None:
    """Exit with a clear message if the project dir is missing expected COLMAP output."""
    if not project.exists():
        sys.exit(f"ERROR: project directory not found: {project}")

    sparse = project / "sparse"
    images = project / "images"

    if not sparse.exists() or not any(sparse.iterdir()):
        sys.exit(
            f"ERROR: no sparse model found at {sparse}\n"
            "Run 03_run_colmap.py first."
        )
    if not images.exists() or not any(images.iterdir()):
        sys.exit(
            f"ERROR: undistorted images not found at {images}\n"
            "Run 03_run_colmap.py first."
        )


def find_train_script(repo: Path) -> Path:
    """Locate train.py in the gaussian-splatting repo; exit if missing."""
    train = repo / "train.py"
    if not train.exists():
        sys.exit(
            f"ERROR: train.py not found at {train}\n"
            "Clone the repo: git clone https://github.com/graphdeco-inria/gaussian-splatting\n"
            "Then pass its path with --repo <path>."
        )
    return train


# ---------------------------------------------------------------------------
# Training process + loss monitoring
# ---------------------------------------------------------------------------

# Matches lines like:
#   [ITER 5000] loss: 0.04512
#   iteration 5000 / 30000, l1_loss: 0.04512
#   Loss: 0.04512
LOSS_RE = re.compile(r"(?:loss|l1_loss)[:\s]+([0-9]+\.[0-9]+)", re.IGNORECASE)
ITER_RE = re.compile(r"(?:iter(?:ation)?)[:\s\[]+([0-9]+)", re.IGNORECASE)


def run_training(
    python_bin: str,
    train_script: Path,
    project: Path,
    output_path: Path,
    iterations: int,
    images_flag: str,
    extra_args: list[str],
    loss_stall_threshold: float = 0.1,
    loss_stall_check_iter: int = 5000,
) -> float | None:
    """
    Run train.py, stream output line-by-line, monitor for loss stalls.
    Returns the last observed loss value, or None if none was parsed.
    """
    cmd = [
        python_bin, str(train_script),
        "-s", str(project),
        "--model_path", str(output_path),
        "--iterations", str(iterations),
        "--images", images_flag,
        *extra_args,
    ]

    print(f"\n{'='*60}")
    print("  Starting training")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    last_loss: float | None = None
    stall_warned = False

    for line in proc.stdout:
        print(line, end="", flush=True)

        loss_match = LOSS_RE.search(line)
        iter_match = ITER_RE.search(line)

        if loss_match:
            last_loss = float(loss_match.group(1))

        if (
            not stall_warned
            and loss_match
            and iter_match
            and last_loss is not None
        ):
            iteration = int(iter_match.group(1))
            if iteration >= loss_stall_check_iter and last_loss > loss_stall_threshold:
                print(
                    f"\nWARNING: Loss is {last_loss:.4f} at iteration {iteration} "
                    f"(threshold {loss_stall_threshold}).\n"
                    "  This suggests poor camera poses or insufficient scene coverage.\n"
                    "  Check COLMAP registration — fewer than 70% of images registered\n"
                    "  is a common cause. Training will continue but quality may be low.\n"
                )
                stall_warned = True

    proc.wait()

    if proc.returncode != 0:
        sys.exit(f"\nERROR: Training failed (exit code {proc.returncode}).")

    return last_loss


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a 3D Gaussian Splat from a COLMAP project directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project_dir", type=Path,
                        help="Project root (must contain images/ and sparse/ from COLMAP).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory for the trained model. "
                             "Defaults to <project_dir>/output.")
    parser.add_argument("--iterations", type=int, default=30000,
                        help="Training iterations (default: 30000). Use 10000 for a quick test.")
    parser.add_argument("--downsample", type=str, default="auto",
                        choices=["auto", "1", "2", "4", "8"],
                        help="Image downsample factor (default: auto — chosen from VRAM). "
                             "1=full, 2=half, 4=quarter, 8=eighth.")
    parser.add_argument("--repo", type=Path, default=Path("gaussian-splatting"),
                        help="Path to the gaussian-splatting repo (default: ./gaussian-splatting).")
    parser.add_argument("--python", default="python",
                        help="Python executable to use (default: python). "
                             "Set this if the repo requires a specific venv/conda env.")
    args, extra_args = parser.parse_known_args()
    # extra_args: anything unrecognised is passed straight through to train.py

    project    = args.project_dir.resolve()
    output_dir = (args.output or project / "output").resolve()
    repo       = args.repo.resolve()

    # --- Validate inputs ---
    validate_project(project)
    train_script = find_train_script(repo)

    # --- VRAM detection + downsample ---
    vram_gb = get_vram_gb()
    if vram_gb is not None:
        print(f"Detected VRAM : {vram_gb:.1f} GB")
    else:
        print("VRAM detection : unavailable (nvidia-smi not found or no NVIDIA GPU)")

    if args.downsample == "auto":
        factor = recommend_downsample(vram_gb)
        source = "auto-selected"
    else:
        factor = int(args.downsample)
        source = "user-specified"

    images_flag = downsample_images_flag(factor)

    # Warn if the chosen images_N folder doesn't exist
    images_dir = project / images_flag
    if not images_dir.exists():
        if factor == 1:
            sys.exit(
                f"ERROR: images/ folder not found at {project / 'images'}\n"
                "Run 03_run_colmap.py first."
            )
        else:
            print(
                f"WARNING: {images_dir} does not exist — "
                f"gaussian-splatting will need to generate it.\n"
                f"If training fails, try running with --downsample 1 instead."
            )

    print(f"Downsample    : {factor}x ({source}) → --images {images_flag}")

    if vram_gb is not None and factor == 1 and vram_gb < 10:
        print(
            f"WARNING: Full resolution selected but only {vram_gb:.1f} GB VRAM detected.\n"
            "  You may run out of memory. Consider --downsample 2 or --downsample 4."
        )

    print(f"Iterations    : {args.iterations}")
    if args.iterations < 30000:
        print(
            f"  Note: {args.iterations} iterations is below the recommended 30000. "
            "Quality will be lower — good for quick testing."
        )
    print(f"Output        : {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Train ---
    last_loss = run_training(
        python_bin=args.python,
        train_script=train_script,
        project=project,
        output_path=output_dir,
        iterations=args.iterations,
        images_flag=images_flag,
        extra_args=extra_args,
    )

    # --- Summary ---
    ply_path = output_dir / "point_cloud" / f"iteration_{args.iterations}" / "point_cloud.ply"

    print("\n" + "="*60)
    print("  Training complete.")
    if last_loss is not None:
        print(f"  Final loss    : {last_loss:.6f}")
        if last_loss > 0.05:
            print(
                f"  WARNING: Final loss {last_loss:.4f} is higher than expected (target <0.05).\n"
                "  The splat may look blurry or have artefacts.\n"
                "  Consider re-running COLMAP with --exhaustive or recapturing the scene."
            )
    if ply_path.exists():
        print(f"  Output .ply   : {ply_path}")
        print("  View online   : drag .ply into https://supersplat.playcanvas.com")
    else:
        print(f"  WARNING: expected .ply not found at {ply_path}")
        print("  Check training logs above for errors.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
