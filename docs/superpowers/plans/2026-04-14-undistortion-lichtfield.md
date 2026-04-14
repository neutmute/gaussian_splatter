# Undistortion Step + Lichtfield Studio Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the gsplat training step with a COLMAP undistortion script (`04_undistort.py`) that outputs a `dense/` folder ready for Lichtfield Studio, and update all docs and scaffolding to match.

**Architecture:** New `04_undistort.py` follows the same project-name interface as `02_cull_frames.py` and `03_run_colmap.py` — takes a project name, resolves paths from the standard folder structure, wraps `colmap image_undistorter`. CLAUDE.md Step 4 and Step 5 are replaced in-place. `01-create-project.ps1` gets `dense/` added to its folder list.

**Tech Stack:** Python 3.10, COLMAP CLI (`image_undistorter`), PowerShell, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/04_undistort.py` | Create | Wraps `colmap image_undistorter`, validates output, prints next-step hint |
| `tests/test_04_undistort.py` | Create | Tests path resolution, pre-flight validation, output validation |
| `scripts/01-create-project.ps1` | Modify | Add `dense/` to folder list; update next-steps message |
| `CLAUDE.md` | Modify | Replace Step 4 (undistortion) + Step 5 (Lichtfield); update folder tree; remove "NO undistorter" note |

---

## Task 1: Write `04_undistort.py` — path resolution and pre-flight validation

**Files:**
- Create: `scripts/04_undistort.py`
- Create: `tests/test_04_undistort.py`

- [ ] **Step 1: Write failing tests for path resolution and pre-flight checks**

Create `tests/test_04_undistort.py`:

```python
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

# Add scripts/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import importlib
undistort = importlib.import_module("04_undistort")


@pytest.fixture
def project(tmp_path):
    """Minimal valid project structure."""
    p = tmp_path / "projects" / "test-project"
    (p / "images").mkdir(parents=True)
    (p / "images" / "frame_0001.jpg").write_bytes(b"")
    (p / "sparse" / "0").mkdir(parents=True)
    (p / "dense").mkdir()
    return tmp_path, p


def test_resolve_paths_from_project_name(project):
    root, proj = project
    paths = undistort.resolve_paths(root / "projects", "test-project")
    assert paths["images"] == proj / "images"
    assert paths["sparse"] == proj / "sparse" / "0"
    assert paths["dense"] == proj / "dense"


def test_preflight_fails_when_project_missing(tmp_path):
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    with pytest.raises(SystemExit):
        undistort.preflight(projects_root, "nonexistent-project")


def test_preflight_fails_when_images_missing(tmp_path):
    proj = tmp_path / "projects" / "test-project"
    (proj / "sparse" / "0").mkdir(parents=True)
    (proj / "dense").mkdir()
    with pytest.raises(SystemExit):
        undistort.preflight(tmp_path / "projects", "test-project")


def test_preflight_fails_when_sparse_missing(tmp_path):
    proj = tmp_path / "projects" / "test-project"
    (proj / "images").mkdir(parents=True)
    (proj / "dense").mkdir()
    with pytest.raises(SystemExit):
        undistort.preflight(tmp_path / "projects", "test-project")


def test_preflight_fails_when_dense_has_content_and_no_overwrite(project):
    root, proj = project
    (proj / "dense" / "images").mkdir()
    (proj / "dense" / "images" / "f.jpg").write_bytes(b"")
    with pytest.raises(SystemExit):
        undistort.preflight(root / "projects", "test-project", overwrite=False)


def test_preflight_deletes_dense_when_overwrite(project):
    root, proj = project
    (proj / "dense" / "images").mkdir()
    (proj / "dense" / "images" / "f.jpg").write_bytes(b"")
    undistort.preflight(root / "projects", "test-project", overwrite=True)
    assert not (proj / "dense" / "images").exists()
