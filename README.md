# mihomoctl

A TUI for controlling [mihomo](https://github.com/MetaCubeX/mihomo) through its external controller (RESTful API).

Currently it supports browsing proxy groups, switching proxies, and running latency tests.

## Usage

```console
$ mihomoctl                       # uses ~/.config/mihomoctl.toml
$ mihomoctl -u http://127.0.0.1:9090 -s <secret>
```

Configuration (`$XDG_CONFIG_HOME/mihomoctl.toml`, all keys optional).
The env vars `MIHOMO_URL` / `MIHOMO_SECRET` override the file, and CLI flags override both.

```toml
[controller]
url = "http://127.0.0.1:9090"
secret = "..."

[proxies]
test-url = "https://www.gstatic.com/generate_204"  # used when a group has no testUrl
test-timeout = 5000                                # ms
close-connections-on-switch = false                # close connections through a group after switching it
```

### Keys

| Key | Action |
| --- | --- |
| `j` / `k`, `↑` / `↓`, `g` / `G`, `^d` / `^u` | move |
| `h` / `l`, `←` / `→`, `Tab` | switch between the groups and proxies panes |
| `Enter` | on a group: jump to its proxies; on a proxy: select it |
| `t` | latency-test the current group |
| `T` | latency-test the proxy under the cursor |
| `u` | unpin a URLTest/Fallback group (selecting a proxy in one pins it) |
| `s` | cycle sort: config order / delay / name |
| `/`, `Esc` | filter proxies, clear filter |
| `r` | refresh |
| `q` | quit |

## Develop Guide

To run the package
```console
$ uv run mihomoctl
```

To type check and test
```console
$ basedpyright
$ pytest
$ nix flake check
```

To format
```console
$ ruff format
$ nix fmt
```
