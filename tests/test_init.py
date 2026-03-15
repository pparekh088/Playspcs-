"""Tests for playspec init command."""

import pytest
from pathlib import Path

from playspec.init_cmd import run_init


class TestInit:
    def test_creates_config(self, tmp_path):
        run_init(tmp_path)
        assert (tmp_path / ".playspec" / "config.yaml").is_file()
        assert (tmp_path / ".playspec" / "regression-manifest.yaml").is_file()
        assert (tmp_path / ".playspec" / "audits").is_dir()
        assert (tmp_path / ".playspec" / "runs").is_dir()

    def test_idempotent(self, tmp_path):
        run_init(tmp_path)
        config_content = (tmp_path / ".playspec" / "config.yaml").read_text()
        run_init(tmp_path)
        assert (tmp_path / ".playspec" / "config.yaml").read_text() == config_content

    def test_detects_test_dir(self, tmp_path):
        (tmp_path / "tests" / "e2e").mkdir(parents=True)
        run_init(tmp_path)
        import yaml
        config = yaml.safe_load((tmp_path / ".playspec" / "config.yaml").read_text())
        assert config["test_dir"] == "tests/e2e"
