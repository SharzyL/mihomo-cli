import argparse
import sys
from pathlib import Path

from .config import ConfigError, default_config_path, load_config


def main() -> None:
    parser = argparse.ArgumentParser(prog='mihomoctl', description='TUI controller for mihomo')
    parser.add_argument('-c', '--config', type=Path, help=f'config file (default: {default_config_path()})')
    parser.add_argument('-u', '--url', help='external controller URL, e.g. http://127.0.0.1:9090 (env: MIHOMO_URL)')
    parser.add_argument('-s', '--secret', help='external controller secret (env: MIHOMO_SECRET)')
    parser.add_argument(
        '--close-connections',
        action=argparse.BooleanOptionalAction,
        default=None,
        help='close connections through a group after switching it',
    )
    args = parser.parse_args()
    config_path: Path | None = args.config
    url: str | None = args.url
    secret: str | None = args.secret
    close_connections: bool | None = args.close_connections

    try:
        config = load_config(config_path)
    except ConfigError as e:
        sys.exit(f'mihomoctl: {e}')
    if url:
        config.controller.url = url
    if secret:
        config.controller.secret = secret
    if close_connections is not None:
        config.proxies.close_connections_on_switch = close_connections

    # Import lazily so `--help` stays fast.
    from .app import MihomoApp

    app = MihomoApp(config)
    app.run()
    sys.exit(app.return_code or 0)
