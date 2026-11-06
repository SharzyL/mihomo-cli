"""Configuration: ~/.config/mihomoctl.toml, overridden by env vars, overridden by CLI flags.

Example config:

    [controller]
    url = "http://127.0.0.1:9090"
    secret = "..."

    [proxies]
    test-url = "https://www.gstatic.com/generate_204"
    test-timeout = 5000                   # ms
    close-connections-on-switch = false
"""

import os
from pathlib import Path

import msgspec


class ControllerConfig(msgspec.Struct, kw_only=True, forbid_unknown_fields=True, rename='kebab'):
    url: str = 'http://127.0.0.1:9090'
    secret: str | None = None


class ProxiesConfig(msgspec.Struct, kw_only=True, forbid_unknown_fields=True, rename='kebab'):
    test_url: str = 'https://www.gstatic.com/generate_204'
    test_timeout: int = 5000
    close_connections_on_switch: bool = False


class Config(msgspec.Struct, kw_only=True, forbid_unknown_fields=True):
    controller: ControllerConfig = msgspec.field(default_factory=ControllerConfig)
    proxies: ProxiesConfig = msgspec.field(default_factory=ProxiesConfig)


def default_config_path() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / 'mihomoctl.toml'


class ConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> Config:
    explicit = path is not None
    path = path or default_config_path()
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        if explicit:
            raise ConfigError(f'config file not found: {path}') from None
        config = Config()
    else:
        try:
            config = msgspec.toml.decode(data, type=Config)
        except (msgspec.DecodeError, msgspec.ValidationError) as e:
            raise ConfigError(f'{path}: {e}') from e

    if url := os.environ.get('MIHOMO_URL'):
        config.controller.url = url
    if secret := os.environ.get('MIHOMO_SECRET'):
        config.controller.secret = secret
    return config
