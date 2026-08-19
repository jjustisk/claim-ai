"""Interactive GPT / Claude inference in the terminal.

Requires Azure login (`az login`) or managed identity when deployed.
Set AZURE_AI_PROJECT_ENDPOINT in .env or Key Vault before running.

Run from backend/:
    python scripts/infer_foundry.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

# Load only Foundry-related Key Vault secrets (skips ~10 unrelated fetches).
os.environ.setdefault("CLAIM_AI_SETTINGS_MODE", "foundry")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings

QUIT_COMMANDS = {"q", "quit", "exit"}
BACK_COMMANDS = {"b", "back"}

T = TypeVar("T")


def _require_endpoint() -> None:
    if not settings.azure_ai_project_endpoint:
        print(
            "AZURE_AI_PROJECT_ENDPOINT is not set.\n"
            "Add it to .env or Key Vault, then rerun this script.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def _print_menu() -> None:
    print()
    print("Foundry inference")
    print("  1) GPT 5.5")
    print("  2) Claude Opus (via model-router in australiaeast)")
    print("  q) Quit")
    print()


def _choose_model() -> str | None:
    while True:
        _print_menu()
        choice = input("Choose model [1/2/q]: ").strip().lower()
        if choice in QUIT_COMMANDS:
            return None
        if choice == "1":
            return "gpt"
        if choice == "2":
            return "claude"
        print("Invalid choice. Enter 1, 2, or q.")


def _lazy_import_foundry() -> dict[str, Any]:
    """Import Foundry clients only after the user picks a model."""
    from app.foundry import (
        CLAUDE_MODEL,
        GPT_MODEL,
        get_claude_client,
        get_claude_deployment,
        get_gpt_client,
        get_gpt_deployment,
        uses_claude_router,
        warm_claude_client,
        warm_gpt_client,
    )

    return {
        "CLAUDE_MODEL": CLAUDE_MODEL,
        "GPT_MODEL": GPT_MODEL,
        "get_claude_client": get_claude_client,
        "get_claude_deployment": get_claude_deployment,
        "get_gpt_client": get_gpt_client,
        "get_gpt_deployment": get_gpt_deployment,
        "uses_claude_router": uses_claude_router,
        "warm_claude_client": warm_claude_client,
        "warm_gpt_client": warm_gpt_client,
    }


def _with_retry(fn: Callable[[], T], label: str) -> T:
    """Retry once on transient Azure API errors."""
    try:
        return fn()
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name not in {"APIError", "APIConnectionError", "RateLimitError"}:
            raise
        print(f"{label} failed, retrying...", file=sys.stderr)
        time.sleep(1)
        return fn()


def _warm_session(label: str, warm_fn) -> None:
    print(f"Connecting to {label}...", end="", flush=True)
    started = time.perf_counter()
    try:
        _with_retry(warm_fn, label)
    except Exception as exc:
        print(f" failed ({exc})", file=sys.stderr)
        return
    print(f" ready ({time.perf_counter() - started:.1f}s)")


def _stream_foundry(foundry: dict[str, Any], deployment: str, prompt: str, label: str) -> None:
    def _run() -> None:
        started = time.perf_counter()
        first_token_at: float | None = None
        routed_model: str | None = None

        print()
        print(f"{label}: ", end="", flush=True)

        with foundry["get_gpt_client"]().responses.stream(
            model=deployment,
            input=prompt,
        ) as stream:
            for event in stream:
                if event.type == "response.output_text.delta":
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    print(event.delta, end="", flush=True)
                elif event.type == "response.completed":
                    routed_model = getattr(event.response, "model", None)
            final = stream.get_final_response()
            if routed_model is None:
                routed_model = getattr(final, "model", None)

        print()
        if first_token_at is not None:
            print(f"({first_token_at - started:.1f}s to first token)")
        if routed_model:
            print(f"(routed to {routed_model})")

    _with_retry(_run, label)


def _stream_direct_claude(foundry: dict[str, Any], deployment: str, prompt: str) -> None:
    def _run() -> None:
        started = time.perf_counter()
        first_token_at: float | None = None

        print()
        print("Claude: ", end="", flush=True)

        with foundry["get_claude_client"]().messages.stream(
            model=deployment,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                print(text, end="", flush=True)

        print()
        if first_token_at is not None:
            print(f"({first_token_at - started:.1f}s to first token)")

    _with_retry(_run, "Claude")


def _run_gpt_session(foundry: dict[str, Any]) -> None:
    deployment = foundry["get_gpt_deployment"]()
    print()
    print(
        f"GPT session — deployment: {deployment} "
        f"(model: {foundry['GPT_MODEL']})"
    )
    print("Type a prompt and press Enter. Commands: back, quit")
    _warm_session("GPT", foundry["warm_gpt_client"])

    while True:
        print()
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt.lower() in QUIT_COMMANDS:
            raise SystemExit(0)
        if prompt.lower() in BACK_COMMANDS:
            return

        try:
            _stream_foundry(foundry, deployment, prompt, "GPT")
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)


def _run_claude_session(foundry: dict[str, Any]) -> None:
    deployment = foundry["get_claude_deployment"]()
    print()
    if foundry["uses_claude_router"]():
        print(
            f"Claude session — deployment: {deployment} "
            f"(target: {foundry['CLAUDE_MODEL']}, via model-router)"
        )
    else:
        print(
            f"Claude session — deployment: {deployment} "
            f"(model: {foundry['CLAUDE_MODEL']})"
        )
    print("Type a prompt and press Enter. Commands: back, quit")
    _warm_session("Claude", foundry["warm_claude_client"])

    while True:
        print()
        prompt = input("You: ").strip()
        if not prompt:
            continue
        if prompt.lower() in QUIT_COMMANDS:
            raise SystemExit(0)
        if prompt.lower() in BACK_COMMANDS:
            return

        try:
            if foundry["uses_claude_router"]():
                _stream_foundry(foundry, deployment, prompt, "Claude")
            else:
                _stream_direct_claude(foundry, deployment, prompt)
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)


def main() -> int:
    _require_endpoint()

    print(f"Project: {settings.azure_ai_project_endpoint}")
    foundry: dict[str, Any] | None = None

    try:
        while True:
            model = _choose_model()
            if model is None:
                break
            if foundry is None:
                foundry = _lazy_import_foundry()
            if model == "gpt":
                _run_gpt_session(foundry)
            else:
                _run_claude_session(foundry)
    finally:
        if foundry is not None:
            from app.foundry import reset_foundry_clients

            reset_foundry_clients()

    print("Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
