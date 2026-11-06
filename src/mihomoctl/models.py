"""Typed views of the mihomo REST API payloads (only the fields we use)."""

import msgspec

# Built-in outbounds that are never latency-tested.
BUILTIN_TYPES = frozenset({'Direct', 'Reject', 'RejectDrop', 'Compatible', 'Pass', 'PassRule', 'Dns'})


class DelayRecord(msgspec.Struct):
    time: str
    delay: int  # 0 means the test failed


class ExtraHistory(msgspec.Struct):
    history: list[DelayRecord] = []


class Proxy(msgspec.Struct, kw_only=True):
    name: str
    type: str
    udp: bool = False
    history: list[DelayRecord] = []
    extra: dict[str, ExtraHistory] = {}
    provider_name: str = msgspec.field(default='', name='provider-name')
    # group-only fields
    all: list[str] | None = None
    now: str | None = None
    fixed: str | None = None  # URLTest/Fallback: member pinned via PUT
    hidden: bool = False
    test_url: str = msgspec.field(default='', name='testUrl')

    @property
    def is_group(self) -> bool:
        return self.all is not None

    @property
    def is_builtin(self) -> bool:
        return self.type in BUILTIN_TYPES

    def last_delay(self, test_url: str | None = None) -> int | None:
        """Most recent delay in ms (0 = failed), or None if never tested."""
        history = self.history
        if test_url and test_url in self.extra:
            history = self.extra[test_url].history
        return history[-1].delay if history else None


class ProxiesResponse(msgspec.Struct):
    proxies: dict[str, Proxy]


class Provider(msgspec.Struct, kw_only=True):
    name: str
    vehicle_type: str = msgspec.field(name='vehicleType')
    proxies: list[Proxy] = []


class ProvidersResponse(msgspec.Struct):
    providers: dict[str, Provider]


class DelayResponse(msgspec.Struct):
    delay: int


class Connection(msgspec.Struct):
    id: str
    chains: list[str]


class ConnectionsResponse(msgspec.Struct):
    connections: list[Connection] | None = None


class Version(msgspec.Struct):
    version: str
    meta: bool = False
