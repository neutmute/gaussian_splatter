# CLAUDE.md Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove gsplat and MS Build Tools references from CLAUDE.md and add DJI Avata 2 as a secondary camera in the Capture Context section.

**Architecture:** Six surgical edits to `CLAUDE.md`. No code changes. No tests — verification is a manual diff review after each edit.

**Tech Stack:** Edit tool only. All edits to `CLAUDE.md` at `C:\CodeMine\gaussian_splatter\CLAUDE.md`.

---

### Task 1: Fix the header blurb and Project Goal

**Files:**
- Modify: `CLAUDE.md:4` (header blurb)
- Modify: `CLAUDE.md:14` (Project Goal body)

- [ ] **Step 1: Edit the header blurb (line 4)**

Remove "using COLMAP + gsplat" from the opening blockquote. Replace:

```
> drone footage into Gaussian Splat scenes using COLMAP + gsplat.
```

With:

```
> drone footage into Gaussian Splat scenes using COLMAP + Lichtfield Studio.
```

- [ ] **Step 2: Edit the Project Goal body (line 14)**

The goal currently says "a viewable Gaussian Splat `.ply` file" — this is fine to keep. No change needed to the body prose. Confirm by reading lines 11–16 and verifying no other gsplat mention exists there.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove gsplat from header blurb"
```

---

### Task 2: Clean up Target Hardware section

**Files:**
- Modify: `CLAUDE.md:25-27`

- [ ] **Step 1: Edit Python version note (line 25)**

Replace:
```
- **Python:** 3.10 recommended (gsplat tested on 3.10)
```
With:
```
- **Python:** 3.10 recommended
```

- [ ] **Step 2: Edit Tools required (line 26)**

Replace:
```
- **Tools required:** FFmpeg, COLMAP v3.11+, Git, Microsoft Build Tools for VS 2022
```
With:
```
- **Tools required:** FFmpeg, COLMAP v3.11+, Git
```

- [ ] **Step 3: Remove Training repo line (line 27)**

Delete this line entirely:
```
- **Training repo:** github.com/nerfstudio-project/gsplat (NOT the abandoned graphdeco-inria/gaussian-splatting)
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove gsplat and MS Build Tools from Target Hardware"
```

---

### Task 3: Slim down Step 0 description

**Files:**
- Modify: `CLAUDE.md:63-87`

- [ ] **Step 1: Replace "What it does" bullet list**

Replace the entire "What it does" block:
```
**What it does:**
- Auto-detects GPU compute capability and installs the right PyTorch CUDA build
  - Blackwell (sm_120, RTX 50xx) → PyTorch + CUDA 12.8
  - Ada/Hopper (sm_89+) → PyTorch + CUDA 12.1
  - Older GPUs → PyTorch + CUDA 11.8
- Installs pipeline script dependencies from `requirements.txt`
- Clones gsplat repo (if not present), sets `DISTUTILS_USE_SDK=1`, builds it with `pip install .`
- Installs gsplat example dependencies
- Applies the pycolmap Windows binary parsing fix
- Checks PATH for required external tools (ffmpeg, colmap) and GPU via nvidia-smi
```

With:
```
**What it does:**
- Installs pipeline script dependencies from `requirements.txt`
- Checks PATH for required external tools (ffmpeg, colmap)
```

- [ ] **Step 2: Replace the "Requires" block and example usage**

Replace:
```
**Run once before using any pipeline scripts. Requires:**
- CUDA Toolkit matching your GPU (12.8 for Blackwell) — https://developer.nvidia.com/cuda-downloads
- Microsoft Build Tools for VS 2022 with "Desktop development with C++" workload
  — https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022
- Run from a "Developer Command Prompt for VS 2022" (or vcvars64.bat must have been called)

**Example usage:**
```powershell
# Default gsplat path C:\apps\gsplat
.\scripts\00-install-prereqs.ps1

# Custom gsplat path
.\scripts\00-install-prereqs.ps1 -GsplatPath C:\apps\gsplat
```
```

With:
```
**Run once before using any pipeline scripts.**

**Example usage:**
```powershell
.\scripts\00-install-prereqs.ps1
```
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: slim Step 0 to PATH/deps check only, remove gsplat build steps"
```

---

### Task 4: Add DJI Avata 2 camera subsection

**Files:**
- Modify: `CLAUDE.md:43-44` (insert after the Mini 4 Pro camera block, before Shooting Scenarios)

- [ ] **Step 1: Insert Avata 2 subsection**

Insert the following block after the Mini 4 Pro block (after `- Gimbal: Standard mode`, before `### Shooting Scenarios`):

```

### Camera: DJI Avata 2 (Secondary)
- Lens: fisheye (~155° FOV)
- EIS: OFF (must be disabled)
- COLMAP camera model: `OPENCV_FISHEYE` — use `--camera-model OPENCV_FISHEYE` in Step 3
- All other settings (fps, color profile, shutter, ND filter) follow the same guidelines as the Mini 4 Pro
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add DJI Avata 2 fisheye camera as secondary option in Capture Context"
```

---

### Task 5: Clean up Dependencies section

**Files:**
- Modify: `CLAUDE.md:342-343`

- [ ] **Step 1: Remove gsplat repo entry (line 342)**

Delete this line:
```
- `gsplat` repo — cloned to disk, path passed via --gsplat flag or pipeline_config.yaml
```

- [ ] **Step 2: Remove MS Build Tools entry (line 343)**

Delete this line:
```
- Microsoft Build Tools for VS 2022 — required to compile gsplat CUDA kernels
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove gsplat and MS Build Tools from Dependencies"
```

---

### Task 6: Remove gsplat rows from Known Gotchas table

**Files:**
- Modify: `CLAUDE.md:353,357-358`

- [ ] **Step 1: Remove VRAM OOM row (line 353)**

Delete this table row:
```
| VRAM OOM during training | GPU too small | Auto-detect and suggest higher `--data-factor` |
```

- [ ] **Step 2: Remove gsplat build fails row (line 357)**

Delete this table row:
```
| gsplat build fails | DISTUTILS_USE_SDK not set, or wrong CUDA toolkit | Script sets env var; check nvcc version matches PyTorch CUDA |
```

- [ ] **Step 3: Remove Blackwell GPU row (line 358)**

Delete this table row:
```
| Blackwell GPU not recognised by PyTorch | Wrong PyTorch build (needs cu128) | prereqs script auto-detects sm_120 and installs cu128 build |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: remove gsplat-specific rows from Known Gotchas table"
```
