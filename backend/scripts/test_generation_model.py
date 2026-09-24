"""Real smoke test for the required local Ollama generation model."""

from __future__ import annotations

import time

import httpx


MODEL_ID = "qwen3.5:9b"
OLLAMA_BASE_URL = "http://localhost:11434"
PROMPT = """Question:
What color is the test system?

Evidence:
[S1] The test system is blue.

Instruction:
Answer using only the evidence and cite the source. Do not include reasoning.
"""


def main() -> None:
    started = time.perf_counter()
    with httpx.Client(base_url=OLLAMA_BASE_URL, timeout=120.0) as client:
        response = client.post(
            "/api/generate",
            json={
                "model": MODEL_ID,
                "prompt": PROMPT,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.0, "num_predict": 64},
            },
        )
        response.raise_for_status()
    duration = time.perf_counter() - started

    answer = response.json().get("response", "").strip()
    if "blue" not in answer.lower() or "[S1]" not in answer:
        raise RuntimeError(
            "Generation response did not contain the expected evidence answer and citation"
        )

    print(f"Model: {MODEL_ID}")
    print(f"Ollama URL: {OLLAMA_BASE_URL}")
    print("Request success: yes")
    print(f"Generation duration: {duration:.3f}s")
    print(f"Response length: {len(answer)} characters")
    print(f"Response: {answer}")


if __name__ == "__main__":
    main()
