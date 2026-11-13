"""Release defaults; provider-specific options never change the supplied URL."""
from urllib.parse import urlsplit

DEFAULT_MODEL = "qwen3.8-27b-noreason"
DEFAULT_CALLS = 6
DEFAULT_COMPACT_DATA_CONTEXT = True


def resolve_json_mode(base_url, override=None):
    if override is not None:
        return bool(override)
    parts = urlsplit(base_url)
    return (parts.scheme == "https" and parts.hostname == "api.neuraldeep.ru"
            and parts.port in (None, 443))
