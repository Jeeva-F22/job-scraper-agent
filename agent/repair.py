"""Stage 7: Repair loop. Feeds validator failures back to the code generator so the
LLM patches the actual root cause, capped at MAX_ATTEMPTS so a broken site can't
spin forever -- an honest failure report after exhausting attempts is a valid outcome.
"""
from . import codegen

MAX_ATTEMPTS = 3


def build_repair_context(sandbox_result, validate_result, current_code):
    return (
        f"Validation outcome: {validate_result['outcome']}\n"
        f"Reasons:\n" + "\n".join(f"- {r}" for r in validate_result["reasons"]) + "\n"
        f"Checks: {validate_result['checks']}\n"
        f"Sandbox exit_code={sandbox_result['exit_code']} timed_out={sandbox_result['timed_out']}\n"
        f"stdout (tail): {sandbox_result['stdout'][-1000:]}\n"
        f"stderr (tail): {sandbox_result['stderr'][-1000:]}\n\n"
        f"Current script (fix this, don't rewrite from scratch unless the approach itself is wrong):\n"
        f"```python\n{current_code[:6000]}\n```"
    )


def repair(plan, discovery_result, re_result, domain, llm, trace, out_dir,
           sandbox_result, validate_result, current_code):
    trace.stage("repair", f"Repairing scraper (reasons: {validate_result['reasons']})")
    repair_context = build_repair_context(sandbox_result, validate_result, current_code)
    path, code = codegen.generate(
        plan, discovery_result, re_result, domain, llm, trace, out_dir,
        repair_context=repair_context,
    )
    return path, code
