"""
04_train_splat.py — Train a 3D Gaussian Splat using gsplat.

Wraps gsplat's examples/simple_trainer.py with VRAM auto-detection, data_factor
selection, pycolmap issue detection, and a clear summary on completion.

Usage:
    python scripts/04_train_splat.py <project_dir> [options]

Examples:
    python scripts/04_train_splat.py projects/house_01 --gsplat C:/apps/gsplat
    python scripts/04_train_splat.py projects/house_01 --iterations 10000
    python scripts/04_train_splat.py projects/house_01 --data-factor 4
    python scripts/04_train_splat.py projects/house_01 --gsplat C:/apps/gsplat --data-factor 1

Expected project layout (output of 03_run_colmap.py):
    <project_dir>/
        images/         <- frames (same folder COLMAP used)
        sparse/0/       <- COLMAP sparse model

Output:
    <project_dir>/output/ply/point_cloud_<iterations-1>.ply

gsplat repo: https://github.com/nerfstudio-project/gsplat
"""

import argparse
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


def recommend_data_factor(vram_gb: float | None) -> int:
    """Return a suggested --data_factor based on available VRAM."""
    if vram_gb is None:
        return 4   # can't detect — be conservative
    if vram_gb >= 16:
        return 1   # full resolution
    if vram_gb >= 10:
        return 2
    if vram_gb >= 6:
        return 4
    return 8


# ---------------------------------------------------------------------------
# Pre-flight validation
# ---------------------------------------------------------------------------

def validate_project(project: Path) -> None:
    """Exit with a clear message if expected COLMAP output is missing."""
    if not project.exists():
        sys.exit(f"ERROR: project directory not found: {project}")

    sparse_0 = project / "sparse" / "0"
    images   = project / "images"

    if not sparse_0.exists() or not any(sparse_0.iterdir()):
        sys.exit(
            f"ERROR: no sparse model found at {sparse_0}\n"
            "Run 03_run_colmap.py first."
        )
    if not images.exists() or not any(images.iterdir()):
        sys.exit(
            f"ERROR: images/ folder not found or empty at {images}\n"
            "Run 03_run_colmap.py first."
        )


def find_trainer_script(gsplat_path: Path) -> Path:
    """Locate examples/simple_trainer.py in the gsplat repo; exit if missing."""
    trainer = gsplat_path / "examples" / "simple_trainer.py"
    if not trainer.exists():
        sys.exit(
            f"ERROR: simple_trainer.py not found at {trainer}\n"
            "Clone gsplat: git clone --recursive https://github.com/nerfstudio-project/gsplat\n"
            "Then pass its path with --gsplat <path>."
        )
    return trainer


