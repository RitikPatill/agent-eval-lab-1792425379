"""Smoke-test: make demo prerequisites are all present."""
import os
from pathlib import Path


def test_docs_demo_gif_exists():
    assert Path("docs/demo.gif").exists(), "docs/demo.gif placeholder missing"


def test_docs_screenshot_exists():
    assert Path("docs/screenshot.png").exists(), "docs/screenshot.png placeholder missing"


def test_record_demo_sh_exists_and_executable():
    p = Path("record_demo.sh")
    assert p.exists()
    assert os.access(p, os.X_OK), "record_demo.sh is not executable"


def test_makefile_has_record_target():
    makefile = Path("Makefile").read_text()
    assert "record:" in makefile
    assert "ANTHROPIC_API_KEY" in makefile
