"""Cross-run platform memory -- entirely agent-authored, never human-edited.

After a successful run, the agent writes its own fingerprint signature + the plan +
scraper code it just verified works to platform_memory.json. On a future domain that
fingerprints to the same platform, that entry is offered to the architect/codegen
stages as a *starting-point hint* -- it is still independently re-validated against
the new domain's own reverse-engineering evidence, never blindly reused. This is the
efficiency mechanism (§ stretch goal: cross-run memory) and it satisfies constraint #2
because every line in this file was written by the LLM at runtime, never by a human.
"""
import json
import os

_DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "platform_memory.json")


def load(path=_DEFAULT_PATH):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def get_hint(platform, path=_DEFAULT_PATH):
    mem = load(path)
    entry = mem.get(platform)
    if not entry:
        return None, None
    return entry.get("plan"), entry.get("scraper_code")


def record_success(platform, domain, plan, scraper_code, validate_result, cost_dict, path=_DEFAULT_PATH):
    mem = load(path)
    entry = mem.get(platform, {"success_count": 0, "domains_seen": []})
    entry["success_count"] = entry.get("success_count", 0) + 1
    entry["domains_seen"] = list(set(entry.get("domains_seen", []) + [domain]))[-20:]
    entry["plan"] = plan
    entry["scraper_code"] = scraper_code
    entry["last_validate_score"] = validate_result.get("score")
    entry["last_job_count"] = validate_result.get("job_count")
    entry["last_cost_usd"] = cost_dict.get("cost_usd")
    mem[platform] = entry
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return entry
