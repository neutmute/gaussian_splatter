# Gaussian Splat Pipeline — Project Context & Script Briefing

> This file provides context for Claude Code to build reusable scripts for processing
> drone footage into Gaussian Splat scenes using COLMAP + 3D Gaussian Splatting.
> Place this file in your project root: `C:\code\gaussian-splat\CLAUDE.md`

---

## Project Goal

Build a set of reusable, well-documented Python/shell scripts that automate the full
pipeline from raw drone MP4 footage through to a viewable Gaussian Splat `.ply` file.
Scripts should be modular — each step runnable independently, with clear inputs/outputs
so the user can re-run individual steps without repeating the whole pipeline.

---

## Target Hardware & Environment

- **OS:** Windows (primary), Linux (secondary)
- **GPU:** NVIDIA (RTX 3060 minimum, 3080+ ideal), 8GB+ VRAM
- **CUDA:** 11.8
- **Python:** 3.9–3.11
- **Tools required:** FFmpeg, COLMAP, Git
- **Repo:** github.com/graphdeco-inria/gaussian-splatting

---

## Capture Context

Scripts should be optimised for footage captured with these specs:

### Camera: DJI Mini Pro 4
- Resolution: 4K 30fps
- Color profile: D-Log M
- Shutter: 1/60s (fixed, 2× rule)
- ISO: 100 (fixed, sunny conditions)
- White balance: Manual fixed — Cloudy preset (~6200K)
- EIS: OFF (electronic stabilisation must be disabled)
- ND filter: ND16 for sunny morning conditions
- Gimbal: Standard mode

### Shooting Scenarios
1. **House frontage** — simple arc pass at 3–5m + lower pass at 1.5–2m
2. **Garden** — three passes: low through (1–2m), mid orbit (3–5m), high grid (8–15m)
3. **Multiple clips** — different passes extracted into same COLMAP input folder

