#!/usr/bin/env python3
"""
Minimal LangChain CLI runner for Ollama.

Example:
  python scripts/langchain_cli.py --prompt "List files in /workspaces/poc"
"""
import argparse
import os
import sys

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _load_env() -> None:
    if load_dotenv:
        load_dotenv()


def _build_client(model: str, base_url: str):
    try:
        from langchain_community.chat_models import ChatOllama
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "langchain_community is required. Install with: pip install langchain-community"
        ) from exc
    return ChatOllama(model=model, base_url=base_url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a LangChain chat call against Ollama")
    parser.add_argument("--prompt", required=True, help="Prompt to send to the model")
    parser.add_argument("--model", default=os.getenv("AGENT_MODEL", "qwen3:0.6b"))
    parser.add_argument("--ollama", default=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"))
    args = parser.parse_args()

    _load_env()

    model = args.model
    base_url = args.ollama.rstrip("/")
    prompt = args.prompt

    try:
        client = _build_client(model, base_url)
    except RuntimeError as exc:
        print(str(exc))
        return 1

    response = client.invoke(prompt)
    print(response.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
