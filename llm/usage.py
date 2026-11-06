"""Request-local model usage, with no prompts, feedback or credentials logged."""

from contextlib import contextmanager
from contextvars import ContextVar
import os
import time
import math


_events = ContextVar("model_usage", default=None)


@contextmanager
def capture_usage():
    events = []
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


def observed_completion(client, *, stage, **kwargs):
    started = time.perf_counter()
    event = {"stage": stage, "model": kwargs.get("model"), "success": False,
             "input_tokens": None, "output_tokens": None, "estimated_usd": None}
    try:
        response = client.chat.completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        event.update(success=True, input_tokens=getattr(usage, "prompt_tokens", None),
                     output_tokens=getattr(usage, "completion_tokens", None))
        # Configured rates are estimates; missing usage/rates must not imply zero cost.
        try:
            input_rate = float(os.environ["MODEL_INPUT_USD_PER_MILLION"])
            output_rate = float(os.environ["MODEL_OUTPUT_USD_PER_MILLION"])
            if all(math.isfinite(rate) and rate >= 0 for rate in (input_rate, output_rate)) and event["input_tokens"] is not None and event["output_tokens"] is not None:
                event["estimated_usd"] = (event["input_tokens"] * input_rate + event["output_tokens"] * output_rate) / 1_000_000
        except (KeyError, ValueError, TypeError):
            pass
        return response
    except Exception as exc:
        event["error_type"] = type(exc).__name__
        raise
    finally:
        event["elapsed_seconds"] = round(time.perf_counter() - started, 4)
        events = _events.get()
        if events is not None:
            events.append(event)
