"""Limiteur partagé entre processus (Redis) et repli mémoire si Redis est indisponible."""

import asyncio

import pytest

from app.middleware import idempotency, rate_limit


class _RedisFaux:
    """Exécute la logique du script Lua sur un ZSET en mémoire."""

    def __init__(self) -> None:
        self.zsets: dict[str, list[tuple[float, str]]] = {}

    async def eval(self, _script, _n, key, now, win, limit, membre):
        z = [(s, m) for s, m in self.zsets.get(key, []) if s > now - win]
        self.zsets[key] = z
        if len(z) >= limit:
            return [0, 0, str(min(s for s, _ in z))]
        z.append((now, membre))
        return [1, limit - len(z), "0"]


class _RedisKo:
    appels = 0

    async def eval(self, *_a):
        _RedisKo.appels += 1
        raise ConnectionError("redis indisponible")


@pytest.fixture(autouse=True)
def _reinit(monkeypatch):
    monkeypatch.setattr(rate_limit, "_redis_ko_jusqua", 0.0)
    monkeypatch.setattr(rate_limit, "_BUCKET", rate_limit._SlidingWindow())


def test_compteur_partage_entre_processus(monkeypatch):
    redis = _RedisFaux()
    monkeypatch.setattr(idempotency, "_redis", lambda: redis)

    async def scenario():
        # Deux « processus » = deux appels indépendants sur le même Redis : la limite est globale.
        r1 = await rate_limit._hit_partage("api:1.2.3.4", limit=2)
        r2 = await rate_limit._hit_partage("api:1.2.3.4", limit=2)
        r3 = await rate_limit._hit_partage("api:1.2.3.4", limit=2)
        autre = await rate_limit._hit_partage("api:5.6.7.8", limit=2)
        return r1, r2, r3, autre

    r1, r2, r3, autre = asyncio.run(scenario())
    assert r1[:2] == (True, 1)
    assert r2[:2] == (True, 0)
    assert r3[0] is False and 1 <= r3[2] <= 60
    assert autre[0] is True


def test_repli_memoire_sans_reessayer_redis(monkeypatch):
    _RedisKo.appels = 0
    monkeypatch.setattr(idempotency, "_redis", lambda: _RedisKo())

    async def scenario():
        return [await rate_limit._hit_partage("login_platform:ip", limit=2) for _ in range(3)]

    resultats = asyncio.run(scenario())
    assert [r[0] for r in resultats] == [True, True, False]
    assert _RedisKo.appels == 1
