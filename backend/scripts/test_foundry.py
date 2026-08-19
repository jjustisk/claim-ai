"""Verify Azure AI Foundry connection and basic GPT / Claude calls.

Requires Azure login (`az login`) or managed identity when deployed.
Set AZURE_AI_PROJECT_ENDPOINT in .env or Key Vault before running.

Run from backend/:
    python scripts/test_foundry.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.foundry import (
    CLAUDE_MODEL,
    GPT_MODEL,
    create_claude_response,
    get_claude_client,
    get_claude_deployment,
    get_gpt_client,
    get_gpt_deployment,
    reset_foundry_clients,
    uses_claude_router,
)


def main() -> int:
    print("Azure AI Foundry connection test")

    if not settings.azure_ai_project_endpoint:
        print(
            "  SKIP: AZURE_AI_PROJECT_ENDPOINT is not set.\n"
            "  Add it to .env or Key Vault, then rerun this script.",
            file=sys.stderr,
        )
        return 1

    gpt_deployment = get_gpt_deployment()
    claude_deployment = get_claude_deployment()
    print(f"  Project endpoint: {settings.azure_ai_project_endpoint}")
    print(f"  GPT deployment: {gpt_deployment} (model: {GPT_MODEL})")
    print(f"  Claude deployment: {claude_deployment} (target model: {CLAUDE_MODEL})")
    if uses_claude_router():
        print("  Claude path: model-router (quality mode)")

    gpt_ok = False
    claude_ok = False

    try:
        gpt_client = get_gpt_client()
        gpt_response = gpt_client.responses.create(
            model=gpt_deployment,
            input="Reply with exactly: GPT OK",
        )
        gpt_text = gpt_response.output_text.strip()
        print(f"  GPT response: {gpt_text[:120]}")
        if "GPT OK" not in gpt_text:
            print("  FAIL: unexpected GPT response", file=sys.stderr)
            return 1
        print("  GPT call: OK")
        gpt_ok = True

        if uses_claude_router():
            claude_response = create_claude_response(
                "Reply with exactly: Claude OK",
            )
            claude_text = claude_response.output_text.strip()
            routed_model = getattr(claude_response, "model", "unknown")
            print(f"  Claude (router) response: {claude_text[:120]}")
            print(f"  Claude routed to model: {routed_model}")
            if "Claude OK" not in claude_text:
                print("  FAIL: unexpected Claude router response", file=sys.stderr)
                return 1
            print("  Claude call via model-router: OK")
            claude_ok = True
        else:
            try:
                claude_client = get_claude_client()
                claude_response = claude_client.messages.create(
                    model=claude_deployment,
                    max_tokens=32,
                    messages=[
                        {"role": "user", "content": "Reply with exactly: Claude OK"}
                    ],
                )
                claude_text = claude_response.content[0].text.strip()
                print(f"  Claude response: {claude_text[:120]}")
                if "Claude OK" not in claude_text:
                    print("  FAIL: unexpected Claude response", file=sys.stderr)
                    return 1
                print("  Claude call: OK")
                claude_ok = True
            except Exception as claude_exc:
                print(f"  Claude call: SKIPPED ({claude_exc})")
                print(
                    "  Note: set FOUNDRY_CLAUDE_DEPLOYMENT=model-router for australiaeast.",
                    file=sys.stderr,
                )

    except Exception as exc:
        print(f"  FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        reset_foundry_clients()

    if gpt_ok and claude_ok:
        print("SUCCESS: GPT and Claude paths are working.")
    elif gpt_ok:
        print("SUCCESS: GPT is working. Claude path still needs configuration.")
    else:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
