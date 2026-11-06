"""Async client for the mihomo external controller (RESTful API)."""

from dataclasses import dataclass
from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx
import msgspec

from .models import (
    ConnectionsResponse,
    DelayResponse,
    ProvidersResponse,
    ProxiesResponse,
    Proxy,
    Version,
)


class MihomoError(Exception):
    pass


def _seg(name: str) -> str:
    # Proxy names routinely contain spaces, emoji and '/', so escape everything.
    return quote(name, safe='')


@dataclass(frozen=True)
class Snapshot:
    """All proxies (including provider proxies) plus the visible groups in display order."""

    proxies: dict[str, Proxy]
    groups: list[str]


def build_snapshot(proxies: dict[str, Proxy], providers: ProvidersResponse) -> Snapshot:
    # /proxies omits proxies that come from (non-inline) proxy providers; merge them in.
    merged: dict[str, Proxy] = {}
    for provider in providers.providers.values():
        if provider.name == 'default' or provider.vehicle_type == 'Compatible':
            continue
        for p in provider.proxies:
            merged[p.name] = p
    merged.update(proxies)

    groups = [name for name, p in merged.items() if p.is_group and not p.hidden]
    # Order groups as they appear in GLOBAL (i.e. config order), GLOBAL itself last.
    if (glob := merged.get('GLOBAL')) is not None and glob.all is not None:
        order = {name: i for i, name in enumerate([*glob.all, 'GLOBAL'])}
        groups.sort(key=lambda g: order.get(g, -1))
    return Snapshot(merged, groups)


class MihomoClient:
    def __init__(
        self,
        url: str,
        secret: str | None = None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {'Authorization': f'Bearer {secret}'} if secret else {}
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=url, headers=headers, timeout=timeout, transport=transport
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json: object = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        try:
            resp = await self._http.request(
                method,
                path,
                params=params,
                json=json,
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as e:
            raise MihomoError(f'{method} {path}: {e or type(e).__name__}') from e
        if resp.is_error:
            try:
                msg = str(msgspec.json.decode(resp.content, type=dict[str, object]).get('message', resp.text))
            except msgspec.DecodeError:
                msg = resp.text
            raise MihomoError(f'{resp.status_code} {msg}'.strip())
        return resp

    async def _get[T](
        self, path: str, type: type[T], *, params: dict[str, str | int] | None = None, timeout: float | None = None
    ) -> T:
        resp = await self._request('GET', path, params=params, timeout=timeout)
        return msgspec.json.decode(resp.content, type=type)

    async def version(self) -> Version:
        return await self._get('/version', Version)

    async def proxies(self) -> dict[str, Proxy]:
        return (await self._get('/proxies', ProxiesResponse)).proxies

    async def providers(self) -> ProvidersResponse:
        return await self._get('/providers/proxies', ProvidersResponse)

    async def snapshot(self) -> Snapshot:
        return build_snapshot(await self.proxies(), await self.providers())

    async def select(self, group: str, name: str) -> None:
        """Select `name` in `group`. On URLTest/Fallback groups this pins (fixes) the choice."""
        await self._request('PUT', f'/proxies/{_seg(group)}', json={'name': name})

    async def unfix(self, group: str) -> None:
        """Clear a pinned selection on a URLTest/Fallback group."""
        await self._request('DELETE', f'/proxies/{_seg(group)}')

    async def proxy_delay(self, proxy: Proxy, url: str, timeout_ms: int) -> int:
        """Test a single proxy; returns delay in ms, 0 if it failed."""
        # Provider proxies are not reachable via /proxies/{name}; use the provider endpoint instead.
        if proxy.provider_name:
            path = f'/providers/proxies/{_seg(proxy.provider_name)}/{_seg(proxy.name)}/healthcheck'
        else:
            path = f'/proxies/{_seg(proxy.name)}/delay'
        try:
            resp = await self._get(
                path,
                DelayResponse,
                params={'url': url, 'timeout': timeout_ms},
                timeout=timeout_ms / 1000 + 5,
            )
        except MihomoError:
            return 0
        return resp.delay

    async def group_delay(self, group: str, url: str, timeout_ms: int) -> dict[str, int]:
        """Test every member of a group; members missing from the result failed."""
        return await self._get(
            f'/group/{_seg(group)}/delay',
            dict[str, int],
            params={'url': url, 'timeout': timeout_ms},
            timeout=timeout_ms / 1000 + 5,
        )

    async def close_connections_through(self, group: str, keep: str) -> int:
        """Close connections routed through `group` but not through `keep`. Returns the count closed."""
        conns = (await self._get('/connections', ConnectionsResponse)).connections or []
        closed = 0
        for c in conns:
            if group in c.chains and keep not in c.chains:
                await self._request('DELETE', f'/connections/{_seg(c.id)}')
                closed += 1
        return closed
