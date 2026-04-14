---
title: CLAUDE.md Cleanup — Remove gsplat, Add DJI Avata 2
date: 2026-04-15
status: approved
---

# CLAUDE.md Cleanup Design

## Scope

Surgical edits only (Option A). No structural changes, no stale-ref cleanup beyond what
is listed. Six targeted changes to CLAUDE.md.

---

## Changes

### 1. Project Goal
Remove the word "gsplat" from the goal statement. The pipeline outputs a viewable `.ply`
file via Lichtfield Studio — no gsplat involvement.

### 2. Target Hardware — Training repo line
Delete the line:
> Training repo: github.com/nerfstudio-project/gsplat (NOT the abandoned graphdeco-inria/gaussian-splatting)

### 3. Step 0 description — slim to PATH/deps only
Replace the current Step 0 body with a short description covering only:
- Checks PATH for `ffmpeg` and `colmap`
- Installs Python dependencies from `requirements.txt`

Remove from the "Requires" section:
- CUDA Toolkit entry
- Microsoft Build Tools for VS 2022 entry

Keep the PowerShell example usage block unchanged.

### 4. Capture Context — DJI Avata 2 secondary camera
Add a new subsection after the existing "### Camera: DJI Mini Pro 4" block:

```
### Camera: DJI Avata 2 (Secondary)
- Lens: fisheye (~155° FOV)
- EIS: OFF (must be disabled)
- COLMAP camera model: `OPENCV_FISHEYE` (use `--camera-model OPENCV_FISHEYE` in Step 3)
- All other settings (fps, color profile, shutter) follow the same guidelines as the Mini 4 Pro
```

### 5. Dependencies — external tools list
Remove from the external tools list:
- `gsplat` repo entry
- `Microsoft Build Tools for VS 2022` entry

### 6. Known Gotchas table
Remove these three rows:
- "VRAM OOM during training"
- "gsplat build fails"
- "Blackwell GPU not recognised by PyTorch"

---

## Out of Scope
- Blackwell/CUDA 12.8 references in Target Hardware — left as-is
- Viewing Output stale gsplat `.ply` path — left as-is
- Session Notes — left as-is
- No structural or prose changes beyond the six items above
