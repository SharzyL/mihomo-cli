"""Textual TUI: browse proxy groups and switch proxies."""

import os
from enum import StrEnum
from typing import ClassVar, Literal, final

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input
from textual.widgets.data_table import RowDoesNotExist

from .api import MihomoClient, MihomoError, Snapshot
from .config import Config
from .models import Proxy


class SortKey(StrEnum):
    CONFIG = 'config'
    DELAY = 'delay'
    NAME = 'name'

    def next(self) -> 'SortKey':
        members = list(SortKey)
        return members[(members.index(self) + 1) % len(members)]


def term_theme() -> Literal['light', 'dark']:
    """Terminal background: TERM_THEME_OVERRIDE, then TERM_THEME_DETECTED, then dark."""
    for var in ('TERM_THEME_OVERRIDE', 'TERM_THEME_DETECTED'):
        match os.environ.get(var):
            case 'light':
                return 'light'
            case 'dark':
                return 'dark'
            case _:
                pass
    return 'dark'


def delay_text(delay: int | None) -> Text:
    if delay is None:
        return Text('-', style='dim')
    if delay == 0:
        return Text('timeout', style='red')
    style = 'green' if delay < 300 else 'yellow' if delay < 800 else 'red'
    return Text(f'{delay}ms', style=style)


class VimTable(DataTable[str | Text]):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding('j', 'cursor_down', show=False),
        Binding('k', 'cursor_up', show=False),
        Binding('g', 'scroll_top', show=False),
        Binding('G', 'scroll_bottom', show=False),
        Binding('ctrl+d', 'page_down', show=False),
        Binding('ctrl+u', 'page_up', show=False),
        # row cursor makes left/right meaningless inside a table; use them to switch panes
        Binding('h,left', 'app.focus_groups', show=False),
        Binding('l,right', 'app.focus_members', show=False),
    ]

    def __init__(self, *, id: str) -> None:
        super().__init__(id=id, cursor_type='row', zebra_stripes=True)

    def highlighted_key(self) -> str | None:
        if self.row_count == 0:
            return None
        return self.coordinate_to_cell_key(self.cursor_coordinate).row_key.value

    def move_to_key(self, key: str | None) -> bool:
        if key is None:
            return False
        try:
            self.move_cursor(row=self.get_row_index(key))
        except RowDoesNotExist:
            return False
        return True

    def set_rows(self, rows: list[tuple[str, list[str | Text]]], cursor: str | None) -> None:
        """Replace the table content, keeping the cursor on `cursor` (or the highlighted row) if possible.

        When the row keys are unchanged the cells are updated in place: clearing the table would reset
        the cursor and emit spurious RowHighlighted messages.
        """
        if [r.key.value for r in self.ordered_rows] == [key for key, _ in rows]:
            columns = [c.key for c in self.ordered_columns]
            for key, cells in rows:
                for column, cell in zip(columns, cells, strict=True):
                    self.update_cell(key, column, cell)
            if cursor is not None:
                self.move_to_key(cursor)
            return
        prev = self.highlighted_key()
        self.clear()
        for key, cells in rows:
            self.add_row(*cells, key=key)
        if not self.move_to_key(cursor):
            self.move_to_key(prev)


class FilterInput(Input):
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding('escape', 'app.clear_filter', 'Clear filter'),
    ]


