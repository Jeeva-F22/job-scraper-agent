"""OpenAI wrapper: single-shot structured calls + a generic tool-calling agentic loop.

The agentic loop is the core "agentic not fixed pipeline" mechanism (§3 rule 1):
at each step the LLM itself picks which tool to call next (or to finish), based
on what it has seen so far. The orchestrator stages just supply the tool menu.
"""
import json
import os
import time

from openai import BadRequestError, OpenAI


def _shape_tool_result_for_llm(result, budget=14000):
    """Naive whole-JSON truncation silently drops trailing keys (e.g. `links`) when a leading
    key (e.g. `markdown`/`html`) is large -- the model then never sees navigation data that was
    right there in the tool output. Shrink known-bulky text fields first, keep structural/list
    fields (links, evidence, etc.) intact, then fall back to a final hard slice as a safety net.
    """
    if not isinstance(result, dict):
        text = json.dumps(result, ensure_ascii=False, default=str)
        return text[:budget]
    shaped = dict(result)
    if "links" in shaped and isinstance(shaped["links"], list) and len(shaped["links"]) > 200:
        shaped["links"] = shaped["links"][:200] + [f"... [{len(shaped['links']) - 200} more links truncated]"]
    if "html" in shaped and isinstance(shaped["html"], str):
        shaped["html"] = shaped["html"][:1500] + ("... [truncated; use grep_text/extract_hydration_json for more]" if len(result["html"]) > 1500 else "")
    if "markdown" in shaped and isinstance(shaped["markdown"], str):
        shaped["markdown"] = shaped["markdown"][:3000] + ("... [truncated]" if len(result["markdown"]) > 3000 else "")
    if "text" in shaped and isinstance(shaped["text"], str) and len(shaped["text"]) > 4000:
        shaped["text"] = shaped["text"][:4000] + "... [truncated]"
    text = json.dumps(shaped, ensure_ascii=False, default=str)
    if len(text) <= budget:
        return text
    return text[:budget]

# Rough per-1M-token USD pricing, used only for the cost report -- not billing-accurate.
_PRICING = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o4-mini": (1.10, 4.40),
}


def _price_for(model):
    for key, price in _PRICING.items():
        if model.startswith(key):
            return price
    return (2.50, 10.00)


class CostTracker:
    def __init__(self):
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.tool_calls = 0
        self.retries = 0
        self.start_time = time.time()

    def add_llm(self, usage, model):
        in_price, out_price = _price_for(model)
        it = usage.prompt_tokens if usage else 0
        ot = usage.completion_tokens if usage else 0
        self.calls += 1
        self.input_tokens += it
        self.output_tokens += ot
        self.cost_usd += (it / 1_000_000) * in_price + (ot / 1_000_000) * out_price
        return (it / 1_000_000) * in_price + (ot / 1_000_000) * out_price

    def add_tool(self):
        self.tool_calls += 1

    def add_retry(self):
        self.retries += 1

    def as_dict(self):
        return {
            "llm_calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 5),
            "tool_calls": self.tool_calls,
            "repair_retries": self.retries,
            "wall_clock_sec": round(time.time() - self.start_time, 2),
        }


class LLM:
    def __init__(self, cost_tracker=None, model=None):
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")
        self.cost = cost_tracker or CostTracker()
        # Some flagship reasoning-tier models reject a custom `temperature` (only their default is allowed).
        # Detected once per model via the API's own error rather than hardcoded per-model-name logic, so any
        # current or future model is handled the same way.
        self._temperature_unsupported = False

    def _create_chat(self, temperature=0.1, **kwargs):
        if not self._temperature_unsupported:
            try:
                return self.client.chat.completions.create(temperature=temperature, **kwargs)
            except BadRequestError as e:
                if "temperature" not in str(e).lower():
                    raise
                self._temperature_unsupported = True
        return self.client.chat.completions.create(**kwargs)

    def complete(self, stage, system, user, trace=None, response_schema=None, temperature=0.1):
        """Single-shot call. If response_schema given (JSON schema dict), forces structured output."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        kwargs = {}
        if response_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "strict": True, "schema": response_schema},
            }
        resp = self._create_chat(model=self.model, messages=messages, temperature=temperature, **kwargs)
        text = resp.choices[0].message.content
        cost = self.cost.add_llm(resp.usage, self.model)
        if trace:
            trace.llm_call(stage, self.model, messages, text, resp.usage.to_dict() if resp.usage else {}, cost)
        if response_schema is not None:
            return json.loads(text)
        return text

    def agentic_loop(self, stage, system, user, tools, tool_executor, trace=None,
                      finish_tool_name="finish", max_steps=8):
        """
        LLM picks which tool to call each step until it calls `finish_tool_name`.
        `tools`: OpenAI function-calling tool schema list (must include a `finish` tool
        whose arguments are the stage's final structured answer).
        `tool_executor(name, args) -> dict`: executes a non-finish tool, returns result.
        Returns the `finish` tool's arguments dict.
        """
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for step in range(max_steps):
            resp = self._create_chat(
                model=self.model, messages=messages, tools=tools, tool_choice="auto", temperature=0.1
            )
            msg = resp.choices[0].message
            cost = self.cost.add_llm(resp.usage, self.model)
            if trace:
                trace.llm_call(
                    f"{stage}.step{step}", self.model, messages,
                    msg.content or [tc.function.name for tc in (msg.tool_calls or [])],
                    resp.usage.to_dict() if resp.usage else {}, cost,
                )
            if not msg.tool_calls:
                # Model didn't call a tool -- nudge it once, then bail with whatever it said.
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({"role": "user", "content": "Call a tool. Use `finish` when done."})
                continue

            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name == finish_tool_name:
                    if trace:
                        trace.decision(stage, "finish", evidence=[args])
                    return args
                self.cost.add_tool()
                result = tool_executor(name, args)
                if trace:
                    trace.tool_call(stage, name, args, result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _shape_tool_result_for_llm(result),
                })

            steps_left = max_steps - step - 1
            if steps_left in (3, 1):
                # Thorough models can keep exploring alternatives even after finding a working answer.
                # A budget-awareness nudge (generic to every stage) pushes toward wrapping up instead of
                # exhausting the loop with no `finish` call at all.
                messages.append({
                    "role": "user",
                    "content": (
                        f"({steps_left} tool-call step(s) left in this budget.) If you already have ONE "
                        "verified working answer, stop exploring alternatives and call `finish` now with what "
                        "you have. If truly nothing works, call `finish` with an honest not-found/failure "
                        "result -- do not let the budget run out without calling finish."
                    ) if steps_left == 3 else
                    "This is your LAST step. Call `finish` now with your best verified answer, or an honest "
                    "not-found result if nothing verified -- do not call any other tool.",
                })
        if trace:
            trace.error(stage, f"agentic_loop exhausted {max_steps} steps without finish")
        return None
