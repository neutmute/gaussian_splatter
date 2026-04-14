# Design: Undistortion Step + Lichtfield Studio Integration

**Date:** 2026-04-14
**Status:** Approved

---

## Overview

Replace the gsplat training step (Step 4) with a COLMAP undistortion step (`04_undistort.py`) that prepares a `dense/` folder as input for Lichtfield Studio. Lichtfield Studio is used as a GUI application for training and viewing Gaussian Splats — the user loads the `dense/` folder directly.

---

## Pipeline Before → After

| Step | Before | After |
|------|--------|-------|
| 0 | Install prereqs | (unchanged) |
| 0.5 | Create project | (unchanged) |
| 1 | Extract frames | (unchanged) |
| 2 | Cull frames | (unchanged) |
| 3 | COLMAP SfM | (unchanged) |
| 4 | gsplat training (`04_train_splat.py`) | **COLMAP undistortion (`04_undistort.py`)** |
| 5 | Pipeline runner | **Lichtfield Studio (manual GUI step)** |

---

## New Script: `scripts/04_undistort.py`

### Interface

```
python scripts/04_undistort.py <project_name> [--overwrite]
```

- `project_name` — positional, e.g. `20260411-house`. Resolves paths via standard project structure.
- `--overwrite` — delete existing `dense/` and re-run. Without this flag, exits with an error if `dense/` already contains output.

### Paths

| Role | Path |
|------|------|
| Input images | `projects/<name>/images/` |
| Input sparse model | `projects/<name>/sparse/0/` |
| Output folder | `projects/<name>/dense/` |

### COLMAP command issued

```bash
colmap image_undistorter \
  --image_path projects/<name>/images \
  --input_path projects/<name>/sparse/0 \
  --output_path projects/<name>/dense \
  --output_type COLMAP \
  --max_image_size 1600
```

### Output validation

After the command completes, the script checks:
- `dense/images/` exists and contains at least one file
- `dense/sparse/` exists

Prints image count on success. Exits with an error message if validation fails.

### Completion message

On success, prints:
```
Done. Undistorted N images → projects/<name>/dense/
Next step: open Lichtfield Studio and load projects\<name>\dense\
```

---

## CLAUDE.md Changes

### Step 4 (new): COLMAP Undistortion

Replaces the old gsplat training step. Documents:
- What it does (undistorts images for Lichtfield)
- Parameters (`project_name`, `--overwrite`)
- The `--max_image_size 1600` rationale (Lichtfield requirement)
- Example usage

### Step 5 (new): Lichtfield Studio

Replaces the old pipeline runner step. Documents:
- Open Lichtfield Studio
- Load / drop `projects/<name>/dense/` folder
- Train from there
- Note that Lichtfield has a CLI (reserved for a future script)

### Folder structure note

The existing note — *"there is NO separate `distorted/` folder and NO `image_undistorter` step"* — is removed. Replaced with a note that `dense/` is the Lichtfield Studio input folder, created by Step 4.

---

## `01-create-project.ps1` Changes

Add `dense` to the list of pre-created folders:

```powershell
$folders = @(
    "footage",
    "frames",
    "frames\culled",
    "images",
    "sparse\0",
    "dense",          # ← new: Lichtfield Studio input, populated by 04_undistort.py
    "output\ply"
)
```

`dense/images/` and `dense/sparse/` are NOT pre-created — COLMAP generates them at runtime.

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/04_undistort.py` | New file |
| `scripts/01-create-project.ps1` | Add `dense/` to folder list |
| `CLAUDE.md` | Step 4 → undistortion, Step 5 → Lichtfield Studio, folder structure updated |

## Files Removed from Pipeline

`scripts/04_train_splat.py` — retained on disk but removed from CLAUDE.md pipeline documentation.
