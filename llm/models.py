import os

from langchain_groq import ChatGroq

MODEL_NAME = "openai/gpt-oss-120b"


def get_llm() -> ChatGroq:
    return ChatGroq(
        model=MODEL_NAME,
        temperature=0,
        api_key=os.environ["GROQ_API_KEY"],
    )
