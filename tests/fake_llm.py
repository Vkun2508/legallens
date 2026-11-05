"""A stand-in for the Anthropic client: same `beta.messages.stream(...)` surface, canned replies."""

import json
from types import SimpleNamespace


def reply(findings=None, *, text=None, stop_reason="end_turn", input_tokens=1000, output_tokens=200,
          cache_read=0, cache_write=0):
    body = text if text is not None else json.dumps({"findings": findings or []})
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_input_tokens=cache_read, cache_creation_input_tokens=cache_write,
        ),
    )


def item(clause, rule_id, verdict="compliant", quote="", explanation="Because.", rewrite=""):
    return {"clause": clause, "rule_id": rule_id, "verdict": verdict, "quote": quote,
            "explanation": explanation, "suggested_rewrite": rewrite}


class _Stream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class FakeClient:
    """`replies` is a list of messages, exceptions, or callables taking the request kwargs."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=self)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        next_reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(next_reply, Exception):
            raise next_reply
        if callable(next_reply):
            next_reply = next_reply(kwargs)
        return _Stream(next_reply)
