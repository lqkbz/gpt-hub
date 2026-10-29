from core.ratelimit import SlidingWindow


def test_limit_within_window():
    w = SlidingWindow(2, 60)
    assert w.hit("a", 0) and w.hit("a", 1)
    assert not w.hit("a", 2)


def test_window_slides():
    w = SlidingWindow(1, 60)
    assert w.hit("a", 0)
    assert not w.hit("a", 59)
    assert w.hit("a", 60.1)


def test_keys_independent():
    w = SlidingWindow(1, 60)
    assert w.hit("a", 0) and w.hit("b", 0)


def test_rejected_hit_not_recorded():
    w = SlidingWindow(1, 10)
    assert w.hit("a", 0)
    assert not w.hit("a", 5)
    assert w.hit("a", 10.5)
