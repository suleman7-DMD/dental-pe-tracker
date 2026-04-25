"""
Research Engine — Qualitative intelligence via Claude API + web search.

Powers both ZIP-Level Scout and Practice-Level Deep Dive tools.

COST OPTIMIZATION (March 2026 pricing):
1. Haiku 4.5 default ($1/$5 per M tokens vs Sonnet $3/$15) — 65% token savings
2. Prompt caching — system prompts cached at 10% rate after first call
3. JSON-only output — no prose, minimal output tokens (output = 5x input cost)
4. Batch API for weekly runs — flat 50% discount
5. Two-pass: Haiku scans all, Sonnet only escalates on high-value targets

Estimated per-call costs (Haiku):
  ZIP Scout:  ~$0.04-0.06/ZIP
  Practice:   ~$0.08-0.12/practice
  
Monthly at moderate scale (50 ZIPs + 100 practices): ~$15-20
"""

import json
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from scrapers.logger_config import get_logger

logger = get_logger("research_engine")

MODEL_HAIKU = "claude-haiku-4-5-20251001"
MODEL_SONNET = "claude-sonnet-4-6"
DEFAULT_MODEL = MODEL_HAIKU

MAX_TOKENS_HAIKU = 3000
MAX_TOKENS_SONNET = 4096
MIN_REQUEST_INTERVAL = 30.0
DEFAULT_CACHE_TTL_DAYS = 90

_last_req_time = 0.0

# ── System Prompts (cached after first call = 90% savings) ───────────────

ZIP_SYSTEM = """You are a dental market analyst. Research the given ZIP code for a dental practice buyer.
Search the web for CURRENT, REAL data. If you can't find something, return null — never fabricate.
Return ONLY raw JSON (no markdown, no explanation). Keep values concise — 1-2 sentences max per field.
Lists max 5 items. This is cost-sensitive — minimize output tokens."""

ZIP_USER = """Research ZIP {zip_code} ({city}, {state}) for dental practice investment.
Return JSON:
{{"housing":{{"status":"active|moderate|stagnant|unknown","developments":[],"summary":""}},"schools":{{"district":"","rating":"","source":"","note":""}},"retail":{{"premium":[],"mass":[],"income_signal":""}},"commercial":{{"status":"","projects":[],"note":""}},"dental_news":{{"new_offices":[],"dso_moves":[],"note":""}},"real_estate":{{"median_price":null,"trend":"","yoy_pct":null,"source":""}},"zoning":{{"items":[],"note":""}},"population":{{"growth_signals":[],"demographics":"","note":""}},"employers":{{"major_nearby":[],"insurance_signal":""}},"competitors":{{"new_opens":[],"closures":[],"note":""}},"demand_outlook":"","supply_outlook":"","investment_thesis":"","confidence":"high|medium|low","sources":[]}}"""

PRACTICE_SYSTEM = """You are conducting PE-style due diligence on a dental practice.
Search the web for CURRENT, REAL data about this specific practice and doctor.
If you can't find something, return null — never fabricate.
Return ONLY raw JSON (no markdown, no explanation). Concise values only.
Cost-sensitive — minimize output tokens."""

PRACTICE_USER = """Research this dental practice:
Name: {name}
Address: {address}, {city}, {state} {zip}
Doctor: {doctor_name}
{extra_context}
Return JSON:
{{"website":{{"url":"","era":"modern|dated|template|none|unknown","last_update":"","analysis":""}},"services":{{"listed":[],"high_revenue":[],"note":""}},"technology":{{"listed":[],"level":"high|moderate|basic|unknown"}},"providers":{{"web_count":null,"owner_stage":"late|mid|early|unknown","notes":""}},"google":{{"reviews":null,"rating":null,"recent_date":"","velocity":"active|moderate|stale|unknown","sentiment":""}},"hiring":{{"active":false,"positions":[],"source":""}},"acquisition_news":{{"found":false,"details":""}},"social":{{"facebook":"active|inactive|none","instagram":"active|inactive|none","other":""}},"healthgrades":{{"rating":null,"reviews":null}},"zocdoc":{{"listed":false}},"doctor":{{"publications":false,"speaking":false,"associations":[],"notes":""}},"insurance":{{"medicaid":null,"ppo_heavy":null,"note":""}},"red_flags":[],"green_flags":[],"assessment":"","readiness":"high|medium|low|unlikely|unknown","confidence":"high|medium|low","sources":[]}}"""

