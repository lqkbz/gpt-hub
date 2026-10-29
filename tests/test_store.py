from core.store import GroupPolicy, Store


def make(tmp_path):
    return Store(tmp_path / "hub.db")


def test_default_policy(tmp_path):
    s = make(tmp_path)
    assert s.get_policy("100") == GroupPolicy(group_id="100")


def test_save_and_load_policy(tmp_path):
    s = make(tmp_path)
    s.save_policy(GroupPolicy("100", model="gpt-x", effort="medium", features={"draw": 3}, chat_enabled=False))
    assert s.get_policy("100") == GroupPolicy("100", "gpt-x", "medium", {"draw": 3}, False)
    s.save_policy(GroupPolicy("100", features={}))
    assert s.get_policy("100") == GroupPolicy("100")


def test_counters_isolated_by_day(tmp_path):
    s = make(tmp_path)
    assert s.get_counter("k", "2026-10-29") == 0
    assert s.incr_counter("k", "2026-10-29") == 1
    assert s.incr_counter("k", "2026-10-29", 2) == 3
    assert s.get_counter("k", "2026-10-30") == 0
    assert s.get_counter("other", "2026-10-29") == 0


def test_voice_toggle(tmp_path):
    s = make(tmp_path)
    assert s.is_voice("u") is False
    s.set_voice("u", True)
    assert s.is_voice("u") is True
    s.set_voice("u", False)
    assert s.is_voice("u") is False


def test_jobs(tmp_path):
    s = make(tmp_path)
    j1 = s.create_job("umo", "1", "topic a", 10.0)
    j2 = s.create_job("umo", "1", "topic b", 11.0)
    s.create_job("other", "2", "topic c", 12.0)
    assert j1.status == "queued" and j1.id != j2.id
    s.update_job(j1.id, status="done", finished_at=20.0, report_path="/r.md")
    got = s.get_job(j1.id)
    assert (got.status, got.finished_at, got.report_path, got.error) == ("done", 20.0, "/r.md", None)
    assert [j.id for j in s.list_jobs("umo")] == [j2.id, j1.id]
    assert s.get_job(999) is None


def test_mark_unfinished_interrupted(tmp_path):
    s = make(tmp_path)
    a = s.create_job("u", "1", "a", 1.0)
    b = s.create_job("u", "1", "b", 2.0)
    c = s.create_job("u", "1", "c", 3.0)
    s.update_job(b.id, status="running")
    s.update_job(c.id, status="done")
    changed = s.mark_unfinished_interrupted(5.0)
    assert sorted(j.id for j in changed) == [a.id, b.id]
    assert s.get_job(a.id).status == "interrupted"
    assert s.get_job(a.id).finished_at == 5.0
    assert s.get_job(c.id).status == "done"


def test_persistence(tmp_path):
    s = make(tmp_path)
    s.save_policy(GroupPolicy("1", features={"voice": 2}))
    s.close()
    assert make(tmp_path).get_policy("1").features == {"voice": 2}


def test_tts_choice(tmp_path):
    s = make(tmp_path)
    assert s.get_tts_choice("global") is None
    s.set_tts_choice("global", "idx")
    s.set_tts_choice("group:1", "edge")
    assert (s.get_tts_choice("global"), s.get_tts_choice("group:1")) == ("idx", "edge")
    s.set_tts_choice("group:1", None)
    assert s.get_tts_choice("group:1") is None
