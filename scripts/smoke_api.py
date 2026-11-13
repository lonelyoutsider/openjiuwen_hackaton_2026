#!/usr/bin/env python3
"""One bounded diagnostic call. Standard library only, Python 3.11–3.14.

Not part of the competition agent. Never saves the key or auto-retries.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

MODELS = ("qwen3.8-27b", "qwen3.8-27b-noreason",
          "qwen3.6-35b-a3b", "qwen3.6-35b-a3b-noreason")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward Authorization to another endpoint on a redirect.
        return None


def make_request(base_url, key, model, *, json_mode=False):
    base_url = base_url.rstrip("/")
    parts = urllib.parse.urlsplit(base_url)
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment):
        raise ValueError("Use an HTTPS API base URL without credentials, query or fragment")
    if not key or any(character.isspace() for character in key):
        raise ValueError("The API key is empty or contains whitespace")
    if key.upper().startswith(("NGU26-", "НГУ-")):
        raise ValueError("This is an invitation code; copy the API key from your account")
    if model not in MODELS:
        raise ValueError("Select one of the four competition models")
    body = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly OK."}],
            "temperature": 0, "max_tokens": 32, "stream": False}
    if json_mode:
        body["messages"][0]["content"] = 'Return exactly one JSON object: {"action":"answer","answer":"OK"}'
        body["response_format"] = {"type": "json_object"}
    return urllib.request.Request(base_url + "/chat/completions",
                                  data=json.dumps(body).encode("utf-8"),
                                  headers={"Authorization": "Bearer " + key,
                                           "Content-Type": "application/json"},
                                  method="POST")


def call_once(base_url, key, model, *, json_mode=False):
    request = make_request(base_url, key, model, json_mode=json_mode)
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(request, timeout=60) as response:
        data = json.loads(response.read(1_048_576).decode("utf-8"))
    message = data["choices"][0]["message"]
    result = {"status": "ok", "model": data.get("model", model),
            "answer": message.get("content"), "usage": data.get("usage"),
            "note": "Diagnostic request; not a competition solution or framework test"}
    if json_mode:
        try:
            valid = json.loads(message.get("content")) == {"action": "answer", "answer": "OK"}
        except (ValueError, TypeError):
            valid = False
        result.update(json_mode_requested=True, json_action_valid=valid)
        result["status"] = "ok" if valid else "unexpected_format"
        usage = data.get("usage")
        usage_known = isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
                                                    for k in ("prompt_tokens", "completion_tokens"))
        result["usage_known"] = usage_known
        result["weighted_tokens"] = round(usage["completion_tokens"] + usage["prompt_tokens"] / 10, 1) if usage_known else None
        if valid and not usage_known:
            result["status"] = "unexpected_usage"
        result["note"] = "One compatibility probe; valid JSON does not prove grammar enforcement or final-proxy support"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "https://api.neuraldeep.ru/v1"))
    parser.add_argument("--model", choices=MODELS, default="qwen3.8-27b-noreason")
    parser.add_argument("--json-mode", action="store_true", help="one 32-output-token probe with response_format=json_object")
    args = parser.parse_args()
    key = os.environ.get("LLM_API_KEY") or getpass.getpass("API key from NeuralDeep (hidden): ")
    try:
        result = call_once(args.base_url, key.strip(), args.model, json_mode=args.json_mode)
    except urllib.error.HTTPError as error:
        hint = {401: "Check the API key copied from your account",
                403: "Check event access and the two-IP restriction",
                404: "Check the API base URL and model name",
                429: "Rate/concurrency limit; wait before a manual retry"}.get(error.code, "Provider returned an HTTP error")
        print(json.dumps({"status": "error", "http_status": error.code, "hint": hint}), file=sys.stderr)
        return 1
    except urllib.error.URLError:
        print("Network/TLS error: check connectivity to the API. No retry was sent.", file=sys.stderr)
        return 1
    except (ValueError, KeyError, IndexError, TypeError, OSError) as error:
        # Never print exceptions which could contain a provider's echoed request.
        print("Invalid input, timeout or unexpected API response (" + type(error).__name__ + "). No retry was sent.", file=sys.stderr)
        return 1
    finally:
        key = None
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
