import json
import logging
import sys
from pathlib import Path
import openai

# Make `app` importable when running from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Hide Azure SDK header dumps so the output stays readable
logging.basicConfig(level=logging.WARNING)

from app.connectors.foundry import get_gpt_client, get_gpt_deployment  # noqa: E402

# 1. FORMALISE THE REQUEST
user_message = {"role": "user", "content": "What does an insurance claims assessor do? One sentence."}

request = {
    "model": get_gpt_deployment(),          # our Azure deployment, e.g. gpt-5.5
    "max_output_tokens": 300,               # cap on reply length
    "input": [user_message],                # the messages list
}
print("REQUEST FORMED:")
print(json.dumps(request, indent=2))

# 2. SEND IT TO AZURE
print("\nSENDING to Azure Foundry...")
try:
    response = get_gpt_client().responses.create(**request)
except openai.PermissionDeniedError as exc:
    print("\nAZURE REFUSED (403). Reason from Azure:")
    print(exc.body or exc.response.text)
    print("status:", exc.response.status_code)
    print({k: v for k, v in exc.response.headers.items() if "id" in k.lower() or "request" in k.lower()})
    sys.exit(1)
print("RECEIVED.\n")

# 3. READ THE REPLY (the equivalent of Anthropic's message.content)
print("response.output      :", response.output)
print("response.output_text :", response.output_text)
print("status               :", response.status)
print("model                :", response.model)
print("tokens in/out        :", response.usage.input_tokens, "/", response.usage.output_tokens)

# 4. KEEP THE CONVERSATION: add the assistant reply, then the next user message
assistant_message = {"role": "assistant", "content": response.output_text}
next_request = {
    **request,
    "input": [user_message, assistant_message, {"role": "user", "content": "And what do they check first?"}],
}
print("\nNEXT REQUEST (history resent):")
print(json.dumps(next_request, indent=2))