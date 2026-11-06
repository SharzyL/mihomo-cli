import pytest
from textual.pilot import Pilot

from mihomoctl.app import MihomoApp, SortKey
from mihomoctl.config import Config

from .fake import FakeMihomo


async def settle(app: MihomoApp, pilot: Pilot[None]) -> None:
    # workers may chain (switch -> reload), so wait a few rounds
    for _ in range(3):
        await app.workers.wait_for_complete()  # pyright: ignore[reportUnknownMemberType]
        await pilot.pause()


def member_names(app: MihomoApp) -> list[str]:
    table = app.members_table
    return [str(table.get_row_at(i)[1]) for i in range(table.row_count)]


async def test_browse_and_switch() -> None:
    fake = FakeMihomo()
    app = MihomoApp(Config(), client=fake.client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        assert app.group == 'Proxy'
        assert app.members_table.highlighted_key() == 'Auto'  # cursor starts on current selection

        await pilot.press('l', 'j', 'j', 'enter')  # -> JP/02
        await settle(app, pilot)
        assert fake.proxies['Proxy']['now'] == 'JP/02 🇯🇵'
        assert app.snapshot.proxies['Proxy'].now == 'JP/02 🇯🇵'
        assert app.members_table.highlighted_key() == 'JP/02 🇯🇵'

        await pilot.press('h', 'j')  # next group
        await settle(app, pilot)
        assert app.group == 'Auto'
        assert member_names(app) == ['HK 01', 'US 03']


async def test_filter_and_sort() -> None:
    fake = FakeMihomo()
    app = MihomoApp(Config(), client=fake.client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press('slash', 'h', 'k', 'enter')
        assert member_names(app) == ['HK 01']
        await pilot.press('escape')
        assert len(member_names(app)) == 6

        await pilot.press('s')
        assert app.sort is SortKey.DELAY
        # groups/builtins first, then by delay, failed (0) last
        assert member_names(app) == ['Auto', 'DIRECT', 'SG 04', 'HK 01', 'US 03', 'JP/02 🇯🇵']


async def test_group_delay_test_refreshes() -> None:
    fake = FakeMihomo()
    app = MihomoApp(Config(), client=fake.client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press('t')
        await settle(app, pilot)
        assert not app.testing
        assert app.snapshot.proxies['US 03'].last_delay() == 99


async def test_unpin_and_close_connections() -> None:
    fake = FakeMihomo()
    config = Config()
    config.proxies.close_connections_on_switch = True
    app = MihomoApp(config, client=fake.client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        app.switch_proxy('Proxy', 'US 03')
        await settle(app, pilot)
        assert [c['id'] for c in fake.connections] == ['c2', 'c3']

        app.switch_proxy('Auto', 'US 03')
        await settle(app, pilot)
        assert app.snapshot.proxies['Auto'].fixed == 'US 03'
        await pilot.press('j', 'u')  # select Auto group, unpin
        await settle(app, pilot)
        assert not app.snapshot.proxies['Auto'].fixed


async def test_connection_failure_exits() -> None:
    fake = FakeMihomo()
    app = MihomoApp(Config(), client=fake.client(secret='wrong'))
    async with app.run_test() as pilot:
        await settle(app, pilot)
    assert app.return_code == 1


async def test_cursor_stays_after_refresh() -> None:
    fake = FakeMihomo()
    app = MihomoApp(Config(), client=fake.client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        await pilot.press('j')  # second group: Auto
        await settle(app, pilot)
        await pilot.press('l', 'j')  # cursor on 'US 03', not the current selection
        assert app.members_table.highlighted_key() == 'US 03'

        await pilot.press('T')
        await settle(app, pilot)
        assert app.group == 'Auto'
        assert app.groups_table.highlighted_key() == 'Auto'
        assert app.members_table.highlighted_key() == 'US 03'

        await pilot.press('r')
        await settle(app, pilot)
        assert app.members_table.highlighted_key() == 'US 03'


@pytest.mark.parametrize(
    ('override', 'detected', 'expected'),
    [
        ('light', 'dark', 'light'),
        ('dark', 'light', 'dark'),
        ('bogus', 'light', 'light'),
        (None, 'dark', 'dark'),
        (None, 'bogus', 'dark'),
        (None, None, 'dark'),
    ],
)
async def test_theme_from_env(
    monkeypatch: pytest.MonkeyPatch, override: str | None, detected: str | None, expected: str
) -> None:
    for var, value in (('TERM_THEME_OVERRIDE', override), ('TERM_THEME_DETECTED', detected)):
        if value is None:
            monkeypatch.delenv(var, raising=False)
        else:
            monkeypatch.setenv(var, value)
    app = MihomoApp(Config(), client=FakeMihomo().client())
    async with app.run_test() as pilot:
        await settle(app, pilot)
        assert app.theme == f'atom-one-{expected}'
