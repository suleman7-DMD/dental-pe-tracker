"""Shared rapid-validation store: stdlib HTTPS calls to the Supabase rapid_* functions.

Sessions (a local terminal or a Claude Code cloud VM) never hold the Supabase secret key. They
need three values, from the environment or the repo's .env:
  SUPABASE_URL       (or NEXT_PUBLIC_SUPABASE_URL)       https://<project>.supabase.co
  SUPABASE_ANON_KEY  (or NEXT_PUBLIC_SUPABASE_ANON_KEY)  the public key the website already uses
  RAPID_TOKEN        a token directory_web_checks_publish.py --new-token issued; it can only call
                     the rapid_* functions (scrapers/directory_web_checks_store.sql)
No third-party packages: the cloud VM may not have requests installed.
"""
import json
import os
import pathlib
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


class StoreError(RuntimeError):
    pass


def load_env():
    """Fill os.environ from the first .env found (never overrides values already set)."""
    for base in (os.environ.get("OFFICE_CENSUS_INPUT_ROOT"), ROOT, pathlib.Path.home() / "dental-pe-tracker"):
        env = pathlib.Path(base) / ".env" if base else None
        if env and env.is_file():
            break
    else:
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def settings():
    load_env()
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    return (url or "").rstrip("/"), key or "", os.environ.get("RAPID_TOKEN") or ""


def missing():
    url, key, tok = settings()
    return [n for n, v in (("SUPABASE_URL", url), ("SUPABASE_ANON_KEY", key), ("RAPID_TOKEN", tok)) if not v]


def configured():
    return not missing()


def _ssl_context():
    ca = next((os.environ[k] for k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE")
               if os.environ.get(k) and pathlib.Path(os.environ[k]).is_file()), None)
    return ssl.create_default_context(cafile=ca)


def _curl(method, url, headers, data, timeout):
    """Fallback when Python's TLS stack rejects a proxy certificate that curl accepts."""
    with tempfile.TemporaryDirectory() as d:
        cfg = pathlib.Path(d) / "cfg"
        lines = [f'url = "{url}"', f'request = "{method}"', "silent", "show-error",
                 f"max-time = {int(timeout)}", 'write-out = "\\n%{http_code}"']
        lines += [f'header = "{k}: {v}"' for k, v in headers.items()]
        if data is not None:
            body = pathlib.Path(d) / "body"
            body.write_bytes(data)
            lines.append(f'data-binary = "@{body}"')
        cfg.write_text("\n".join(lines) + "\n")
        out = subprocess.run(["curl", "-K", str(cfg)], capture_output=True, timeout=timeout + 10)
    if out.returncode != 0:
        raise StoreError(f"curl failed: {out.stderr.decode(errors='replace').strip()[:200]}")
    body, _, code = out.stdout.rpartition(b"\n")
    return int(code or 0), body


def request(method, path, body=None, headers=None, timeout=60, attempts=4):
    """-> (status, headers, parsed JSON or None). Retries network errors, 429 and 5xx."""
    url, key, _ = settings()
    if not url or not key:
        raise StoreError("SUPABASE_URL / SUPABASE_ANON_KEY not set")
    hdr = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json",
           "Accept": "application/json", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    err = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(min(2 ** attempt, 10))
        try:
            req = urllib.request.Request(url + path, data=data, method=method, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
                status, rh, raw = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            status, rh, raw = e.code, dict(e.headers or {}), e.read()
        except (urllib.error.URLError, OSError) as e:
            err = e
            reason = getattr(e, "reason", e)
            if isinstance(reason, ssl.SSLError) or isinstance(e, ssl.SSLError):
                try:
                    status, raw = _curl(method, url + path, hdr, data, timeout)
                    rh = {}
                except (StoreError, OSError, subprocess.SubprocessError) as ce:
                    err = ce
                    continue
            else:
                continue
        if status == 429 or status >= 500:
            err = StoreError(f"HTTP {status}: {raw[:200].decode(errors='replace')}")
            continue
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw.decode(errors="replace")
        return status, rh, parsed
    raise StoreError(f"Supabase unreachable after {attempts} attempts: {err}")


def rpc(name, **params):
    _, _, tok = settings()
    status, _, out = request("POST", f"/rest/v1/rpc/{name}", {"p_token": tok, **params})
    if status >= 400:
        msg = out.get("message") if isinstance(out, dict) else out
        raise StoreError(f"{name}: HTTP {status}: {msg}")
    return out


def count(table, **filters):
    """Exact row count through PostgREST as anon (what the website sees)."""
    q = "&".join(["select=location_id"] + [f"{k}={v}" for k, v in filters.items()])
    status, rh, _ = request("GET", f"/rest/v1/{table}?{q}", headers={"Prefer": "count=exact", "Range": "0-0"})
    rng = {k.lower(): v for k, v in rh.items()}.get("content-range", "")
    if status >= 400 or "/" not in rng:
        return f"HTTP {status}"
    return int(rng.split("/")[-1])