JOB_HUNT_SYSTEM = """You are a dental career advisor helping new DDS/DMD graduates evaluate first-job opportunities.
Search the web for CURRENT, REAL data about this specific practice. If you can't find something, return null — never fabricate.
Return ONLY raw JSON (no markdown, no explanation). Concise values only.
Cost-sensitive — minimize output tokens."""

JOB_HUNT_PRACTICE_USER = """Evaluate this dental practice as a first-job opportunity for a new DDS/DMD graduate:
Name: {name}
Address: {address}, {city}, {state} {zip}
Doctor: {doctor_name}
{extra_context}
Return JSON:
{{"website":{{"url":"","era":"modern|dated|template|none|unknown","last_update":"","analysis":""}},"services":{{"listed":[],"high_revenue":[],"note":""}},"technology":{{"listed":[],"level":"high|moderate|basic|unknown"}},"providers":{{"web_count":null,"owner_stage":"late|mid|early|unknown","notes":""}},"google":{{"reviews":null,"rating":null,"recent_date":"","velocity":"active|moderate|stale|unknown","sentiment":""}},"hiring":{{"active":false,"positions":[],"source":""}},"acquisition_news":{{"found":false,"details":""}},"social":{{"facebook":"active|inactive|none","instagram":"active|inactive|none","other":""}},"healthgrades":{{"rating":null,"reviews":null}},"zocdoc":{{"listed":false}},"doctor":{{"publications":false,"speaking":false,"associations":[],"notes":""}},"insurance":{{"medicaid":null,"ppo_heavy":null,"note":""}},"red_flags":[],"green_flags":[],"assessment":"","readiness":"high|medium|low|unlikely|unknown","confidence":"high|medium|low","sources":[],"succession_intent":"active_seeking|receptive|unclear|not_considering|unknown","new_grad_friendly_score":null,"mentorship_signals":[],"associate_runway":"immediate|0-2 years|2-5 years|succession path|unclear","compensation_signals":{{"base_est_usd":null,"production_pct_est":null,"benefits_quality":"strong|standard|thin|unknown"}},"red_flags_for_grad":[],"green_flags_for_grad":[]}}"""


ESCALATION_SYSTEM = """You are a senior dental PE analyst. You have initial scan results.
Conduct DEEPER follow-up research on this high-priority target.
Verify key findings, search for missed information, provide nuanced assessment.
Return ONLY raw JSON, same structure as input but with deeper verified data.
Add "escalation_findings" key with new discoveries."""


CIRCUIT_BREAKER_THRESHOLD = 10  # Consecutive failures before aborting


class CircuitBreakerOpen(Exception):
    """Raised when too many consecutive API failures occur."""
    pass


