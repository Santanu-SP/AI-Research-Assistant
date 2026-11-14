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
from app.services.observability.usage import (
    acquire_run_quota_policy,
    count_active_users,
    enforce_user_daily_model_quota,
    get_user_model_usage_and_quota,
    record_model_usage,
    release_research_shared_quota,
    release_shared_quota_slot,
    reserve_shared_quota_slot,
)

__all__ = [
    "CaseEvaluationResult",
    "EvaluationBenchmarkCase",
    "EvaluationSuiteReport",
    "acquire_run_quota_policy",
    "compute_answer_faithfulness",
    "compute_answer_relevance",
    "compute_citation_accuracy",
    "compute_context_precision",
    "compute_context_recall",
    "count_active_users",
    "enforce_user_daily_model_quota",
    "estimate_cost_usd",
    "evaluate_case",
    "get_user_model_usage_and_quota",
    "record_model_usage",
    "record_telemetry_event",
    "release_research_shared_quota",
    "release_shared_quota_slot",
    "reserve_shared_quota_slot",
    "run_evaluation_suite",
    "sanitize_metadata",
    "summarize_telemetry",
]

