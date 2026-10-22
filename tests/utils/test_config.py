from pathlib import Path

import pytest

from ds_project.utils.config import CONF_ENV_VAR, find_config_file, load_config

ROOT = Path(__file__).resolve().parents[2]


def test_load_config_resolves_paths_against_project_root() -> None:
    config = load_config(ROOT / "conf" / "base.yaml")
    assert config.paths.raw == ROOT / "data" / "01_raw"
    assert config.paths.reporting == ROOT / "data" / "08_reporting"
    assert config.project.random_seed == 42


def test_find_config_file_walks_up_from_subdirectory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONF_ENV_VAR, raising=False)
    assert find_config_file(ROOT / "notebooks" / "1-data") == ROOT / "conf" / "base.yaml"


def test_find_config_file_uses_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf = tmp_path / "custom.yaml"
    conf.write_text("x: 1")
    monkeypatch.setenv(CONF_ENV_VAR, str(conf))
    assert find_config_file() == conf


def test_find_config_file_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONF_ENV_VAR, str(tmp_path / "missing.yaml"))
    with pytest.raises(FileNotFoundError):
        find_config_file()
    monkeypatch.delenv(CONF_ENV_VAR)
    with pytest.raises(FileNotFoundError):
        find_config_file(tmp_path)


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "conf").mkdir()
    conf = tmp_path / "conf" / "base.yaml"
    conf.write_text((ROOT / "conf" / "base.yaml").read_text() + "\ntypo_section: {}\n")
    with pytest.raises(ValueError, match="typo_section"):
        load_config(conf)
