from pathlib import Path

import pytest

from mihomoctl.config import ConfigError, load_config


def test_defaults_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    monkeypatch.delenv('MIHOMO_URL', raising=False)
    monkeypatch.delenv('MIHOMO_SECRET', raising=False)
    config = load_config()
    assert config.controller.url == 'http://127.0.0.1:9090'
    assert config.controller.secret is None
    assert config.proxies.close_connections_on_switch is False


def test_file_and_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / 'c.toml'
    path.write_text(
        '[controller]\nurl = "http://a:1"\nsecret = "s"\n[proxies]\nclose-connections-on-switch = true\ntest-timeout = 9\n'
    )
    monkeypatch.setenv('MIHOMO_SECRET', 'from-env')
    monkeypatch.delenv('MIHOMO_URL', raising=False)
    config = load_config(path)
    assert config.controller.url == 'http://a:1'
    assert config.controller.secret == 'from-env'
    assert config.proxies.close_connections_on_switch is True
    assert config.proxies.test_timeout == 9


def test_invalid(tmp_path: Path) -> None:
    path = tmp_path / 'c.toml'
    path.write_text('[controller]\nadress = "typo"\n')
    with pytest.raises(ConfigError, match='adress'):
        load_config(path)
    with pytest.raises(ConfigError, match='not found'):
        load_config(tmp_path / 'missing.toml')
