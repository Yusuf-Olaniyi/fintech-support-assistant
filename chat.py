from dotenv import load_dotenv
from openai import OpenAI
import os

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1",
)

history = [{"role": "system", "content": "You are a helpful assistant."}]

while True:
    user_text = input("You: ")
    if user_text.lower() == "quit":
        break

    history.append({"role": "user", "content": user_text})

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=history,
    )

    reply = response.choices[0].message.content
    print("Bot:", reply)

    history.append({"role": "assistant", "content": reply})
    if len(history) > 10:
        history = history[:1] + history[-8:]
    print(len(history))