"""Tests for the shared rapid store path (fake store: no network, no DB).

    python3 -m pytest scrapers/test_rapid_store.py -q
"""
import io
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import directory_web_checks_publish as pub  # noqa: E402
import office_census_rapid as rv  # noqa: E402
import rapid_store as store  # noqa: E402
from test_office_census_rapid import rec, setup_dir  # noqa: E402


class FakeStore:
    """Scripted rapid_* replies; records every call."""

    def __init__(self, record_outcomes=(), next_reply=None, log=()):
        self.calls, self.outcomes, self.next_reply, self.log = [], list(record_outcomes), next_reply, list(log)
        self.seen = {}

    def rpc(self, name, **params):
        self.calls.append((name, params))
        if name == "rapid_record":
            eid = params["p_entry"]["entry_id"]
            if eid in self.seen:
                return {"outcome": self.seen[eid], "duplicate": True}
            out = self.outcomes.pop(0) if self.outcomes else {"outcome": "live"}
            if out["outcome"] != "rejected":
                self.seen[eid] = out["outcome"]
            return out
        if name == "rapid_next":
            return self.next_reply
        if name == "rapid_pull":
            return self.log[params["p_offset"]:params["p_offset"] + params["p_limit"]]
        if name == "rapid_release":
            return 0
        raise AssertionError(name)


def remote(tmp_path, monkeypatch, fake):
    setup_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(store, "rpc", fake.rpc)
    monkeypatch.setattr(store, "configured", lambda: True)
    return ["--store", "supabase", "--rapid-dir", str(tmp_path)]


def record(argv, monkeypatch, obj, session="cloud-1"):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(obj)))
    return rv.main(argv + ["record", "--session", session])


def mirror(tmp_path):
    p = tmp_path / "checks.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


# ---- store selection ---------------------------------------------------------------
def test_real_queue_fails_closed_without_store(monkeypatch, capsys):
    monkeypatch.setattr(store, "missing", lambda: ["RAPID_TOKEN"])
    monkeypatch.setattr(store, "configured", lambda: False)
    assert rv.main(["next", "--session", "x"]) == 2
    assert "STORE NOT CONFIGURED: missing RAPID_TOKEN" in capsys.readouterr().out


def test_rapid_dir_runs_stay_local(tmp_path, monkeypatch):
    setup_dir(tmp_path, monkeypatch)
    monkeypatch.setattr(store, "configured", lambda: True)
    monkeypatch.setattr(rv, "dns_status", lambda urls: {})
    monkeypatch.setattr(store, "rpc", lambda *a, **k: pytest.fail("a --rapid-dir run touched the store"))
    assert rv.main(["--rapid-dir", str(tmp_path), "next", "--n", "1", "--session", "a"]) == 0
    assert rv.P.store == "local"


# ---- record ------------------------------------------------------------------------
def test_record_goes_live_with_the_page_row(tmp_path, monkeypatch, capsys):
    fake = FakeStore()
    argv = remote(tmp_path, monkeypatch, fake)
    assert record(argv, monkeypatch, rec(decision="VALID_CORRECTED", observed={"name": "Main St Smiles"})) == 0
    assert "live on the Directory page" in capsys.readouterr().out
    (name, params), = fake.calls
    row = params["p_row"]
    assert name == "rapid_record" and row["location_id"] == "aaaaaaaaaaaaaaaa"
    assert row["effect"] == "open_corrected" and row["publish_id"] == params["p_entry"]["entry_id"]
    assert set(row) == set(pub.COLS)
    assert [e["entry_id"] for e in mirror(tmp_path)] == [params["p_entry"]["entry_id"]]


def test_store_rejection_is_not_mirrored(tmp_path, monkeypatch, capsys):
    fake = FakeStore([{"outcome": "rejected", "error": "this row already has a check; add \"supersede\": true"}])
    argv = remote(tmp_path, monkeypatch, fake)
    assert record(argv, monkeypatch, rec()) == 1
    assert "REJECTED" in capsys.readouterr().out and mirror(tmp_path) == []


def test_held_removal_is_mirrored_as_held_and_kept_off_the_page(tmp_path, monkeypatch, capsys):
    fake = FakeStore([{"outcome": "held", "held_reason": "removals would be 11/20"}])
    argv = remote(tmp_path, monkeypatch, fake)
    closed = rec(decision="NOT_CURRENT_GP", reason="closed", ties_by=["name"],
                 evidence=[{"kind": "listing", "url": "https://www.yelp.com/biz/x", "quote": "X - CLOSED"}])
    assert record(argv, monkeypatch, closed) == 0
    assert "HELD by the removal brake" in capsys.readouterr().out
    assert mirror(tmp_path)[0]["outcome"] == "held"
    assert rv.latest_checks(include_held=False) == {}          # the publisher skips it
    assert "loc:aaaaaaaaaaaaaaaa" in rv.latest_checks()      # but the row counts as checked