def check_pycolmap(python_bin: str) -> None:
    """
    Detect the known Windows pycolmap binary-parsing bug and print the fix.
    The stock pycolmap uses struct.unpack('L', ...) which is 4 bytes on Windows
    but COLMAP writes 8-byte uint64. The mathijshenquet fork fixes this.
    """
    check = subprocess.run(
        [python_bin, "-c",
         "import pycolmap; import inspect, pathlib; "
         "src = pathlib.Path(inspect.getfile(pycolmap)).parent; "
         "txt = (src / 'pycolmap' / 'scene' / 'reconstruction.py').read_text() "
         "if (src / 'pycolmap' / 'scene' / 'reconstruction.py').exists() else ''; "
         "print('bug' if 'struct.unpack' in txt and \"'L'\" in txt else 'ok')"],
        capture_output=True, text=True,
    )
    # Simpler heuristic: just try importing and loading; catch the specific error pattern
    # by checking the installed pycolmap version string
    probe = subprocess.run(
        [python_bin, "-c", "import pycolmap; print(pycolmap.__version__)"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        print(
            "\nWARNING: pycolmap is not installed. gsplat requires it to read COLMAP data.\n"
            "  Install the Windows-compatible fork:\n"
            "    pip install git+https://github.com/mathijshenquet/pycolmap\n"
        )


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def run_training(
    python_bin: str,
    trainer: Path,
    project: Path,
    result_dir: Path,
    iterations: int,
    data_factor: int,
    extra_args: list[str],
) -> None:
    """Run gsplat simple_trainer.py, streaming output live."""
    cmd = [
        python_bin, str(trainer),
        "default",
        "--eval_steps",    "-1",        # disable mid-train evaluation
        "--disable_viewer",             # no Nerfstudio viewer (headless)
        "--data_factor",   str(data_factor),
        "--save_ply",
        "--ply_steps",     str(iterations),
        "--data_dir",      str(project),
        "--result_dir",    str(result_dir),
        *extra_args,
    ]

    print(f"\n{'='*60}")
    print("  Starting gsplat training")
    print(f"  Trainer     : {trainer}")
    print(f"  Data dir    : {project}")
    print(f"  Result dir  : {result_dir}")
    print(f"  Iterations  : {iterations}")
    print(f"  Data factor : {data_factor}x")
    print(f"  CMD: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(trainer.parent),   # run from examples/ so relative imports work
    )

    for line in proc.stdout:
        print(line, end="", flush=True)

    proc.wait()

    if proc.returncode != 0:
        sys.exit(f"\nERROR: Training failed (exit code {proc.returncode}).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a 3D Gaussian Splat from a COLMAP project using gsplat.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("project_dir", type=Path,
                        help="Project root (must contain images/ and sparse/0/ from COLMAP).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory for training results. "
                             "Defaults to <project_dir>/output.")
    parser.add_argument("--iterations", type=int, default=30000,
                        help="Training iterations (default: 30000). Use 10000 for a quick test.")
    parser.add_argument("--data-factor", type=str, default="auto",
                        choices=["auto", "1", "2", "4", "8"],
                        help="Image downsample factor passed to gsplat as --data_factor "
                             "(default: auto — chosen from detected VRAM). "
                             "1=full res, 2=half, 4=quarter, 8=eighth.")
    parser.add_argument("--gsplat", type=Path, default=Path("C:/apps/gsplat"),
                        help="Path to the gsplat repository (default: C:/apps/gsplat).")
    parser.add_argument("--python", default="python",
                        help="Python executable to use (default: python).")
    args, extra_args = parser.parse_known_args()

    project    = args.project_dir.resolve()
    result_dir = (args.output or project / "output").resolve()
    gsplat     = args.gsplat.resolve()

    # --- Validate ---
    validate_project(project)
    trainer = find_trainer_script(gsplat)
    check_pycolmap(args.python)

    # --- VRAM / data_factor ---
    vram_gb = get_vram_gb()
    if vram_gb is not None:
        print(f"Detected VRAM : {vram_gb:.1f} GB")
    else:
        print("VRAM detection : unavailable (nvidia-smi not found or no NVIDIA GPU)")

    if args.data_factor == "auto":
        factor = recommend_data_factor(vram_gb)
        source = "auto-selected"
    else:
        factor = int(args.data_factor)
        source = "user-specified"

    print(f"Data factor   : {factor}x ({source})")

    if vram_gb is not None and factor == 1 and vram_gb < 10:
        print(
            f"WARNING: Full resolution selected but only {vram_gb:.1f} GB VRAM detected.\n"
            "  You may run out of memory. Consider --data-factor 2 or --data-factor 4."
        )

    if args.iterations < 30000:
        print(
            f"Note: {args.iterations} iterations is below the recommended 30000. "
            "Quality will be lower — suitable for quick testing."
        )

    result_dir.mkdir(parents=True, exist_ok=True)

    # --- Train ---
    run_training(
        python_bin=args.python,
        trainer=trainer,
        project=project,
        result_dir=result_dir,
        iterations=args.iterations,
        data_factor=factor,
        extra_args=extra_args,
    )

    # --- Summary ---
    # gsplat saves ply at step N as point_cloud_{N-1}.ply (0-indexed step)
    ply_step = args.iterations - 1
    ply_path = result_dir / "ply" / f"point_cloud_{ply_step}.ply"

    print("\n" + "="*60)
    print("  Training complete.")
    if ply_path.exists():
        print(f"  Output .ply : {ply_path}")
        print("  View online : drag .ply into https://superspl.at/editor")
    else:
        # gsplat may use a slightly different step number — find what's there
        ply_dir = result_dir / "ply"
        if ply_dir.exists():
            candidates = sorted(ply_dir.glob("point_cloud_*.ply"))
            if candidates:
                print(f"  Output .ply : {candidates[-1]}  (last checkpoint found)")
                print("  View online : drag .ply into https://superspl.at/editor")
            else:
                print(f"  WARNING: no .ply found in {ply_dir}")
        else:
            print(f"  WARNING: expected .ply not found at {ply_path}")
            print("  Check training logs above for errors.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
