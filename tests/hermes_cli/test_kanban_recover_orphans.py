"""Tests for hermes kanban recover-orphans.

Covers the required acceptance scenarios:
- PID dead + run missing/closed -> candidate and apply recovery.
- PID alive -> ignored.
- active run -> ignored.
- recent heartbeat -> ignored.
- two apply passes -> second idempotent.
- two processes -> only one recovery.
- dry-run does not change DB.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import pytest

from hermes_cli import kanban_db as kb


REQUIRED_TESTS = [
    "test_recover_orphans_dry_run_reports_dead_pid_no_run",
    "test_recover_orphans_apply_recovers_dead_pid_no_run",
    "test_recover_orphans_alive_pid_ignored",
    "test_recover_orphans_active_run_ignored",
    "test_recover_orphans_recent_heartbeat_ignored",
    "test_recover_orphans_apply_idempotent_second_pass",
    "test_recover_orphans_apply_concurrent_single_recovery",
    "test_recover_orphans_dry_run_does_not_mutate_db",
]


@pytest.fixture
def kanban_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_CRASH_GRACE_SECONDS", "0")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    db_path = kb.kanban_db_path(board="default")
    kb._INITIALIZED_PATHS.discard(str(db_path.resolve()))
    kb.init_db()
    return home


@pytest.fixture
def conn(kanban_home):
    with kb.connect() as c:
        yield c


def _host():
    return kb._claimer_id().split(":", 1)[0]


def test_recover_orphans_dry_run_reports_dead_pid_no_run(conn):
    tid = kb.create_task(conn, title="orphan", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    results = kb.recover_orphans(conn, apply=False)

    assert [r["task_id"] for r in results] == [tid]
    assert results[0]["reason"] == "dead_pid,no_run"
    row = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "running"


def test_recover_orphans_apply_recovers_dead_pid_no_run(conn):
    tid = kb.create_task(conn, title="orphan", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    results = kb.recover_orphans(conn, apply=True)

    assert [r["task_id"] for r in results] == [tid]
    assert results[0]["reason"] == "dead_pid,no_run"
    row = conn.execute("SELECT status, claim_lock FROM tasks WHERE id=?", (tid,)).fetchone()
    assert row["status"] == "ready"
    assert row["claim_lock"] is None
    events = kb.list_events(conn, tid)
    assert any(e.kind == "orphan_recovered" for e in events)


def test_recover_orphans_alive_pid_ignored(conn):
    tid = kb.create_task(conn, title="alive", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        kb._set_worker_pid(conn, tid, sleeper.pid)
        conn.execute(
            "UPDATE tasks SET current_run_id=NULL WHERE id=?",
            (tid,),
        )
        conn.commit()

        results = kb.recover_orphans(conn, apply=False)
        assert results == []
    finally:
        sleeper.terminate()
        sleeper.wait()


def test_recover_orphans_active_run_ignored(conn):
    tid = kb.create_task(conn, title="active run", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.commit()

    results = kb.recover_orphans(conn, apply=False)
    assert results == []


def test_recover_orphans_recent_heartbeat_ignored(conn):
    tid = kb.create_task(conn, title="recent hb", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET last_heartbeat_at=? WHERE id=?",
        (int(time.time()), tid),
    )
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    results = kb.recover_orphans(conn, apply=False)
    assert results == []


def test_recover_orphans_apply_idempotent_second_pass(conn):
    tid = kb.create_task(conn, title="idempotent", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    first = kb.recover_orphans(conn, apply=True)
    assert len(first) == 1
    second = kb.recover_orphans(conn, apply=True)
    assert second == []


def test_recover_orphans_apply_concurrent_single_recovery(conn):
    tid = kb.create_task(conn, title="concurrent", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    results: list[list[dict[str, object]]] = []
    errors: list[Exception] = []

    def worker(path: Path) -> None:
        try:
            con = kb.connect(db_path=path)
            try:
                out = kb.recover_orphans(con, apply=True)
                results.append(out)
            finally:
                con.close()
        except Exception as exc:
            errors.append(exc)

    db = kb.kanban_db_path(board="default")
    threads = [threading.Thread(target=worker, args=(db,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    recovered = [r for r in results if any(item["task_id"] == tid for item in r)]
    assert len(recovered) == 1


def test_recover_orphans_dry_run_does_not_mutate_db(conn):
    tid = kb.create_task(conn, title="dry", assignee="w")
    host = _host()
    kb.claim_task(conn, tid, claimer=f"{host}:A")
    dead = subprocess.Popen(["true"])
    dead.wait()
    kb._set_worker_pid(conn, tid, dead.pid)
    conn.execute(
        "UPDATE tasks SET current_run_id=NULL WHERE id=?",
        (tid,),
    )
    conn.commit()

    before = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    events_before = conn.execute("SELECT COUNT(*) AS n FROM task_events WHERE task_id=?", (tid,)).fetchone()["n"]

    kb.recover_orphans(conn, apply=False)

    after = conn.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    events_after = conn.execute("SELECT COUNT(*) AS n FROM task_events WHERE task_id=?", (tid,)).fetchone()["n"]
    assert dict(before) == dict(after)
    assert events_before == events_after
