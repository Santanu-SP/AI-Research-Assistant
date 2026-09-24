"""Real smoke test for the required local Qwen reranker."""

from __future__ import annotations

import math
import time

from sentence_transformers import CrossEncoder


MODEL_ID = "Qwen/Qwen3-Reranker-0.6B"
QUERY = "Which passage states the color of the test system?"
PASSAGES = [
    "The test system is blue.",
    "The backup system is stored in another building.",
    "The experiment ran for three days.",
]


def main() -> None:
    load_started = time.perf_counter()
    model = CrossEncoder(MODEL_ID, trust_remote_code=True)
    load_duration = time.perf_counter() - load_started

    inference_started = time.perf_counter()
    scores = model.predict([(QUERY, passage) for passage in PASSAGES])
    inference_duration = time.perf_counter() - inference_started

    ranked = sorted(
        enumerate(float(score) for score in scores),
        key=lambda item: (-item[1], item[0]),
    )
    if not all(math.isfinite(score) for _, score in ranked):
        raise RuntimeError("Reranker returned a non-finite score")

    print(f"Model: {MODEL_ID}")
    print(f"Device: {model.model.device}")
    print(f"Load time: {load_duration:.3f}s")
    print(f"Inference time: {inference_duration:.3f}s")
    print("Ranked passage indexes/scores:")
    for passage_index, score in ranked:
        print(f"  {passage_index}: {score:.6f}")


if __name__ == "__main__":
    main()
