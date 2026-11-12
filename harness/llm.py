"""Sequential OpenAI-compatible calls with a shared conservative token ledger."""
import json
import time
import urllib.request
import urllib.parse

MODELS = ("qwen3.8-27b", "qwen3.8-27b-noreason", "qwen3.6-35b-a3b", "qwen3.6-35b-a3b-noreason")


class LLMStopped(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, base_url, api_key, budget, *, model=MODELS[1], timeout=60, deadline=None, json_mode=False):
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError("invalid proxy URL")
        if not api_key or any(c.isspace() for c in api_key) or model not in MODELS:
            raise ValueError("invalid API configuration")
        self.url, self.key, self.model = base_url.rstrip("/") + "/chat/completions", api_key, model
        self.limit = int(budget) * 10
        self.spent = self.prompt_tokens = self.completion_tokens = self.calls = 0
        self.stopped = False
        self.timeout, self.deadline, self.last_call = timeout, deadline, 0.0
        self.opener = urllib.request.build_opener(NoRedirect())
        self.json_mode = json_mode
        self.last_request_metadata = self.last_response_metadata = None

    def complete(self, messages, max_tokens):
        self.last_request_metadata = self.last_response_metadata = None
        if self.stopped:
            raise LLMStopped("API disabled after an uncertain or failed request")
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens,
                "temperature": 0, "stream": False}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        # UTF-8 bytes + generous chat framing allowance is a conservative input
        # estimate, not an exact Qwen tokenizer. Unused reservation is released.
        reserve = len(payload) + 1024 + max_tokens * 10
        self.last_request_metadata = {"request_sent": False, "max_output_tokens": max_tokens,
            "reservation_weighted_tokens": reserve / 10,
            "remaining_weighted_tokens": (self.limit - self.spent) / 10}
        if self.spent + reserve > self.limit:
            raise LLMStopped("not enough budget for a conservative request reservation")
        pause = max(0.0, 1.05 - (time.monotonic() - self.last_call))
        remaining = (self.deadline - time.monotonic() - pause) if self.deadline else self.timeout
        if remaining <= 1:
            raise LLMStopped("run deadline reached")
        if pause:
            time.sleep(pause)
        request = urllib.request.Request(self.url, data=payload, method="POST",
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"})
        self.calls += 1
        self.last_call = time.monotonic()
        # Charge reservation until authoritative usage has arrived. Never
        # automatically retry a request whose billable outcome is unknown.
        self.spent += reserve
        self.last_request_metadata["request_sent"] = True
        try:
            with self.opener.open(request, timeout=min(self.timeout, remaining)) as response:
                data = json.loads(response.read(2_000_000).decode("utf-8"))
            usage = data["usage"]
            prompt, completion = usage["prompt_tokens"], usage["completion_tokens"]
            if type(prompt) is not int or type(completion) is not int or min(prompt, completion) < 0:
                raise ValueError("invalid usage")
            # The verified provider schema includes reasoning inside completion.
            # Nested reasoning_tokens must not be added a second time.
            self.spent += prompt + completion * 10 - reserve
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            if self.spent >= self.limit:
                self.stopped = True
            choice = data["choices"][0]
            content = choice["message"]["content"]
            finish = choice.get("finish_reason")
            if finish not in (None, "stop", "length", "tool_calls", "function_call", "content_filter"):
                finish = "other"
            details = usage.get("completion_tokens_details")
            reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
            if type(reasoning) is not int or reasoning < 0:
                reasoning = None
            self.last_response_metadata = {"finish_reason": finish, "reasoning_tokens": reasoning,
                "json_mode": self.json_mode,
                "input_tokens": prompt, "output_tokens": completion, "max_output_tokens": max_tokens,
                "content_chars": len(content) if isinstance(content, str) else None}
            return content
        except Exception as error:
            self.stopped = True
            # Do not expose provider response bodies, headers or API credentials.
            raise LLMStopped("API request stopped: " + type(error).__name__) from None

    def snapshot(self):
        return {"llm_calls": self.calls, "input_tokens": self.prompt_tokens,
                "output_tokens": self.completion_tokens, "weighted_tokens": self.spent / 10,
                "usage_uncertain": self.stopped and self.spent > self.prompt_tokens + self.completion_tokens * 10}
