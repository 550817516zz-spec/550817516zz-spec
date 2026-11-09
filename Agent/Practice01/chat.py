import configparser
import time

from openai import OpenAI


def typewriter_print(text, delay=0.03):
    for char in text:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()


def load_config():
    config = configparser.ConfigParser()
    config.read("config.ini", encoding="utf-8")
    llm = config["llm"]
    return llm["base_url"], llm["api_key"], llm["model"]


def main():
    base_url, api_key, model = load_config()
    client = OpenAI(base_url=base_url, api_key=api_key)

    history = []

    while True:
        user_input = input("请输入消息：").strip()

        history.append({"role": "user", "content": user_input})

        response = client.chat.completions.create(
            model=model,
            messages=history,
        )
        reply = response.choices[0].message.content

        print("-" * 40)
        typewriter_print(reply)

        history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    main()