def test_resending_the_same_record_is_a_no_op(tmp_path, monkeypatch, capsys):
    fake = FakeStore()
    argv = remote(tmp_path, monkeypatch, fake)
    assert record(argv, monkeypatch, rec()) == 0
    assert record(argv, monkeypatch, rec()) == 0
    ids = [c[1]["p_entry"]["entry_id"] for c in fake.calls]
    assert ids[0] == ids[1]                                   # content-derived id
    assert "already recorded earlier" in capsys.readouterr().out
    assert len(mirror(tmp_path)) == 1


def test_network_failure_says_not_saved(tmp_path, monkeypatch, capsys):
    fake = FakeStore()
    argv = remote(tmp_path, monkeypatch, fake)

    def down(name, **params):
        raise store.StoreError("Supabase unreachable after 4 attempts")
    monkeypatch.setattr(store, "rpc", down)
    assert record(argv, monkeypatch, rec()) == 1
    assert "NOT SAVED" in capsys.readouterr().out and mirror(tmp_path) == []


# ---- next ----------------------------------------------------------------------------
def test_next_claims_through_the_store(tmp_path, monkeypatch, capsys):
    fake = FakeStore(next_reply={"picked": ["loc:bbbbbbbbbbbbbbbb"], "resumed": 0, "searches_used": 12,
                                 "held": 0, "remaining": 2})
    argv = remote(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(rv, "dns_status", lambda urls: {})
    assert rv.main(argv + ["next", "--n", "5", "--session", "cloud-1"]) == 0
    out = capsys.readouterr().out
    assert "loc:bbbbbbbbbbbbbbbb" in out and "12/170" in out and "PUBLISH DUE" not in out
    (name, params), = fake.calls
    assert params["p_ids"] == ["loc:aaaaaaaaaaaaaaaa", "loc:bbbbbbbbbbbbbbbb"] and params["p_n"] == 5


def test_next_stops_a_session_after_a_held_removal(tmp_path, monkeypatch, capsys):
    fake = FakeStore(next_reply={"picked": [], "resumed": 0, "searches_used": 40, "held": 1, "remaining": 2})
    argv = remote(tmp_path, monkeypatch, fake)
    assert rv.main(argv + ["next", "--session", "cloud-1"]) == 0
    assert "REMOVAL BRAKE" in capsys.readouterr().out


def test_dns_check_skipped_when_the_sandbox_resolves_nothing(monkeypatch):
    monkeypatch.setattr(rv, "dns_works", lambda: False)
    assert rv.dns_status(["https://example-dental.com"]) == {"https://example-dental.com": "dns not checked"}


# ---- pull ----------------------------------------------------------------------------
def test_pull_keeps_local_lines_verbatim_and_adds_other_sessions(tmp_path, monkeypatch):
    fake = FakeStore()
    remote(tmp_path, monkeypatch, fake)
    rv.P.store = "supabase"
    t = "2026-09-25T21:00:00+00:00"
    a = {"entry_id": "rc-z", "candidate_id": "loc:aaaaaaaaaaaaaaaa", "recorded_at": t, "decision": "VALID"}
    b = {"entry_id": "rc-a", "candidate_id": "loc:bbbbbbbbbbbbbbbb", "recorded_at": t, "decision": "VALID"}
    text = "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in (a, b))
    (tmp_path / "checks.jsonl").write_text(text)
    other = {"entry_id": "rc-m", "candidate_id": "loc:cccccccccccccccc", "recorded_at": "2026-09-25T20:00:00+00:00",
             "decision": "IDENTITY_ONLY", "outcome": "live"}
    # the log returns jsonb (keys reordered), sorted by (recorded_at, entry_id)
    fake.log = [other, dict(sorted(b.items()), outcome="backfill"), dict(sorted(a.items()), outcome="live")]
    r = rv.pull()
    assert r == {"log": 3, "added": 1, "only_local": 0}
    lines = (tmp_path / "checks.jsonl").read_text().splitlines(keepends=True)
    assert "".join(lines[1:]) == text                         # same-second local order and bytes kept
    assert json.loads(lines[0])["entry_id"] == "rc-m" and "outcome" not in json.loads(lines[0])
    assert rv.pull()["added"] == 0
    assert (tmp_path / "checks.jsonl").read_text().splitlines(keepends=True) == lines


# ---- publisher ------------------------------------------------------------------------
def test_full_replace_refuses_without_the_shared_log(monkeypatch):
    monkeypatch.setattr(store, "configured", lambda: False)
    with pytest.raises(SystemExit, match="not configured"):
        pub.main(["--allow-db-write"])