```

- [ ] **Step 2: Run tests — expect failure (module doesn't exist yet)**

```
pytest tests/test_04_undistort.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` for `04_undistort`.

- [ ] **Step 3: Implement path resolution and pre-flight in `04_undistort.py`**

Create `scripts/04_undistort.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect path resolution and pre-flight tests to pass**

```
pytest tests/test_04_undistort.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```
git add scripts/04_undistort.py tests/test_04_undistort.py
git commit -m "feat: add 04_undistort.py path resolution and pre-flight validation"
```

---

## Task 2: Write `04_undistort.py` — COLMAP invocation and output validation

**Files:**
- Modify: `scripts/04_undistort.py`
- Modify: `tests/test_04_undistort.py`

- [ ] **Step 1: Write failing tests for COLMAP invocation and output validation**

Append to `tests/test_04_undistort.py`:

```python
from unittest.mock import MagicMock, call


def test_validate_output_passes_when_dense_populated(project):
    root, proj = project
    (proj / "dense" / "images").mkdir(parents=True)
    (proj / "dense" / "images" / "frame_0001.jpg").write_bytes(b"")
    (proj / "dense" / "sparse").mkdir(parents=True)
    count = undistort.validate_output(proj / "dense")
    assert count == 1


def test_validate_output_fails_when_dense_images_empty(project):
    root, proj = project
    (proj / "dense" / "images").mkdir(parents=True)
    (proj / "dense" / "sparse").mkdir(parents=True)
    with pytest.raises(SystemExit):
        undistort.validate_output(proj / "dense")


def test_validate_output_fails_when_dense_sparse_missing(project):
    root, proj = project
    (proj / "dense" / "images").mkdir(parents=True)
    (proj / "dense" / "images" / "frame_0001.jpg").write_bytes(b"")
    with pytest.raises(SystemExit):
        undistort.validate_output(proj / "dense")


def test_build_colmap_cmd(project):
    root, proj = project
    paths = undistort.resolve_paths(root / "projects", "test-project")
    cmd = undistort.build_colmap_cmd(paths)
    assert cmd[0] == "colmap"
    assert "image_undistorter" in cmd
    assert "--max_image_size" in cmd
    assert "1600" in cmd
    assert str(paths["images"]) in cmd
    assert str(paths["sparse"]) in cmd
    assert str(paths["dense"]) in cmd
```

- [ ] **Step 2: Run tests — expect 4 new failures**

```
pytest tests/test_04_undistort.py -v
```

Expected: 6 pass (from Task 1), 4 fail (`validate_output` and `build_colmap_cmd` not yet defined).

- [ ] **Step 3: Implement `validate_output` and `build_colmap_cmd`**

Append to `scripts/04_undistort.py` (after `preflight`):

```python
def validate_output(dense: Path) -> int:
    """Check dense/ has images and sparse. Returns image count."""
    dense_images = dense / "images"
    dense_sparse = dense / "sparse"

    if not dense_images.exists():
        sys.exit(f"Output validation failed: {dense_images} not found. "
                 f"COLMAP may have crashed — check output above.")

    image_files = list(dense_images.iterdir())
    if not image_files:
        sys.exit(f"Output validation failed: {dense_images} is empty. "
                 f"COLMAP may have crashed — check output above.")

    if not dense_sparse.exists():
        sys.exit(f"Output validation failed: {dense_sparse} not found.")

    return len(image_files)


def build_colmap_cmd(paths: dict) -> list:
    return [
        "colmap", "image_undistorter",
        "--image_path",   str(paths["images"]),
        "--input_path",   str(paths["sparse"]),
        "--output_path",  str(paths["dense"]),
        "--output_type",  "COLMAP",
        "--max_image_size", "1600",
    ]
