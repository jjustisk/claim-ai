   import anthropic

   client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY

   request = {
       "model": "claude-sonnet-5-5",
       "max_tokens": 300,
       "messages": [{"role": "user", "content": "What does a claims assessor do? One sentence."}],
   }
   print("REQUEST:", request)

   message = client.messages.create(**request)

   print("message.content:", message.content)
   print("text:", message.content[0].text)
   print("stop_reason:", message.stop_reason, "| tokens:", message.usage.input_tokens, "/", message.usage.output_tokens)