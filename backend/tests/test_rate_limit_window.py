from app.middleware.rate_limit import _SlidingWindow


def test_fenetre_glissante_refuse_au_dela_de_la_limite():
    w = _SlidingWindow()
    assert w.hit("k", limit=2)[:2] == (True, 1)
    assert w.hit("k", limit=2)[:2] == (True, 0)
    ok, remaining, retry = w.hit("k", limit=2)
    assert ok is False
    assert remaining == 0
    assert 1 <= retry <= 60