```

- [ ] **Step 4: Run tests — all 10 should pass**

```
pytest tests/test_04_undistort.py -v
```

Expected: 10 tests pass.

- [ ] **Step 5: Implement `main()` and wire up the CLI**

Append to `scripts/04_undistort.py`:

```python
def main():
    scripts_dir = Path(__file__).parent
    projects_root = scripts_dir.parent / "projects"

    parser = argparse.ArgumentParser(description="COLMAP undistortion for Lichtfield Studio")
    parser.add_argument("project_name",
                        help="Project folder name under projects\\ (e.g. 20260411-house)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Delete existing dense/ output and re-run")
    args = parser.parse_args()

    paths = resolve_paths(projects_root, args.project_name)

    print(f"\nProject    : {args.project_name}")
    print(f"Images in  : {paths['images']}")
    print(f"Sparse in  : {paths['sparse']}")
    print(f"Dense out  : {paths['dense']}")
    print()

    preflight(projects_root, args.project_name, overwrite=args.overwrite)

    if not (paths["dense"]).exists():
        paths["dense"].mkdir(parents=True)

    cmd = build_colmap_cmd(paths)
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"\nCOLMAP exited with code {result.returncode}. Check output above.")

    count = validate_output(paths["dense"])

    print(f"\nDone. Undistorted {count} images -> {paths['dense']}")
    print(f"Next step: open Lichtfield Studio and load {paths['dense']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke-test the CLI help (no COLMAP needed)**

```
python scripts/04_undistort.py --help
```

Expected output includes `project_name` and `--overwrite` in usage.

- [ ] **Step 7: Commit**

```
git add scripts/04_undistort.py tests/test_04_undistort.py
git commit -m "feat: implement 04_undistort.py COLMAP invocation and output validation"
```

---

## Task 3: Update `01-create-project.ps1`

**Files:**
- Modify: `scripts/01-create-project.ps1`

- [ ] **Step 1: Add `dense` to the folder list**

In `scripts/01-create-project.ps1`, replace the `$folders` block and header comment:

```powershell
# Step 1 (setup) -- Create Project
# Creates the standard folder structure for a new Gaussian Splat project.
# Usage: .\01-create-project.ps1 -ProjectName <name>
#
# Creates under projects\<ProjectName>\:
#   footage\          <- drop raw MP4s here before running 01-ffmpeg.ps1
#   frames\           <- extracted frames land here
#   frames\culled\    <- frames culled by 02_cull_frames.py
#   images\           <- kept frames; COLMAP input
#   sparse\0\         <- COLMAP sparse model output
#   dense\            <- undistorted output; Lichtfield Studio input (populated by 04_undistort.py)
#   output\ply\       <- reserved for future use
```

```powershell
$folders = @(
    "footage",
    "frames",
    "frames\culled",
    "images",
    "sparse\0",
    "dense",
    "output\ply"
)
```

- [ ] **Step 2: Update the next-steps message**

Replace the `Write-Host "Done. Next steps:"` block at the bottom of the script:

```powershell
Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  1. Copy raw MP4s into: $ProjectDir\footage\"
Write-Host "  2. Extract frames    : .\scripts\01-ffmpeg.ps1 -Mp4 projects\$ProjectName\footage"
Write-Host "  3. Cull frames       : python scripts\02_cull_frames.py $ProjectName"
Write-Host "  4. Run COLMAP        : python scripts\03_run_colmap.py $ProjectName"
Write-Host "  5. Undistort         : python scripts\04_undistort.py $ProjectName"
Write-Host "  6. Train             : open Lichtfield Studio, load projects\$ProjectName\dense\"
```

- [ ] **Step 3: Verify manually**

```powershell
.\scripts\01-create-project.ps1 -ProjectName test-scaffold-deleteme
```

Expected: prints 7 folders including `dense\`, next-steps shows step 5 as `04_undistort.py` and step 6 as Lichtfield Studio.

Then clean up:

```powershell
Remove-Item -Recurse -Force projects\test-scaffold-deleteme
```

- [ ] **Step 4: Commit**

```
git add scripts/01-create-project.ps1
git commit -m "feat: add dense/ folder to project scaffold, update next-steps for Lichtfield"
```

---

## Task 4: Update CLAUDE.md — Step 4, Step 5, folder structure

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace Step 4 (gsplat training → undistortion)**

Find and replace the entire Step 4 section in `CLAUDE.md`. Replace from `### Step 4: Train Gaussian Splat` through the closing `---` with:

```markdown
### Step 4: COLMAP Undistortion (`04_undistort.py`)
Tool: COLMAP CLI (`image_undistorter`)

**What it does:**
Runs `colmap image_undistorter` to produce undistorted images and an undistorted sparse model
in `projects/<name>/dense/`. This is the folder Lichtfield Studio loads directly.

- `--max_image_size 1600` — required by Lichtfield Studio; larger images are downscaled
- `--output_type COLMAP` — outputs a COLMAP-format sparse model alongside the undistorted images

**Parameters:**
- `project_name` — project folder name under `projects\` (e.g. `20260411-house`)
- `--overwrite` — delete existing `dense/` output and re-run

**Output:**
```
projects/<name>/dense/
    images/     ← undistorted images (Lichtfield input)
    sparse/     ← undistorted sparse model (Lichtfield input)
```

**Example usage (project: 20260411-house):**
```bash
# Standard run
python scripts/04_undistort.py 20260411-house

# Re-run after a failed or partial attempt
python scripts/04_undistort.py 20260411-house --overwrite
```

---

### Step 5: Lichtfield Studio (manual)

**What it does:**
Lichtfield Studio is a Windows GUI application for training and viewing Gaussian Splats.
It takes the `dense/` folder produced by Step 4 as input.

**Steps:**
1. Open Lichtfield Studio
2. Load or drop the folder `projects\<name>\dense\` into the application
3. Train from within Lichtfield Studio

Note: Lichtfield Studio has a CLI — a `05_lichtfield.py` script is a future addition.

---
```

- [ ] **Step 2: Update the folder structure tree**

Find and replace the `## Suggested Project File Structure` section's tree and note. Replace the content from the opening ` ``` ` through the closing `Note:` paragraph:

```markdown
```
C:\code\gaussian-splat\
├── CLAUDE.md                  ← this file
├── scripts\
│   ├── 00-install-prereqs.ps1
│   ├── 01-create-project.ps1
│   ├── 01-ffmpeg.ps1
│   ├── 02_cull_frames.py
│   ├── 03_run_colmap.py
│   └── 04_undistort.py
├── projects\
│   └── house_frontage_01\
│       ├── footage\           ← raw MP4s go here
│       ├── frames\            ← extracted frames (with frames/culled/ subdir)
│       ├── images\            ← culled frames — COLMAP input
│       ├── colmap.db          ← COLMAP database
│       ├── sparse\
│       │   └── 0\             ← sparse model (cameras.bin, images.bin, points3D.bin)
│       └── dense\             ← Lichtfield Studio input (created by 04_undistort.py)
│           ├── images\        ← undistorted images
│           └── sparse\        ← undistorted sparse model
└── requirements.txt
```

`dense/` is populated by `04_undistort.py` (Step 4). Load this folder into Lichtfield Studio to train.
```

- [ ] **Step 3: Verify CLAUDE.md reads correctly**

Open `CLAUDE.md` and visually confirm:
- Step 4 header reads "COLMAP Undistortion (`04_undistort.py`)"
- Step 5 header reads "Lichtfield Studio (manual)"
- Folder tree shows `dense/` with `images/` and `sparse/` children
- The old "there is NO separate `distorted/` folder" note is gone
- No remaining references to `04_train_splat.py` or gsplat in the pipeline steps

- [ ] **Step 4: Commit**

```
git add CLAUDE.md
git commit -m "docs: replace Step 4/5 with undistortion + Lichtfield Studio, update folder structure"
```

---

## Task 5: Run full test suite

- [ ] **Step 1: Run all tests**

```
pytest tests/ -v
```

Expected: all tests pass. No failures or errors.

- [ ] **Step 2: Final commit if any fixups were needed**

If any tests required fixes during Task 5, commit them:

```
git add -p
git commit -m "fix: test suite cleanup after integration"
```
