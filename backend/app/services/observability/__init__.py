"""Observability, telemetry, and RAG quality evaluation."""

from app.services.observability.evaluation import (
    CaseEvaluationResult,
    EvaluationBenchmarkCase,
    EvaluationSuiteReport,
    compute_answer_faithfulness,
    compute_answer_relevance,
    compute_citation_accuracy,
    compute_context_precision,
    compute_context_recall,
    evaluate_case,
    run_evaluation_suite,
)
from app.services.observability.telemetry import (
    estimate_cost_usd,
    record_telemetry_event,
    sanitize_metadata,
    summarize_telemetry,
)

__all__ = [
    "CaseEvaluationResult",
    "EvaluationBenchmarkCase",
    "EvaluationSuiteReport",
    "compute_answer_faithfulness",
    "compute_answer_relevance",
    "compute_citation_accuracy",
    "compute_context_precision",
    "compute_context_recall",
    "estimate_cost_usd",
    "evaluate_case",
    "record_telemetry_event",
    "run_evaluation_suite",
    "sanitize_metadata",
    "summarize_telemetry",
]

