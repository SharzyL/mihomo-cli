"""In-memory fake of the mihomo controller endpoints we use."""

import json
from typing import Any
from urllib.parse import unquote

import httpx

from mihomoctl.api import MihomoClient


def node(name: str, type: str = 'Trojan', delay: int | None = None, **kw: Any) -> dict[str, Any]:
    history = [{'time': '2026-01-01T00:00:00Z', 'delay': delay}] if delay is not None else []
    return {'name': name, 'type': type, 'udp': True, 'history': history, 'extra': {}, **kw}


def group(name: str, members: list[str], now: str, type: str = 'Selector', **kw: Any) -> dict[str, Any]:
    return node(name, type, all=members, now=now) | {'hidden': False, 'testUrl': ''} | kw


class FakeMihomo:
    def __init__(self) -> None:
        self.proxies: dict[str, dict[str, Any]] = {
            'DIRECT': node('DIRECT', 'Direct'),
            'HK 01': node('HK 01', delay=120),
            'JP/02 🇯🇵': node('JP/02 🇯🇵', delay=0),
            'US 03': node('US 03', delay=640),
            'Auto': group('Auto', ['HK 01', 'US 03'], 'HK 01', type='URLTest', fixed=''),
            'Proxy': group('Proxy', ['Auto', 'HK 01', 'JP/02 🇯🇵', 'US 03', 'DIRECT'], 'Auto'),
            'Hidden': group('Hidden', ['DIRECT'], 'DIRECT', hidden=True),
            'GLOBAL': group('GLOBAL', ['DIRECT', 'HK 01', 'Proxy', 'Auto', 'Hidden'], 'Proxy'),
        }
        self.providers: dict[str, Any] = {
            'default': {'name': 'default', 'type': 'Proxy', 'vehicleType': 'Compatible', 'proxies': []},
            'sub': {
                'name': 'sub',
                'type': 'Proxy',
                'vehicleType': 'HTTP',
                'proxies': [node('SG 04', delay=80, **{'provider-name': 'sub'})],
            },
        }
        self.proxies['Proxy']['all'].append('SG 04')
        self.connections: list[dict[str, Any]] = [
            {'id': 'c1', 'chains': ['HK 01', 'Proxy']},
            {'id': 'c2', 'chains': ['US 03', 'Proxy']},
            {'id': 'c3', 'chains': ['DIRECT']},
        ]
        self.requests: list[tuple[str, str]] = []

    def client(self, secret: str | None = 'sekrit') -> MihomoClient:
        return MihomoClient('http://mihomo.test', secret, transport=httpx.MockTransport(self.handle))

    def handle(self, req: httpx.Request) -> httpx.Response:
        if req.headers.get('authorization') != 'Bearer sekrit':
            return httpx.Response(401, json={'message': 'Unauthorized'})
        # raw_path keeps %2F intact, mirroring how chi routes escaped segments
        path = req.url.raw_path.decode().split('?')[0]
        parts = [unquote(p) for p in path.strip('/').split('/')]
        self.requests.append((req.method, '/'.join(parts)))
        match req.method, parts:
            case 'GET', ['version']:
                return httpx.Response(200, json={'meta': True, 'version': 'test'})
            case 'GET', ['proxies']:
                return httpx.Response(200, json={'proxies': self.proxies})
            case 'GET', ['providers', 'proxies']:
                return httpx.Response(200, json={'providers': self.providers})
            case 'PUT', ['proxies', name]:
                target = json.loads(req.content)['name']
                g = self.proxies.get(name)
                if g is None or target not in g['all']:
                    return httpx.Response(400, json={'message': 'Selector update error: proxy not exist'})
                g['now'] = target
                if g['type'] != 'Selector':
                    g['fixed'] = target
                return httpx.Response(204)
            case 'DELETE', ['proxies', name]:
                self.proxies[name]['fixed'] = ''
                return httpx.Response(204)
            case 'GET', ['group', name, 'delay']:
                result = {m: 99 for m in self.proxies[name]['all'] if m != 'JP/02 🇯🇵'}
                for m, d in result.items():
                    if m in self.proxies:
                        self.proxies[m]['history'] = [{'time': '2026-01-02T00:00:00Z', 'delay': d}]
                return httpx.Response(200, json=result)
            case 'GET', ['proxies', name, 'delay']:
                return httpx.Response(200, json={'delay': 42})
            case 'GET', ['providers', 'proxies', _, _, 'healthcheck']:
                return httpx.Response(200, json={'delay': 7})
            case 'GET', ['connections']:
                return httpx.Response(200, json={'connections': self.connections})
            case 'DELETE', ['connections', cid]:
                self.connections = [c for c in self.connections if c['id'] != cid]
                return httpx.Response(204)
            case _:
                return httpx.Response(404, json={'message': 'not found'})