class ResearchEngine:
    """
    Core research engine. Three execution modes:
    1. Synchronous — immediate results (CLI, dashboard buttons)
    2. Batch — 50% token discount (weekly automated runs)
    3. Two-pass — Haiku scan + Sonnet deep dive on flagged targets
    """

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or DEFAULT_MODEL
        self.max_tokens = MAX_TOKENS_HAIKU if "haiku" in self.model else MAX_TOKENS_SONNET
        self._consecutive_failures = 0
        if not self.api_key:
            logger.warning("No ANTHROPIC_API_KEY set. export ANTHROPIC_API_KEY='sk-ant-...'")

    def _rate_limit(self):
        global _last_req_time
        elapsed = time.time() - _last_req_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        _last_req_time = time.time()

    def _call_api(self, system, user_msg, model=None, max_tokens=None,
                  max_searches=8):
        """Single API call with web search + prompt caching."""
        if self._consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
            msg = (f"Circuit breaker open: {self._consecutive_failures} consecutive "
                   f"API failures. Aborting to prevent 290 items x 120s timeout.")
            logger.error(msg)
            raise CircuitBreakerOpen(msg)

        try:
            import requests as req
        except ImportError:
            return {"error": "requests library not installed: pip install requests"}

        if not self.api_key:
            return {"error": "No API key. Set ANTHROPIC_API_KEY env var."}

        self._rate_limit()
        _model = model or self.model
        _max = max_tokens or self.max_tokens

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        body = {
            "model": _model,
            "max_tokens": _max,
            "system": [{"type": "text", "text": system,
                        "cache_control": {"type": "ephemeral"}}],
            "tools": [{"type": "web_search_20250305", "name": "web_search",
                       "max_uses": max_searches}],
            "messages": [{"role": "user", "content": user_msg}]
        }

        try:
            resp = req.post("https://api.anthropic.com/v1/messages",
                           headers=headers, json=body, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            text_parts = [b["text"] for b in data.get("content", [])
                         if b.get("type") == "text"]
            raw = "\n".join(text_parts).strip()

            usage = data.get("usage", {})
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cache_r = usage.get("cache_read_input_tokens", 0)
            cache_c = usage.get("cache_creation_input_tokens", 0)

            if "haiku" in _model:
                cost = (inp * 1.0 + out * 5.0 + cache_r * 0.1 + cache_c * 1.25) / 1e6
            else:
                cost = (inp * 3.0 + out * 15.0 + cache_r * 0.3 + cache_c * 3.75) / 1e6

            logger.info(f"API: {_model} in={inp} out={out} cache={cache_r} ${cost:.4f}")

            parsed = self._parse_json(raw)
            meta = {"model": _model, "input_tokens": inp, "output_tokens": out,
                    "cache_read": cache_r, "cost_usd": round(cost, 4),
                    "timestamp": datetime.now().isoformat()}
            if parsed:
                parsed["_meta"] = meta
                self._consecutive_failures = 0
                return parsed
            return {"error": "JSON parse failed", "raw": raw[:2000], "_meta": meta}

        except CircuitBreakerOpen:
            raise
        except Exception as e:
            self._consecutive_failures += 1
            logger.error(f"API error ({self._consecutive_failures}/{CIRCUIT_BREAKER_THRESHOLD}): {e}")
            return {"error": str(e)}

    def _parse_json(self, text):
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [l for l in lines[1:] if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            s, e = cleaned.find("{"), cleaned.rfind("}") + 1
            if s >= 0 and e > s:
                try:
                    return json.loads(cleaned[s:e])
                except json.JSONDecodeError:
                    pass
        return None

    # ── ZIP Research ─────────────────────────────────────────────────────

    def research_zip(self, zip_code, city, state, model=None):
        msg = ZIP_USER.format(zip_code=zip_code, city=city, state=state)
        r = self._call_api(ZIP_SYSTEM, msg, model=model)
        r["_type"] = "zip"
        r["_zip"] = zip_code
        return r

    # ── Practice Research ────────────────────────────────────────────────

    def research_practice(self, npi, name, address, city, state, zip_code,
                         doctor_name=None, extra_context=None, model=None):
        msg = PRACTICE_USER.format(
            name=name, address=address, city=city, state=state,
            zip=zip_code, doctor_name=doctor_name or "Unknown",
            extra_context=extra_context or "")
        r = self._call_api(PRACTICE_SYSTEM, msg, model=model, max_searches=4)
        r["_type"] = "practice"
        r["_npi"] = npi
        return r


    def research_practice_jobhunt(self, name: str, address: str, city: str,
                                   state: str, zip_code: str,
                                   doctor_name: Optional[str] = None,
                                   extra_context: Optional[str] = None) -> Dict[str, Any]:
        """Job-hunt focused research — returns practice intel with grad-specific signals.

        Uses JOB_HUNT_SYSTEM + JOB_HUNT_PRACTICE_USER prompts tuned for new DDS/DMD
        graduates evaluating first-job opportunities. Returns all standard PRACTICE fields
        plus: succession_intent, new_grad_friendly_score, mentorship_signals,
        associate_runway, compensation_signals, red_flags_for_grad, green_flags_for_grad.

        NOTE: Does NOT call the API internally — use build_batch_requests_jobhunt() for
        batch runs or call _call_api() directly for synchronous single-practice research.
        """
        msg = JOB_HUNT_PRACTICE_USER.format(
            name=name, address=address, city=city, state=state,
            zip=zip_code, doctor_name=doctor_name or "Unknown",
            extra_context=extra_context or "")
        r = self._call_api(JOB_HUNT_SYSTEM, msg, model=MODEL_HAIKU,
                           max_tokens=1500, max_searches=4)
        r["_type"] = "practice_jobhunt"
        return r

    # ── Two-Pass Escalation ──────────────────────────────────────────────

    def research_practice_deep(self, npi, name, address, city, state,
                               zip_code, doctor_name=None, extra_context=None):
        """Haiku scan → conditional Sonnet escalation for high-value targets."""
        logger.info(f"Pass 1 (Haiku): {name}")
        p1 = self.research_practice(npi, name, address, city, state, zip_code,
                                     doctor_name, extra_context, model=MODEL_HAIKU)
        if "error" in p1 and "_meta" not in p1:
            return p1

        if not self._should_escalate(p1):
            p1["_escalated"] = False
            return p1

        logger.info(f"Pass 2 (Sonnet): {name}")
        esc_msg = (f"Initial scan for {name} at {address}, {city} {state} {zip_code}:\n"
                   f"{json.dumps(p1, default=str)[:3000]}\n\n"
                   "Deeper research needed. Verify Google reviews, search for hiring "
                   "signals, news, technology investments, real estate at this address. "
                   "Return same JSON structure with verified/deeper data.")
        p2 = self._call_api(ESCALATION_SYSTEM, esc_msg,
                           model=MODEL_SONNET, max_tokens=MAX_TOKENS_SONNET)
        merged = self._merge(p1, p2)
        merged["_escalated"] = True
        merged["_pass1_cost"] = p1.get("_meta", {}).get("cost_usd", 0)
        merged["_pass2_cost"] = p2.get("_meta", {}).get("cost_usd", 0)
        return merged

    def _should_escalate(self, r):
        readiness = r.get("readiness", r.get("acquisition_readiness", "unknown"))
        if readiness in ("unlikely", "unknown"):
            return False  # Never escalate non-targets
        confidence = r.get("confidence", "low")
        greens = r.get("green_flags", [])
        if readiness in ("high", "medium") and confidence != "high":
            return True
        if len(greens) >= 3:
            return True
        return False

    def _merge(self, p1, p2):
        m = dict(p1)
        for k, v in p2.items():
            if k.startswith("_") or v is None:
                continue
            if isinstance(v, dict) and isinstance(m.get(k), dict):
                for k2, v2 in v.items():
                    if v2 is not None:
                        m[k][k2] = v2
            elif isinstance(v, list) and isinstance(m.get(k), list):
                m[k] = m[k] + [x for x in v if x not in m[k]]
            elif isinstance(v, str) and v.strip():
                m[k] = v
            elif v is not None:
                m[k] = v
        m["_meta"] = p2.get("_meta", p1.get("_meta", {}))
        return m


    def build_batch_requests_jobhunt(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build batch request list using JOB_HUNT prompts (50% token discount via Batch API).

        Each item must have: name, address, city, state, zip, npi.
        Optional per-item: doctor_name, extra_context.

        Returns list of batch request dicts compatible with submit_batch().
        """
        reqs = []
        for item in items:
            msg = JOB_HUNT_PRACTICE_USER.format(
                name=item["name"], address=item["address"],
                city=item["city"], state=item["state"],
                zip=item["zip"], doctor_name=item.get("doctor_name", "Unknown"),
                extra_context=item.get("extra_context", ""))
            reqs.append({
                "custom_id": f"jobhunt_{item['npi']}",
                "params": {
                    "model": self.model,
                    "max_tokens": 1500,
                    "system": [{"type": "text", "text": JOB_HUNT_SYSTEM,
                               "cache_control": {"type": "ephemeral"}}],
                    "tools": [{"type": "web_search_20250305",
                              "name": "web_search", "max_uses": 4}],
                    "messages": [{"role": "user", "content": msg}]
                }
            })
        return reqs

    # ── Batch API ────────────────────────────────────────────────────────

    def build_batch_requests(self, items, research_type="zip"):
        """Build batch request list. research_type: 'zip' or 'practice'."""
        reqs = []
        for item in items:
            if research_type == "zip":
                msg = ZIP_USER.format(**item)
                sys = ZIP_SYSTEM
                cid = f"zip_{item['zip_code']}"
                ms = 8
            else:
                msg = PRACTICE_USER.format(
                    name=item["name"], address=item["address"],
                    city=item["city"], state=item["state"],
                    zip=item["zip"], doctor_name=item.get("doctor_name", "Unknown"),
                    extra_context=item.get("extra_context", ""))
                sys = PRACTICE_SYSTEM
                cid = f"practice_{item['npi']}"
                ms = 4

            reqs.append({
                "custom_id": cid,
                "params": {
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "system": [{"type": "text", "text": sys,
                               "cache_control": {"type": "ephemeral"}}],
                    "tools": [{"type": "web_search_20250305",
                              "name": "web_search", "max_uses": ms}],
                    "messages": [{"role": "user", "content": msg}]
                }
            })
        return reqs

    def submit_batch(self, requests):
        """Submit batch to Anthropic Batch API (50% token discount)."""
        try:
            import requests as req
        except ImportError:
            return {"error": "requests library required"}
        if not self.api_key:
            return {"error": "No API key"}

        headers = {"x-api-key": self.api_key,
                   "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        try:
            resp = req.post("https://api.anthropic.com/v1/messages/batches",
                           headers=headers, json={"requests": requests}, timeout=60)
            if resp.ok:
                d = resp.json()
                return {"batch_id": d.get("id"), "status": d.get("processing_status"),
                        "count": len(requests)}
            return {"error": f"{resp.status_code}: {resp.text[:300]}"}
        except Exception as e:
            return {"error": str(e)}

    def check_batch(self, batch_id):
        import requests as req
        resp = req.get(f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
                      headers={"x-api-key": self.api_key,
                              "anthropic-version": "2023-06-01"}, timeout=30)
        return resp.json() if resp.ok else {"error": resp.text[:300]}

    def get_batch_results(self, batch_id):
        import requests as req
        resp = req.get(f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
                      headers={"x-api-key": self.api_key,
                              "anthropic-version": "2023-06-01"},
                      timeout=60, stream=True)
        results = []
        if resp.ok:
            for line in resp.iter_lines():
                if line:
                    try:
                        r = json.loads(line)
                        texts = [b["text"] for b in
                                r.get("result",{}).get("message",{}).get("content",[])
                                if b.get("type") == "text"]
                        parsed = self._parse_json("\n".join(texts))
                        results.append({"id": r.get("custom_id"),
                                       "data": parsed or {"error": "parse failed"}})
                    except Exception as e:
                        logger.error(f"Batch parse error: {e}")
        return results


class CostTracker:
    """Tracks cumulative API spend. Persists to JSON file."""

    def __init__(self, path=None):
        self.path = path or os.path.expanduser(
            "~/dental-pe-tracker/data/research_costs.json")
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"total_usd": 0.0, "calls": 0, "zips": 0, "practices": 0,
                "months": {}, "log": []}

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def record(self, rtype, cost, model, target_id):
        mo = datetime.now().strftime("%Y-%m")
        self.data["total_usd"] = round(self.data["total_usd"] + cost, 4)
        self.data["calls"] += 1
        self.data["zips" if rtype == "zip" else "practices"] += 1
        self.data["months"][mo] = round(self.data["months"].get(mo, 0) + cost, 4)
        self.data["log"].append({"ts": datetime.now().isoformat(), "type": rtype,
                                 "target": target_id, "model": model, "cost": cost})
        if len(self.data["log"]) > 500:
            self.data["log"] = self.data["log"][-500:]
        self._save()

    def month_total(self, mo=None):
        return self.data["months"].get(mo or datetime.now().strftime("%Y-%m"), 0)

    def summary(self):
        return (f"${self.data['total_usd']:.2f} total "
                f"(${self.month_total():.2f} this month) | "
                f"{self.data['calls']} calls "
                f"({self.data['zips']} ZIPs, {self.data['practices']} practices)")
