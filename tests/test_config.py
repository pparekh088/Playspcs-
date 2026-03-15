"""Tests for config loading and validation."""

import pytest
import yaml
from pathlib import Path

from playspec.config import PlaySpecConfig, ExecutionProfile, RepairPolicy, load_config


@pytest.fixture
def config_dir(tmp_path):
    """Create a .playspec dir with a valid config."""
    ps = tmp_path / ".playspec"
    ps.mkdir()
    config = {
        "test_dir": "tests/e2e",
        "page_objects_dir": "tests/e2e/pages",
        "fixtures_dir": "tests/e2e/fixtures",
        "naming_convention": "kebab-case",
        "max_retries": 3,
        "profiles": {
            "local-dev": {
                "base_url": "http://localhost:3000",
                "browsers": ["chromium"],
                "parallelism": 2,
                "headed": True,
                "repair_policy": "propose",
            },
            "pr-ci": {
                "base_url": "https://preview.example.com",
                "browsers": ["chromium"],
                "parallelism": 4,
                "headed": False,
                "repair_policy": "never",
            },
        },
        "audit": {"enabled": True, "output_dir": ".playspec/audits", "retention_days": 90},
    }
    (ps / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")
    return tmp_path


class TestPlaySpecConfig:
    def test_defaults(self):
        cfg = PlaySpecConfig()
        assert cfg.test_dir == "tests/e2e"
        assert cfg.max_retries == 3
        assert cfg.audit.enabled is True

    def test_invalid_naming(self):
        with pytest.raises(ValueError, match="naming_convention"):
            PlaySpecConfig(naming_convention="SCREAMING")

    def test_get_profile_named(self):
        cfg = PlaySpecConfig(profiles={
            "local-dev": ExecutionProfile(base_url="http://localhost:3000"),
            "nightly": ExecutionProfile(base_url="https://staging.example.com"),
        })
        profile = cfg.get_profile("nightly")
        assert profile.base_url == "https://staging.example.com"

    def test_get_profile_fallback(self):
        cfg = PlaySpecConfig(profiles={
            "local-dev": ExecutionProfile(base_url="http://localhost:3000"),
        })
        profile = cfg.get_profile("nonexistent")
        assert profile.base_url == "http://localhost:3000"

    def test_get_profile_empty(self):
        cfg = PlaySpecConfig()
        profile = cfg.get_profile(None)
        assert isinstance(profile, ExecutionProfile)


class TestLoadConfig:
    def test_load_valid(self, config_dir):
        path = config_dir / ".playspec" / "config.yaml"
        cfg = load_config(path)
        assert cfg.test_dir == "tests/e2e"
        assert "local-dev" in cfg.profiles
        assert cfg.profiles["pr-ci"].repair_policy == RepairPolicy.NEVER

    def test_load_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="playspec init"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        ps = tmp_path / ".playspec"
        ps.mkdir()
        (ps / "config.yaml").write_text("naming_convention: INVALID_VALUE", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid config"):
            load_config(ps / "config.yaml")
