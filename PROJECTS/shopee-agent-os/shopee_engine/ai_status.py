"""
AI provider status — checks which AI features are active at runtime.
Used for startup logging and /system-status diagnostics.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _load_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            env_path = Path(__file__).parent.parent / ".env"
            load_dotenv(env_path, override=False)
            key = os.environ.get("ANTHROPIC_API_KEY", "")
        except ImportError:
            pass
    return key


def _is_real_key(key: str) -> bool:
    return bool(key) and len(key) > 80 and key.startswith("sk-ant-")


def get_ai_status() -> dict:
    """Return AI provider status dict."""
    key    = _load_key()
    active = _is_real_key(key)

    modules = {
        "humanize_engine":  active,
        "editorial_engine": active,
        "content_engine":   active,
        "trend_engine":     active,
    }

    if active:
        try:
            import anthropic  # noqa: F401
            import_ok = True
        except ImportError:
            import_ok = False
            active = False
    else:
        import importlib.util
        import_ok = importlib.util.find_spec("anthropic") is not None

    return {
        "provider":          "Claude" if active else "Fallback Templates",
        "model":             _ANTHROPIC_MODEL if active else None,
        "active":            active,
        "key_present":       bool(key),
        "key_valid_format":  _is_real_key(key),
        "anthropic_installed": import_ok,
        "modules":           modules,
    }


def probe_anthropic_api() -> dict:
    """Make a minimal API call to verify the key works. Returns success + details."""
    key = _load_key()
    if not _is_real_key(key):
        return {
            "success": False,
            "error":   "Key is missing or invalid format (placeholder value detected)",
            "error_type": "invalid_key_format",
        }
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {
            "success":     True,
            "model":       msg.model,
            "stop_reason": msg.stop_reason,
            "provider":    "Claude",
        }
    except Exception as exc:
        err_str = str(exc)
        if "401" in err_str or "authentication" in err_str.lower():
            err_type = "invalid_api_key"
        elif "429" in err_str or "rate" in err_str.lower():
            err_type = "rate_limited"
        elif "overloaded" in err_str.lower():
            err_type = "model_overloaded"
        elif "model" in err_str.lower() and "not" in err_str.lower():
            err_type = "model_unavailable"
        else:
            err_type = "unknown"
        return {"success": False, "error": err_str, "error_type": err_type}


def log_ai_status() -> None:
    """Print startup AI status to stdout (picked up by bot log)."""
    s = get_ai_status()
    if s["active"]:
        print(f"[AI] Provider: Claude")
        print(f"[AI] Model: {s['model']}")
        print(f"[AI] Humanize Engine: ENABLED")
        print(f"[AI] Modules active: {', '.join(k for k, v in s['modules'].items() if v)}")
    else:
        print(f"[AI] Provider: Fallback Templates")
        print(f"[AI] Humanize Engine: DISABLED")
        if not s["key_present"]:
            print(f"[AI] Reason: ANTHROPIC_API_KEY not set")
        elif not s["key_valid_format"]:
            print(f"[AI] Reason: ANTHROPIC_API_KEY is a placeholder — replace with real key")
        elif not s["anthropic_installed"]:
            print(f"[AI] Reason: anthropic package not installed")
