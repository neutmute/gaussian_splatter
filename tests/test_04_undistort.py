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
    with pytest.raises(SystemExit):
        undistort.preflight(tmp_path / "projects", "test-project")


def test_preflight_fails_when_sparse_missing(tmp_path):
    proj = tmp_path / "projects" / "test-project"
    (proj / "images").mkdir(parents=True)
    with pytest.raises(SystemExit):
        undistort.preflight(tmp_path / "projects", "test-project")


def test_preflight_fails_when_dense_has_content_and_no_overwrite(project):
    root, proj = project
    (proj / "dense" / "images").mkdir(parents=True)
    (proj / "dense" / "images" / "f.jpg").write_bytes(b"")
    with pytest.raises(SystemExit):
        undistort.preflight(root / "projects", "test-project", overwrite=False)


def test_preflight_clears_and_recreates_dense_when_overwrite(project):
    root, proj = project
    # Simulate a prior partial run: dense/ exists with images inside
    (proj / "dense").mkdir()
    (proj / "dense" / "images").mkdir()
    (proj / "dense" / "images" / "f.jpg").write_bytes(b"")
    undistort.preflight(root / "projects", "test-project", overwrite=True)
    assert (proj / "dense").exists()            # directory was recreated
    assert not any((proj / "dense").iterdir())  # and is empty


def test_preflight_passes_when_dense_images_exists_but_empty(project):
    root, proj = project
    # Simulate partial run: dense/images/ exists but is empty
    (proj / "dense").mkdir()
    (proj / "dense" / "images").mkdir()
    # Should not raise — treated as a clean slate
    undistort.preflight(root / "projects", "test-project", overwrite=False)
    assert (proj / "dense").exists()
