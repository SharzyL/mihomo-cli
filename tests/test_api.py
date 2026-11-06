import pytest

from mihomoctl.api import MihomoError

from .fake import FakeMihomo


async def test_snapshot_merges_providers_and_orders_groups() -> None:
    fake = FakeMihomo()
    async with fake.client() as client:
        snap = await client.snapshot()
    assert snap.groups == ['Proxy', 'Auto', 'GLOBAL']  # GLOBAL order, hidden dropped, GLOBAL last
    assert snap.proxies['SG 04'].provider_name == 'sub'
    assert snap.proxies['HK 01'].last_delay() == 120
    assert snap.proxies['JP/02 🇯🇵'].last_delay() == 0
    assert snap.proxies['Auto'].is_group and not snap.proxies['HK 01'].is_group
    assert snap.proxies['DIRECT'].is_builtin


async def test_select_escapes_names() -> None:
    fake = FakeMihomo()
    async with fake.client() as client:
        await client.select('Proxy', 'JP/02 🇯🇵')
    assert fake.proxies['Proxy']['now'] == 'JP/02 🇯🇵'
    assert ('PUT', 'proxies/Proxy') in fake.requests


async def test_select_on_urltest_pins_and_unfix() -> None:
    fake = FakeMihomo()
    async with fake.client() as client:
        await client.select('Auto', 'US 03')
        assert (await client.proxies())['Auto'].fixed == 'US 03'
        await client.unfix('Auto')
        assert (await client.proxies())['Auto'].fixed == ''


async def test_errors_carry_server_message() -> None:
    fake = FakeMihomo()
    async with fake.client(secret='wrong') as client:
        with pytest.raises(MihomoError, match='401 Unauthorized'):
            await client.proxies()
    async with fake.client() as client:
        with pytest.raises(MihomoError, match='proxy not exist'):
            await client.select('Proxy', 'nope')


async def test_proxy_delay_uses_provider_endpoint() -> None:
    fake = FakeMihomo()
    async with fake.client() as client:
        snap = await client.snapshot()
        assert await client.proxy_delay(snap.proxies['HK 01'], 'http://t', 1000) == 42
        assert await client.proxy_delay(snap.proxies['SG 04'], 'http://t', 1000) == 7
    assert ('GET', 'providers/proxies/sub/SG 04/healthcheck') in fake.requests


async def test_close_connections_through() -> None:
    fake = FakeMihomo()
    async with fake.client() as client:
        assert await client.close_connections_through('Proxy', 'US 03') == 1
    assert [c['id'] for c in fake.connections] == ['c2', 'c3']
