import json


def test_job_public_record_is_json_safe(monkeypatch):
    import desktop_executor

    monkeypatch.setattr(desktop_executor.threading, "Thread", lambda **kwargs: type(
        "FakeThread", (), {"start": lambda self: None}
    )())
    plan = {
        "bpm": 140, "key": "F", "scale": "minor", "bars": 8, "style": "trap",
        "midi_files": {"chords": "a.mid", "melody": "b.mid"},
    }
    job = desktop_executor.start_beat(plan)
    plan["desktop_job"] = job
    json.dumps(plan)
    assert "_plan" not in job
    assert job["status"] == "queued"