@final
class MihomoApp(App[None]):
    TITLE = 'mihomoctl'
    CSS = """
    #groups-pane { width: 2fr; }
    #members-pane { width: 3fr; }
    #groups-pane, #members-pane { border: round $primary-background; }
    #groups-pane:focus-within, #members-pane:focus-within { border: round $primary; }
    VimTable { height: 1fr; }
    FilterInput { display: none; border: none; height: 1; padding: 0 1; }
    FilterInput.visible { display: block; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding('q', 'quit', 'Quit'),
        Binding('r', 'refresh', 'Refresh'),
        Binding('t', 'test_group', 'Test group'),
        Binding('T', 'test_proxy', 'Test proxy'),
        Binding('u', 'unfix', 'Unpin'),
        Binding('s', 'cycle_sort', 'Sort'),
        Binding('slash', 'filter', 'Filter'),
        Binding('escape', 'clear_filter', 'Clear filter', show=False),
        Binding('tab', 'toggle_pane', 'Switch pane', show=False),
    ]

    def __init__(self, config: Config, client: MihomoClient | None = None) -> None:
        super().__init__()
        self.config: Config = config
        self.client: MihomoClient = client or MihomoClient(config.controller.url, config.controller.secret)
        self.snapshot: Snapshot = Snapshot({}, [])
        self.group: str | None = None  # group whose members are shown
        self.sort: SortKey = SortKey.CONFIG
        self.filter: str = ''
        self.testing: set[str] = set()  # names with a delay test in flight

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id='groups-pane'):
                yield VimTable(id='groups')
            with Vertical(id='members-pane'):
                yield VimTable(id='members')
                yield FilterInput(placeholder='filter…', id='filter')
        yield Footer()

    @property
    def groups_table(self) -> VimTable:
        return self.query_one('#groups', VimTable)

    @property
    def members_table(self) -> VimTable:
        return self.query_one('#members', VimTable)

    @property
    def filter_input(self) -> FilterInput:
        return self.query_one('#filter', FilterInput)

    def on_mount(self) -> None:
        self.theme = f'atom-one-{term_theme()}'
        self.query_one('#groups-pane').border_title = 'Groups'
        self.groups_table.add_column('Group', key='name')
        self.groups_table.add_column('Type', key='type')
        self.groups_table.add_column('Now', key='now')
        self.members_table.add_column(' ', key='mark', width=1)
        self.members_table.add_column('Proxy', key='name')
        self.members_table.add_column('Type', key='type')
        self.members_table.add_column('Delay', key='delay')
        self.members_table.add_column('UDP', key='udp')
        self.groups_table.focus()
        self.initial_load()

    async def on_unmount(self) -> None:
        await self.client.aclose()

    # ---- data loading ----

    @work(exclusive=True, group='refresh')
    async def initial_load(self) -> None:
        try:
            version = await self.client.version()
            snapshot = await self.client.snapshot()
        except MihomoError as e:
            self.exit(return_code=1, message=f'mihomoctl: cannot reach {self.config.controller.url}: {e}')
            return
        self.sub_title = f'mihomo {version.version} @ {self.config.controller.url}'
        self.apply_snapshot(snapshot)

    @work(exclusive=True, group='refresh')
    async def reload(self) -> None:
        try:
            snapshot = await self.client.snapshot()
        except MihomoError as e:
            self.notify(str(e), title='Refresh failed', severity='error')
            return
        self.apply_snapshot(snapshot)

    def apply_snapshot(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot
        if self.group not in snapshot.groups:
            self.group = snapshot.groups[0] if snapshot.groups else None
        self.render_groups()
        self.render_members(keep_cursor=True)

    # ---- rendering ----

    def proxy(self, name: str) -> Proxy | None:
        return self.snapshot.proxies.get(name)

    def test_url(self, group: str) -> str:
        g = self.proxy(group)
        return (g.test_url if g else '') or self.config.proxies.test_url

    def resolve_chain(self, name: str) -> list[str]:
        """Follow `now` through nested groups: ['Group', 'SubGroup', 'leaf']."""
        chain = [name]
        while (p := self.proxy(chain[-1])) is not None and p.now and p.now not in chain:
            chain.append(p.now)
        return chain

    def render_groups(self) -> None:
        rows: list[tuple[str, list[str | Text]]] = []
        for name in self.snapshot.groups:
            g = self.snapshot.proxies[name]
            now = Text(g.now or '')
            if g.fixed:
                now = Text.assemble(('📌 ', ''), now)
            rows.append((name, [name, Text(g.type, style='dim'), now]))
        self.groups_table.set_rows(rows, cursor=self.group)

    def member_delay(self, p: Proxy, url: str) -> Text:
        if p.name in self.testing:
            return Text('testing…', style='italic dim')
        if p.is_group:
            return Text('→ ' + self.resolve_chain(p.name)[-1], style='cyan')
        if p.is_builtin:
            return Text('')
        return delay_text(p.last_delay(url))

    def sorted_members(self, group: Proxy, url: str) -> list[str]:
        names = list(group.all or [])
        if self.filter:
            needle = self.filter.casefold()
            names = [n for n in names if needle in n.casefold()]
        match self.sort:
            case SortKey.CONFIG:
                pass
            case SortKey.NAME:
                names.sort(key=str.casefold)
            case SortKey.DELAY:

                def key(n: str) -> tuple[int, int]:
                    p = self.proxy(n)
                    if p is None or p.is_group or p.is_builtin:
                        return (0, 0)
                    d = p.last_delay(url)
                    return (2, 0) if not d else (1, d)

                names.sort(key=key)
        return names

    def render_members(self, *, keep_cursor: bool) -> None:
        table = self.members_table
        pane = self.query_one('#members-pane')
        group = self.proxy(self.group) if self.group else None
        if group is None:
            pane.border_title = 'Proxies'
            table.clear()
            return
        url = self.test_url(group.name)
        rows: list[tuple[str, list[str | Text]]] = []
        for name in self.sorted_members(group, url):
            p = self.proxy(name)
            mark = Text('●', style='green bold') if name == group.now else Text('')
            if p is None:
                rows.append((name, [mark, name, Text('?', style='dim'), '', '']))
                continue
            rows.append(
                (
                    name,
                    [
                        mark,
                        Text(name, style='bold') if name == group.now else name,
                        Text(p.type, style='dim'),
                        self.member_delay(p, url),
                        Text('✓', style='green') if p.udp else Text(''),
                    ],
                )
            )
        prev = table.highlighted_key()
        cursor = prev if keep_cursor and any(key == prev for key, _ in rows) else group.now
        table.set_rows(rows, cursor=cursor)
        title = f'{group.name} [{group.type}]  sort: {self.sort}'
        if self.filter:
            title += f'  filter: {self.filter}'
        pane.border_title = title

    # ---- events ----

    @on(DataTable.RowHighlighted, '#groups')
    def group_highlighted(self, event: DataTable.RowHighlighted) -> None:
        name = event.row_key.value
        if name is not None and name != self.group:
            self.group = name
            self.render_members(keep_cursor=False)

    @on(DataTable.RowSelected, '#groups')
    def group_selected(self) -> None:
        self.members_table.focus()

    @on(DataTable.RowSelected, '#members')
    def member_selected(self, event: DataTable.RowSelected) -> None:
        if self.group is not None and event.row_key.value is not None:
            self.switch_proxy(self.group, event.row_key.value)

    @on(Input.Changed, '#filter')
    def filter_changed(self, event: Input.Changed) -> None:
        self.filter = event.value
        self.render_members(keep_cursor=True)

    @on(Input.Submitted, '#filter')
    def filter_submitted(self) -> None:
        if not self.filter:
            self.filter_input.remove_class('visible')
        self.members_table.focus()

    # ---- actions ----

    @work(group='switch')
    async def switch_proxy(self, group: str, name: str) -> None:
        g = self.proxy(group)
        if g is None:
            return
        if g.type not in ('Selector', 'URLTest', 'Fallback'):
            self.notify(f'{group} is a {g.type} group and cannot be switched manually', severity='warning')
            return
        try:
            await self.client.select(group, name)
        except MihomoError as e:
            self.notify(str(e), title=f'Failed to switch {group}', severity='error')
            return
        msg = f'{group} → {name}'
        if self.config.proxies.close_connections_on_switch:
            try:
                closed = await self.client.close_connections_through(group, name)
            except MihomoError as e:
                self.notify(str(e), title='Failed to close connections', severity='warning')
            else:
                msg += f' (closed {closed} connections)'
        self.notify(msg)
        self.reload()

    def action_refresh(self) -> None:
        self.reload()

    def action_focus_groups(self) -> None:
        self.groups_table.focus()

    def action_focus_members(self) -> None:
        self.members_table.focus()

    def action_toggle_pane(self) -> None:
        if self.groups_table.has_focus:
            self.members_table.focus()
        else:
            self.groups_table.focus()

    def action_cycle_sort(self) -> None:
        self.sort = self.sort.next()
        self.render_members(keep_cursor=True)

    def action_filter(self) -> None:
        self.filter_input.add_class('visible')
        self.filter_input.focus()

    def action_clear_filter(self) -> None:
        self.filter_input.value = ''  # triggers Input.Changed -> re-render
        self.filter_input.remove_class('visible')
        self.members_table.focus()

    def action_unfix(self) -> None:
        g = self.proxy(self.group) if self.group else None
        if g is None:
            return
        if not g.fixed:
            self.notify(f'{g.name} has no pinned proxy', severity='warning')
            return
        self.unfix(g.name)

    @work(group='switch')
    async def unfix(self, group: str) -> None:
        try:
            await self.client.unfix(group)
        except MihomoError as e:
            self.notify(str(e), title=f'Failed to unpin {group}', severity='error')
            return
        self.notify(f'{group} unpinned')
        self.reload()

    def action_test_group(self) -> None:
        if self.group is not None:
            self.test_group(self.group)

    def action_test_proxy(self) -> None:
        name = self.members_table.highlighted_key()
        p = self.proxy(name) if name else None
        if p is None or p.is_builtin:
            return
        if p.is_group:
            self.test_group(p.name)
        elif self.group is not None:
            self.test_proxy(p, self.test_url(self.group))

    def set_testing(self, names: list[str], on: bool) -> None:
        if on:
            self.testing.update(names)
        else:
            self.testing.difference_update(names)
        self.render_members(keep_cursor=True)

    @work(group='test')
    async def test_group(self, group: str) -> None:
        g = self.proxy(group)
        if g is None or g.all is None:
            return
        targets = [n for n in g.all if (p := self.proxy(n)) is not None and not p.is_builtin and not p.is_group]
        self.set_testing(targets, True)
        timeout = self.config.proxies.test_timeout
        try:
            result = await self.client.group_delay(group, self.test_url(group), timeout)
        except MihomoError as e:
            self.notify(str(e), title=f'Delay test of {group} failed', severity='error')
            result = {}
        else:
            alive = sum(1 for d in result.values() if d > 0)
            self.notify(f'{group}: {alive}/{len(targets)} alive')
        finally:
            self.set_testing(targets, False)
        self.reload()

    @work(group='test')
    async def test_proxy(self, proxy: Proxy, url: str) -> None:
        self.set_testing([proxy.name], True)
        try:
            delay = await self.client.proxy_delay(proxy, url, self.config.proxies.test_timeout)
        finally:
            self.set_testing([proxy.name], False)
        self.notify(f'{proxy.name}: {delay_text(delay).plain}')
        self.reload()
