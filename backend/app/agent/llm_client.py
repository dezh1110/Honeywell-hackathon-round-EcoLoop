"""
OSS LLM client. Deliberately just an OpenAI-compatible chat-completions
client, because every serious open-source serving stack (Ollama, vLLM,
LM Studio, Text Generation Inference) speaks that wire format -- this file
is what makes the model in `.env` (Llama 3.1, Mistral, Qwen2.5, ...) a
one-line swap.
"""
from __future__ import annotations

from openai import OpenAI

from app.config import settings


def build_client() -> OpenAI:
    return OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)
