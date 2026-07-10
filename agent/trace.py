"""JSONL trace logger. Every LLM call, tool call, and reasoning step gets one line.

This is the "reasoning/action trace" deliverable (§3 rule 6) -- not a debug log,
it's a first-class artifact shipped alongside the generated scraper.
"""
import json
import os
import time


class Trace:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._fh = open(path, "a", encoding="utf-8")
        self._step = 0

    def _write(self, entry):
        self._step += 1
        entry["step"] = self._step
        entry["ts"] = time.time()
        self._fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def stage(self, name, detail=None):
        self._write({"type": "stage", "stage": name, "detail": detail})

    def reasoning(self, stage, text):
        self._write({"type": "reasoning", "stage": stage, "text": text})

    def llm_call(self, stage, model, messages, response_text, usage, cost_usd):
        self._write({
            "type": "llm_call",
            "stage": stage,
            "model": model,
            "input_messages": messages,
            "output": response_text,
            "usage": usage,
            "cost_usd": cost_usd,
        })

    def tool_call(self, stage, tool, tool_input, tool_output):
        self._write({
            "type": "tool_call",
            "stage": stage,
            "tool": tool,
            "input": tool_input,
            "output": tool_output,
        })

    def decision(self, stage, decision, evidence=None, confidence=None):
        self._write({
            "type": "decision",
            "stage": stage,
            "decision": decision,
            "evidence": evidence or [],
            "confidence": confidence,
        })

    def error(self, stage, message):
        self._write({"type": "error", "stage": stage, "message": message})

    def close(self):
        self._fh.close()