### Known Capture Issues to Handle
- Parked cars / moving pedestrians between clips → ghost geometry
- Reflective windows → smearing artefacts (known limitation, document don't fix)
- Leaf movement in wind → degrades matching (warn user if many frames are flagged)
- Repetitive facade features → potential COLMAP misregistration

---

## Full Pipeline — Steps & Commands

### Step 1: Frame Extraction (`01_extract_frames.py`)
Tool: FFmpeg

```bash
ffmpeg -i input.mp4 -vf fps=2 frames/frame_%04d.jpg -q:v 2
```

**Parameters to expose:**
- Input MP4 path (or folder of MPs for multi-clip)
- Output frames folder
- FPS rate (default 2, suggest 3–4 for fast movement, 1 for slow high passes)
- JPEG quality (default 2, range 1–5)
- Option to process multiple MP4s into one output folder

**Logic to include:**
- Auto-calculate expected frame count and warn if >1000 (suggest lowering fps)
- Support glob input: `*.mp4` in a folder → all extracted to same output dir
- Print summary: X clips processed, Y total frames extracted

---

### Step 2: Frame QC / Cull (`02_cull_frames.py`)
Tool: OpenCV (blur detection via Laplacian variance)

**What it does:**
- Scans extracted frames and scores each for sharpness
- Flags and optionally deletes frames below a blur threshold
- Flags near-duplicate frames (too similar to previous = redundant)
- Produces a report: total frames, flagged frames, recommended culls

**Parameters to expose:**
- Input frames folder
- Blur threshold (default 100 Laplacian variance — tune to footage)
- Similarity threshold for deduplication
- `--dry-run` flag — report only, don't delete
- `--auto-cull` flag — delete flagged frames automatically

**Output:**
- `cull_report.txt` listing flagged files with scores
- Optionally moves culled frames to `frames/culled/` subfolder rather than deleting

---

### Step 3: COLMAP SfM (`03_run_colmap.py`)
Tool: COLMAP CLI

**What it does:**
Runs the full COLMAP pipeline headlessly via CLI (no GUI required):
1. Feature extraction
2. Sequential matching
3. Sparse reconstruction
4. Image undistortion

```bash
# Feature extraction
colmap feature_extractor \
  --database_path project/database.db \
  --image_path project/input \
  --ImageReader.camera_model OPENCV \
  --ImageReader.single_camera 1

# Sequential matching
colmap sequential_matcher \
  --database_path project/database.db \
  --SequentialMatching.overlap 15

# Sparse reconstruction
colmap mapper \
  --database_path project/database.db \
  --image_path project/input \
  --output_path project/distorted/sparse

# Undistortion
colmap image_undistorter \
  --image_path project/input \
  --input_path project/distorted/sparse/0 \
  --output_path project/ \
  --output_type COLMAP
```

**Parameters to expose:**
- Project folder path
- Sequential overlap (default 15, increase to 20–30 for tricky footage)
- `--exhaustive` flag — switch to exhaustive matcher (slower, more thorough)
- COLMAP binary path (for non-standard installs)

**Output validation:**
- After mapper, read `images.txt` and report: X of Y images registered (%)
- Warn if <70% registered — suggest exhaustive matching or re-culling
- Warn if multiple sparse models produced (fragmentation)

---

### Step 4: Train Gaussian Splat (`04_train_splat.py`)
Tool: gaussian-splatting repo (`train.py`)

```bash
python train.py \
  -s /path/to/project \
  --iterations 30000 \
  --model_path /path/to/output
```

**Parameters to expose:**
- Project path (COLMAP output)
- Output path
- Iterations (default 30000, quick-test option 10000)
- Downsample factor: `--images images_2` / `images_4` / `images_8` for low VRAM
- gaussian-splatting repo path (if not in same directory)

**Logic to include:**
- Auto-detect available VRAM and suggest downsample factor if <10GB
- Monitor training output and warn if loss stalls above 0.1 early
- Print final loss value and output `.ply` path on completion

---

### Step 5: Pipeline Runner (`run_pipeline.py`)
Master script that chains steps 1–4 with a single config file.

**Config file (`pipeline_config.yaml`):**
```yaml
project_name: house_frontage_01
input_clips:
  - footage/pass_high.mp4
  - footage/pass_low.mp4
output_dir: output/

extraction:
  fps: 2
  quality: 2

colmap:
  matcher: sequential
  overlap: 15
  camera_model: OPENCV

training:
  iterations: 30000
  downsample: auto   # auto, 1, 2, 4, 8
```

**Behaviour:**
- Runs each step in sequence, logging to `pipeline.log`
- Skips steps where output already exists (resumable)
- `--from-step 3` flag to restart from a specific step
- Prints elapsed time per step and total on completion

---

## Suggested Project File Structure

```
C:\code\gaussian-splat\
├── CLAUDE.md                  ← this file
├── run_pipeline.py            ← master runner
├── pipeline_config.yaml       ← user config
├── scripts\
│   ├── 01_extract_frames.py
│   ├── 02_cull_frames.py
│   ├── 03_run_colmap.py
│   └── 04_train_splat.py
├── projects\
│   └── house_frontage_01\
│       ├── footage\           ← raw MP4s go here
│       ├── frames\            ← extracted frames
│       ├── input\             ← culled frames for COLMAP
│       ├── distorted\
│       │   └── sparse\
│       ├── sparse\
│       ├── images\            ← undistorted images
│       └── output\            ← splat .ply output
└── requirements.txt
```

---

## Dependencies (`requirements.txt`)

```
opencv-python
numpy
PyYAML
tqdm
Pillow
```

External tools (must be installed separately and on PATH):
- `ffmpeg`
- `colmap`
- gaussian-splatting repo (cloned separately, path set in config)

---

## Known Gotchas & Troubleshooting Notes

| Issue | Cause | Script Handling |
|---|---|---|
| COLMAP registers <70% images | Blur, low overlap | Warn user, suggest exhaustive matcher |
| Multiple sparse models | Fragmented reconstruction | Detect in output, warn, suggest more overlap in capture |
| VRAM OOM during training | GPU too small | Auto-detect and suggest downsample flag |
| Training loss plateaus >0.1 | Bad camera poses | Warn after 5000 iterations if loss not dropping |
| FFmpeg not found | Not on PATH | Clear error message with install instructions |
| Frames folder already exists | Re-run scenario | Ask user to confirm overwrite or skip |

---

## Viewing Output

- **Browser (easiest):** supersplat.playcanvas.com — drag `.ply` file in
- **Local viewer:** `python viewer.py` from gaussian-splatting repo
- Output `.ply` location: `projects/[name]/output/point_cloud/iteration_30000/point_cloud.ply`

---

## Session Notes

- Primary capture hardware: DJI Mini Pro 4
- Secondary scenario discussed: GoPro 9 (use linear mode, EIS off, less ideal)
- Garden shoots require bridging altitude passes to avoid COLMAP fragmentation
- House frontage recommended as first/test project — simpler, more reliable
- Shoot in calm conditions, overcast preferred, early morning minimises traffic/people
- D-Log M footage should be colour-graded before visual review but raw frames
  (ungraded) are fine for COLMAP — it works on luminance/feature geometry not colour
