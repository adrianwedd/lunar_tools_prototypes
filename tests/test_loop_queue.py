import threading

from lunar_tools_art.loop_utils import MainLoopQueue


def test_post_from_thread_drain_on_main():
    q = MainLoopQueue()
    results = []
    t = threading.Thread(target=lambda: q.post(results.append, 42))
    t.start()
    t.join()
    assert results == []  # nothing ran until drained
    q.drain()
    assert results == [42]


def test_drain_respects_max_items():
    q = MainLoopQueue()
    hits = []
    for i in range(15):
        q.post(hits.append, i)
    q.drain(max_items=10)
    assert len(hits) == 10
    q.drain()
    assert len(hits) == 15
