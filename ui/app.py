"""Web UI for the scraper-writing agent.

Run:  python ui/app.py        ->  http://localhost:5000

Type a domain, watch the agent's live reasoning timeline (streamed from the
run's trace.jsonl), then inspect/download the generated scraper + JSONL.
The agent itself is untouched -- this is a thin viewer + launcher.
"""
import json
import os
import sys
import threading
import time

from flask import Flask, jsonify, render_template, request, send_from_directory

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent.orchestrator import run_domain  # noqa: E402

app = Flask(__name__)

_runs = {}          # domain -> {"thread": Thread, "status": "running"|"done"|"error", "error": str|None}
_runs_lock = threading.Lock()

_ALLOWED_FILES = {"scraper.py", "output.jsonl", "trace.jsonl", "report.md", "report.json", "linkedin_jobs.jsonl"}


def _normalize_domain(raw):
    d = (raw or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/")[0].strip()
    if d.startswith("www."):
        d = d[4:]
    if d and "." not in d:
        d = d + ".com"
    return d


def _out_dir(domain):
    return os.path.join(ROOT, "generated", domain.replace("/", "_"))


def _avg_past_wall_clock():
    """Self-learned ETA baseline: average wall_clock_sec across every past run's own report.json
    (the agent's own cost report, not a hardcoded estimate). Falls back to a generic default
    when there is no history yet (fresh install / first-ever run)."""
    gen_dir = os.path.join(ROOT, "generated")
    durations = []
    if os.path.isdir(gen_dir):
        for name in os.listdir(gen_dir):
            rp = os.path.join(gen_dir, name, "report.json")
            if not os.path.isfile(rp):
                continue
            try:
                with open(rp, encoding="utf-8") as f:
                    r = json.load(f)
                sec = (r.get("cost_report") or {}).get("wall_clock_sec")
                if sec:
                    durations.append(sec)
            except (json.JSONDecodeError, OSError):
                continue
    if not durations:
        return 120.0
    return sum(durations) / len(durations)


def _run_in_thread(domain):
    try:
        run_domain(domain)
        with _runs_lock:
            _runs[domain]["status"] = "done"
    except Exception as e:
        with _runs_lock:
            _runs[domain]["status"] = "error"
            _runs[domain]["error"] = str(e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    domain = _normalize_domain((request.get_json(silent=True) or {}).get("domain"))
    if not domain:
        return jsonify({"ok": False, "error": "enter a domain, e.g. swissre.com"}), 400
    with _runs_lock:
        existing = _runs.get(domain)
        if existing and existing["status"] == "running":
            return jsonify({"ok": False, "error": f"{domain} is already running"}), 409
        # fresh run: clear the old trace so the timeline starts clean
        trace_path = os.path.join(_out_dir(domain), "trace.jsonl")
        if os.path.exists(trace_path):
            try:
                os.remove(trace_path)
            except OSError:
                pass
        report_path = os.path.join(_out_dir(domain), "report.json")
        if os.path.exists(report_path):
            try:
                os.remove(report_path)
            except OSError:
                pass
        t = threading.Thread(target=_run_in_thread, args=(domain,), daemon=True)
        _runs[domain] = {"thread": t, "status": "running", "error": None, "started_at": time.time()}
        t.start()
    return jsonify({"ok": True, "domain": domain, "eta_sec": round(_avg_past_wall_clock(), 1)})


def _read_trace_events(domain):
    """Compact view of trace.jsonl for the timeline (skip giant llm_call payloads),
    plus per-stage cost/latency/call aggregates for the stage tracker."""
    path = os.path.join(_out_dir(domain), "trace.jsonl")
    events, llm_calls, tool_calls = [], 0, 0
    stage_stats = {}   # stage -> {first_ts, last_ts, cost_usd, in_tokens, out_tokens, llm_calls, tool_calls}

    def _stat(stage, ts):
        s = stage_stats.setdefault(stage, {"first_ts": ts, "last_ts": ts, "cost_usd": 0.0,
                                           "in_tokens": 0, "out_tokens": 0,
                                           "llm_calls": 0, "tool_calls": 0})
        if ts:
            s["first_ts"] = min(s["first_ts"], ts) if s["first_ts"] else ts
            s["last_ts"] = max(s["last_ts"], ts) if s["last_ts"] else ts
        return s

    if not os.path.exists(path):
        return events, llm_calls, tool_calls, stage_stats
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            etype = e.get("type")
            stage = e.get("stage")
            if stage and "." in stage:  # fold agentic-loop sub-steps (e.g. discovery.step3) into parent
                stage = stage.split(".", 1)[0]
            ts = e.get("ts")
            if stage and stage not in ("run_start", "run_end"):
                st = _stat(stage, ts)
                if etype == "llm_call":
                    st["llm_calls"] += 1
                    st["cost_usd"] += e.get("cost_usd") or 0
                    usage = e.get("usage") or {}
                    st["in_tokens"] += usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                    st["out_tokens"] += usage.get("completion_tokens") or usage.get("output_tokens") or 0
                elif etype == "tool_call":
                    st["tool_calls"] += 1
            if etype == "llm_call":
                llm_calls += 1
                continue
            if etype == "tool_call":
                tool_calls += 1
                inp = e.get("input") or {}
                url = inp.get("url") or inp.get("query") or ""
                events.append({"type": "tool_call", "stage": e.get("stage"),
                               "tool": e.get("tool"), "detail": str(url)[:160]})
            elif etype == "stage":
                events.append({"type": "stage", "stage": e.get("stage"),
                               "detail": (e.get("detail") or "")[:200]})
            elif etype == "decision":
                events.append({"type": "decision", "stage": e.get("stage"),
                               "decision": str(e.get("decision"))[:300],
                               "evidence": [str(x)[:220] for x in (e.get("evidence") or [])[:6]],
                               "confidence": e.get("confidence")})
            elif etype == "reasoning":
                events.append({"type": "reasoning", "stage": e.get("stage"),
                               "detail": (e.get("text") or "")[:300]})
            elif etype == "error":
                events.append({"type": "error", "stage": e.get("stage"),
                               "detail": (e.get("message") or "")[:300]})
    return events, llm_calls, tool_calls, stage_stats


@app.route("/api/status/<domain>")
def api_status(domain):
    domain = _normalize_domain(domain)
    with _runs_lock:
        run = _runs.get(domain)
    run_status = run["status"] if run else None
    events, llm_calls, tool_calls, stage_stats = _read_trace_events(domain)
    now = time.time()
    stages = []
    for name, s in stage_stats.items():
        end = s["last_ts"]
        # while the run is live, the most recent stage is still ticking
        stages.append({
            "stage": name,
            "seconds": round(max(0.0, (end or now) - (s["first_ts"] or now)), 1),
            "cost_usd": round(s["cost_usd"], 4),
            "in_tokens": s["in_tokens"],
            "out_tokens": s["out_tokens"],
            "llm_calls": s["llm_calls"],
            "tool_calls": s["tool_calls"],
            "first_ts": s["first_ts"],
        })
    stages.sort(key=lambda x: x["first_ts"] or 0)
    if run_status == "running" and stages:
        stages[-1]["seconds"] = round(max(0.0, now - (stage_stats[stages[-1]["stage"]]["first_ts"] or now)), 1)
        stages[-1]["active"] = True

    report = None
    report_path = os.path.join(_out_dir(domain), "report.json")
    # only surface the report once the run finished -- an old report from a prior run was deleted at start
    if run_status in ("done", "error", None) and os.path.exists(report_path):
        try:
            with open(report_path, encoding="utf-8") as f:
                report = json.load(f)
        except (json.JSONDecodeError, OSError):
            report = None

    jobs = []
    if report:
        out_path = os.path.join(_out_dir(domain), "output.jsonl")
        if os.path.exists(out_path):
            with open(out_path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= 100:
                        break
                    try:
                        j = json.loads(line)
                        j.pop("job_description", None)  # table doesn't show it; keeps payload small
                        jobs.append(j)
                    except json.JSONDecodeError:
                        continue

    linkedin_jobs = []
    if report:
        li_path = os.path.join(_out_dir(domain), "linkedin_jobs.jsonl")
        if os.path.exists(li_path):
            with open(li_path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= 50:
                        break
                    try:
                        j = json.loads(line)
                        j.pop("job_description", None)
                        linkedin_jobs.append(j)
                    except json.JSONDecodeError:
                        continue

    files = []
    if os.path.isdir(_out_dir(domain)):
        files = [n for n in _ALLOWED_FILES if os.path.exists(os.path.join(_out_dir(domain), n))]

    scraper_code = None
    scraper_path = os.path.join(_out_dir(domain), "scraper.py")
    if report and os.path.exists(scraper_path):
        try:
            with open(scraper_path, encoding="utf-8") as f:
                scraper_code = f.read()
        except OSError:
            scraper_code = None

    elapsed_sec = None
    eta_sec = None
    avg_sec = None
    if run and run.get("started_at"):
        elapsed_sec = round(now - run["started_at"], 1)
        if run_status == "running":
            avg_sec = round(_avg_past_wall_clock(), 1)
            eta_sec = round(max(0.0, avg_sec - elapsed_sec), 1)

    return jsonify({
        "domain": domain,
        "run_status": run_status,
        "run_error": run.get("error") if run else None,
        "elapsed_sec": elapsed_sec,
        "eta_sec": eta_sec,
        "avg_sec": avg_sec,
        "events": events,
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "stage_stats": stages,
        "report": report,
        "jobs": jobs,
        "linkedin_jobs": linkedin_jobs,
        "files": files,
        "scraper_code": scraper_code,
    })


@app.route("/api/file/<domain>/<name>")
def api_file(domain, name):
    domain = _normalize_domain(domain)
    if name not in _ALLOWED_FILES:
        return jsonify({"error": "unknown file"}), 404
    return send_from_directory(_out_dir(domain), name, as_attachment=True)


if __name__ == "__main__":
    print("Agent UI ->  http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
