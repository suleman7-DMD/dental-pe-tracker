"""
Structured pipeline event logger (JSON-Lines).

Writes append-only events to ~/dental-pe-tracker/logs/pipeline_events.jsonl
for consumption by the dashboard System Health tab.

Usage:
    from scrapers.pipeline_logger import log_scrape_start, log_scrape_complete, log_scrape_error

    t = log_scrape_start("pesp_scraper")
    # ... do work ...
    log_scrape_complete("pesp_scraper", t, new_records=12, summary="Found 12 new deals")
"""

import json
import os
import time
import fcntl
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE = os.environ.get(
    "DENTAL_PE_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
LOGS_DIR = os.path.join(_BASE, "logs")
LOG_FILE = os.path.join(LOGS_DIR, "pipeline_events.jsonl")

# Auto-rotation limits
_MAX_LINES = 1000
_TRIM_THRESHOLD = 1200  # trigger trim when file exceeds this many lines


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_log_dir():
    """Create the logs directory if it doesn't exist."""
    try:
        os.makedirs(LOGS_DIR, exist_ok=True)
    except (OSError, PermissionError):
        pass


def _now_iso() -> str:
    """Current local time as ISO-8601 string (no timezone suffix)."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _append_line(line: str):
    """
    Append a single line to the JSONL log file with file locking.

    Uses fcntl.LOCK_EX so concurrent scrapers don't interleave writes.
    After appending, checks whether the file has grown past _TRIM_THRESHOLD
    and truncates to the last _MAX_LINES if so.
    """
    _ensure_log_dir()

    try:
        with open(LOG_FILE, "a+", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.write(line + "\n")
                f.flush()

                # --- Auto-rotation check ---
                f.seek(0)
                all_lines = f.readlines()
                if len(all_lines) > _TRIM_THRESHOLD:
                    keep = all_lines[-_MAX_LINES:]
                    f.seek(0)
                    f.truncate()
                    f.writelines(keep)
                    f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except (OSError, PermissionError):
        # Silently degrade — logging should never crash a scraper
        pass


def _read_lines() -> list[str]:
    """Read all lines from the log file (empty list if missing)."""
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                lines = f.readlines()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        return lines
    except FileNotFoundError:
        return []
    except (OSError, PermissionError):
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def log_event(
    source: str,
    event: str,
    summary: str,
    details: dict = None,
    status: str = "success",
):
    """Append a structured event to the pipeline log."""
    record = {
        "timestamp": _now_iso(),
        "source": source,
        "event": event,
        "summary": summary,
        "details": details or {},
        "status": status,
    }
    _append_line(json.dumps(record, default=str))


def log_scrape_start(source: str) -> float:
    """
    Log the start of a scraping run.

    Returns the monotonic start time (seconds) for duration calculation.
    """
    log_event(
        source=source,
        event="scrape_start",
        summary=f"{source} run started",
        status="info",
    )
    return time.monotonic()


def log_scrape_complete(
    source: str,
    start_time: float,
    new_records: int = 0,
    updated_records: int = 0,
    summary: str = "",
    extra: dict = None,
):
    """Log completion of a scraping run with stats."""
    duration = round(time.monotonic() - start_time, 1) if start_time else 0

    details = {
        "new_records": new_records,
        "updated_records": updated_records,
        "duration_seconds": duration,
    }
    if extra:
        details.update(extra)

    if not summary:
        parts = []
        if new_records:
            parts.append(f"{new_records} new")
        if updated_records:
            parts.append(f"{updated_records} updated")
        summary = f"{source} complete: {', '.join(parts)}" if parts else f"{source} complete (no changes)"

    log_event(
        source=source,
        event="scrape_complete",
        summary=summary,
        details=details,
        status="success",
    )


def log_scrape_error(source: str, error: str, start_time: float = None):
    """Log a scraper error."""
    details = {"error": error}
    if start_time is not None:
        details["duration_seconds"] = round(time.monotonic() - start_time, 1)

    log_event(
        source=source,
        event="scrape_error",
        summary=f"{source} failed: {error[:120]}",
        details=details,
        status="error",
    )


def get_recent_events(limit: int = 50, source_filter: str = None) -> list[dict]:
    """
    Read the last N events from the log.

    Args:
        limit: Maximum number of events to return (default 50).
        source_filter: If provided, only return events from this source.

    Returns:
        List of dicts, most recent last.
    """
    lines = _read_lines()
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if source_filter and record.get("source") != source_filter:
            continue
        events.append(record)

    # Return the tail (most recent events)
    return events[-limit:]


def get_last_run_summary() -> dict:
    """
    Get a summary dict of the most recent run of each source.

    Returns:
        {
            "pesp_scraper": { <most recent event dict> },
            "gdn_scraper":  { <most recent event dict> },
            ...
        }

    Only considers scrape_complete and scrape_error events (not starts).
    """
    lines = _read_lines()
    latest: dict[str, dict] = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = record.get("event", "")
        if event_type in ("scrape_complete", "scrape_error"):
            source = record.get("source", "unknown")
            latest[source] = record

    return latest


# ---------------------------------------------------------------------------
# CLI debugging
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    events = get_recent_events(limit=20)
    if not events:
        print("No pipeline events found.")
        print(f"  Log file: {LOG_FILE}")
        raise SystemExit(0)

    # Column widths
    w_time = 19
    w_source = 22
    w_event = 16
    w_status = 8
    w_summary = 60

    header = (
        f"{'TIMESTAMP':<{w_time}}  "
        f"{'SOURCE':<{w_source}}  "
        f"{'EVENT':<{w_event}}  "
        f"{'STATUS':<{w_status}}  "
        f"{'SUMMARY':<{w_summary}}"
    )
    print(header)
    print("-" * len(header))

    for ev in events:
        ts = ev.get("timestamp", "")[:w_time]
        src = ev.get("source", "")[:w_source]
        evt = ev.get("event", "")[:w_event]
        st = ev.get("status", "")[:w_status]
        sm = ev.get("summary", "")[:w_summary]
        print(
            f"{ts:<{w_time}}  "
            f"{src:<{w_source}}  "
            f"{evt:<{w_event}}  "
            f"{st:<{w_status}}  "
            f"{sm:<{w_summary}}"
        )

    print(f"\n({len(events)} events shown from {LOG_FILE})")
