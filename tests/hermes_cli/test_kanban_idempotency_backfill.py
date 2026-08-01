import json
import os
from pathlib import Path

from hermes_cli import kanban_db as kb


def _connect_home(tmp_path: Path):
    home = tmp_path / ".hermes"
    home.mkdir(parents=True, exist_ok=True)
    old_home = os.environ.get("HERMES_KANBAN_HOME")
    os.environ["HERMES_KANBAN_HOME"] = str(home)
    try:
        kb.init_db()
        return kb.connect_closing()
    finally:
        if old_home is None:
            os.environ.pop("HERMES_KANBAN_HOME", None)
        else:
            os.environ["HERMES_KANBAN_HOME"] = old_home


def test_single_backfill_assigns_key(tmp_path):
    with _connect_home(tmp_path) as conn:
        task_id = kb.create_task(
            conn,
            title="Fix bug https://github.com/pestoura/hermes-agent/issues/42",
            created_by="test",
        )
        report = kb.backfill_idempotency(conn, apply=False)
        assert report["counts"]["single"] == 1
        assert report["applied"] is False
        report = kb.backfill_idempotency(conn, apply=True)
        assert report["applied"] is True
        assert kb.get_task(conn, task_id).idempotency_key == "github:pestoura/hermes-agent#42"


def test_duplicate_unambiguous_archives_residual(tmp_path):
    with _connect_home(tmp_path) as conn:
        a = kb.create_task(
            conn,
            title="Issue https://github.com/pestoura/hermes-agent/issues/99",
            created_by="test",
        )
        b = kb.create_task(
            conn,
            title="Ref https://github.com/pestoura/hermes-agent/issues/99 again",
            created_by="test",
        )
        report = kb.backfill_idempotency(conn, apply=True)
        assert report["counts"]["duplicate_unambiguous"] == 1
        canonical = report["duplicate_unambiguous"][0]["canonical_task_id"]
        residual = [x for x in report["duplicate_unambiguous"][0]["tasks"] if x["task_id"] != canonical][0]["task_id"]
        assert kb.get_task(conn, canonical).idempotency_key == "github:pestoura/hermes-agent#99"
        assert kb.get_task(conn, residual).status == "archived"


def test_ambiguous_untouched(tmp_path):
    with _connect_home(tmp_path) as conn:
        kb.create_task(
            conn,
            title="https://github.com/pestoura/hermes-agent/issues/1 and https://github.com/pestoura/hermes-agent/pull/2",
            created_by="test",
        )
        report = kb.backfill_idempotency(conn, apply=True)
        assert report["counts"]["ambiguous"] == 1
        assert report["counts"]["single"] == 0
        assert report["counts"]["duplicate_unambiguous"] == 0


def test_existing_key_conflict_untouched(tmp_path):
    with _connect_home(tmp_path) as conn:
        first = kb.create_task(
            conn,
            title="Clash https://github.com/pestoura/hermes-agent/issues/7",
            created_by="test",
            idempotency_key="github:pestoura/hermes-agent#7",
        )
        second = kb.create_task(
            conn,
            title="Another https://github.com/pestoura/hermes-agent/issues/7",
            created_by="test",
        )
        report = kb.backfill_idempotency(conn, apply=True)
        assert report["counts"]["conflict_existing_key"] == 1
        assert kb.get_task(conn, second).idempotency_key is None
        assert kb.get_task(conn, second).status != "archived"


def test_apply_idempotent_repeat(tmp_path):
    with _connect_home(tmp_path) as conn:
        kb.create_task(
            conn,
            title="Stable https://github.com/pestoura/hermes-agent/issues/11",
            created_by="test",
        )
        first = kb.backfill_idempotency(conn, apply=True)
        assert first["counts"]["single"] == 1
        assert first["applied"] is True
        second = kb.backfill_idempotency(conn, apply=True)
        assert second["counts"]["single"] == 0
        assert second["applied"] is False


def test_runs_events_attachments_preserved(tmp_path):
    with _connect_home(tmp_path) as conn:
        a = kb.create_task(
            conn,
            title="Preserve https://github.com/pestoura/hermes-agent/issues/21",
            created_by="test",
        )
        b = kb.create_task(
            conn,
            title="Again https://github.com/pestoura/hermes-agent/issues/21",
            created_by="test",
        )
        kb.add_comment(conn, a, "tester", "keep me")
        kb.add_comment(conn, b, "tester", "also keep")
        kb._append_event(conn, a, "heartbeat", {"note": "a"})
        kb._append_event(conn, b, "heartbeat", {"note": "b"})
        conn.execute(
            "INSERT INTO task_runs (task_id, profile, status, started_at) VALUES (?, ?, ?, ?)",
            (a, "test", "running", 1),
        )
        conn.execute(
            "INSERT INTO task_runs (task_id, profile, status, started_at) VALUES (?, ?, ?, ?)",
            (b, "test", "running", 1),
        )
        kb.store_attachment_bytes(conn, a, filename="a.txt", data=b"a")
        kb.store_attachment_bytes(conn, b, filename="b.txt", data=b"b")
        report = kb.backfill_idempotency(conn, apply=True)
        canonical = report["duplicate_unambiguous"][0]["canonical_task_id"]
        residual = [x for x in report["duplicate_unambiguous"][0]["tasks"] if x["task_id"] != canonical][0]["task_id"]
        pre_events = len(kb.list_events(conn, residual))
        pre_attachments = len(kb.list_attachments(conn, residual))
        pre_runs = len(kb.list_runs(conn, residual))
        assert len(kb.list_events(conn, residual)) >= pre_events
        assert len(kb.list_attachments(conn, residual)) >= pre_attachments
        assert len(kb.list_runs(conn, residual)) >= pre_runs


def test_cli_default_dry_run_and_json(tmp_path):
    with _connect_home(tmp_path) as conn:
        kb.create_task(
            conn,
            title="Ref https://github.com/pestoura/hermes-agent/issues/77",
            created_by="test",
        )
        conn.close()

        import argparse
        import io
        import contextlib
        from hermes_cli.kanban import build_parser, kanban_command

        root = argparse.ArgumentParser()
        sub = root.add_subparsers(dest="_top")
        build_parser(sub)
        args = root.parse_args(["kanban", "backfill-idempotency"])
        assert getattr(args, "kanban_action", None) == "backfill-idempotency"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = kanban_command(args)
        assert rc == 0
        out = buf.getvalue()
        assert "Backfill idempotency (dry-run)" in out
        assert "single: 1" in out

        root2 = argparse.ArgumentParser()
        sub2 = root2.add_subparsers(dest="_top")
        build_parser(sub2)
        args2 = root2.parse_args(["kanban", "backfill-idempotency", "--json"])
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2), contextlib.redirect_stderr(io.StringIO()):
            rc2 = kanban_command(args2)
        assert rc2 == 0
        payload = json.loads(buf2.getvalue())
        assert payload["counts"]["single"] == 1
