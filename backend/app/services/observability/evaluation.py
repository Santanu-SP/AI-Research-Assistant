"""Ragas-style RAG quality evaluation suite (context precision, recall, faithfulness, relevance, citations)."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from app.schemas.rag import EvidenceItem, ValidatedCitation
from app.services.rag.citations import CitationValidator

_WORD_RE = re.compile(r"[a-zA-Z0-9]{3,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "was",
        "were",
        "have",
        "has",
        "had",
        "not",
        "but",
        "what",
        "which",
        "when",
        "where",
        "how",
        "who",
        "why",
        "into",
        "than",
        "then",
        "their",
        "there",
        "about",
        "between",
        "through",
        "using",
        "used",
    }
)


def _content_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _WORD_RE.findall(text)
        if token.lower() not in _STOPWORDS
    }


@dataclass(frozen=True)
class EvaluationBenchmarkCase:
    case_id: str
    question: str
    expected_facts: list[str]
    relevant_keywords: list[str]
    evidence: list[EvidenceItem]
    generated_answer: str


@dataclass(frozen=True)
class CaseEvaluationResult:
    case_id: str
    context_precision: float
    context_recall: float
    answer_faithfulness: float
    answer_relevance: float
    citation_accuracy: float
    overall_score: float


@dataclass(frozen=True)
class EvaluationSuiteReport:
    case_count: int
    mean_context_precision: float
    mean_context_recall: float
    mean_answer_faithfulness: float
    mean_answer_relevance: float
    mean_citation_accuracy: float
    overall_score: float
    cases: list[CaseEvaluationResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "mean_context_precision": round(self.mean_context_precision, 4),
            "mean_context_recall": round(self.mean_context_recall, 4),
            "mean_answer_faithfulness": round(self.mean_answer_faithfulness, 4),
            "mean_answer_relevance": round(self.mean_answer_relevance, 4),
            "mean_citation_accuracy": round(self.mean_citation_accuracy, 4),
            "overall_score": round(self.overall_score, 4),
            "cases": [
                {
                    "case_id": c.case_id,
                    "context_precision": round(c.context_precision, 4),
                    "context_recall": round(c.context_recall, 4),
                    "answer_faithfulness": round(c.answer_faithfulness, 4),
                    "answer_relevance": round(c.answer_relevance, 4),
                    "citation_accuracy": round(c.citation_accuracy, 4),
                    "overall_score": round(c.overall_score, 4),
                }
                for c in self.cases
            ],
        }


def compute_context_precision(
    evidence: list[EvidenceItem],
    relevant_keywords: list[str],
) -> float:
    """Ragas-style Precision@K: weighted precision of retrieved chunks that contain relevant concepts."""
    if not evidence or not relevant_keywords:
        return 0.0
    kw_set = {kw.lower() for kw in relevant_keywords}
    relevant_hits = 0
    precision_sum = 0.0
    for idx, item in enumerate(evidence, start=1):
        text_lower = item.text.lower()
        is_relevant = any(kw in text_lower for kw in kw_set)
        if is_relevant:
            relevant_hits += 1
            precision_sum += relevant_hits / idx
    if relevant_hits == 0:
        return 0.0
    return min(1.0, precision_sum / relevant_hits)


def compute_context_recall(
    evidence: list[EvidenceItem],
    expected_facts: list[str],
) -> float:
    """Fraction of ground-truth expected facts supported by retrieved context."""
    if not expected_facts:
        return 1.0
    if not evidence:
        return 0.0
    combined_tokens = _content_tokens(" ".join(item.text for item in evidence))
    supported = 0
    for fact in expected_facts:
        fact_tokens = _content_tokens(fact)
        if not fact_tokens:
            supported += 1
            continue
        overlap = len(fact_tokens & combined_tokens) / len(fact_tokens)
        if overlap >= 0.5:
            supported += 1
    return supported / len(expected_facts)


def compute_answer_faithfulness(
    answer: str,
    evidence: list[EvidenceItem],
) -> float:
    """Fraction of factual sentences in the answer whose content tokens are grounded in evidence."""
    if not answer.strip() or not evidence:
        return 0.0
    evidence_tokens = _content_tokens(" ".join(item.text for item in evidence))
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(answer.strip()) if s.strip()]
    if not sentences:
        return 0.0
    grounded_sentences = 0
    for sentence in sentences:
        cleaned = re.sub(r"\[S\d+\]", "", sentence)
        tokens = _content_tokens(cleaned)
        if not tokens:
            grounded_sentences += 1
            continue
        overlap = len(tokens & evidence_tokens) / len(tokens)
        if overlap >= 0.45:
            grounded_sentences += 1
    return grounded_sentences / len(sentences)


def compute_answer_relevance(question: str, answer: str) -> float:
    """Overlap and topical alignment between question and generated answer."""
    q_tokens = _content_tokens(question)
    a_tokens = _content_tokens(re.sub(r"\[S\d+\]", "", answer))
    if not q_tokens or not a_tokens:
        return 0.0
    overlap = len(q_tokens & a_tokens) / len(q_tokens)
    return min(1.0, max(0.0, overlap))


def compute_citation_accuracy(
    answer: str,
    evidence: list[EvidenceItem],
) -> float:
    """Validate that all [S#] citations exist in evidence and cited blocks support the claim."""
    if not answer.strip() or not evidence:
        return 0.0
    validator = CitationValidator()
    try:
        validated = validator.validate(answer, evidence)
    except Exception:
        return 0.0
    if not validated.citations:
        return 0.0
    evidence_by_id = {item.source_id: item for item in evidence}
    valid_citations: list[ValidatedCitation] = [
        c for c in validated.citations if c.citation_id in evidence_by_id
    ]
    return len(valid_citations) / max(1, len(validated.citations))


def evaluate_case(case: EvaluationBenchmarkCase) -> CaseEvaluationResult:
    cp = compute_context_precision(case.evidence, case.relevant_keywords)
    cr = compute_context_recall(case.evidence, case.expected_facts)
    af = compute_answer_faithfulness(case.generated_answer, case.evidence)
    ar = compute_answer_relevance(case.question, case.generated_answer)
    ca = compute_citation_accuracy(case.generated_answer, case.evidence)
    overall = (cp + cr + af + ar + ca) / 5.0
    return CaseEvaluationResult(
        case_id=case.case_id,
        context_precision=cp,
        context_recall=cr,
        answer_faithfulness=af,
        answer_relevance=ar,
        citation_accuracy=ca,
        overall_score=overall,
    )


def run_evaluation_suite(
    cases: list[EvaluationBenchmarkCase],
) -> EvaluationSuiteReport:
    if not cases:
        return EvaluationSuiteReport(
            case_count=0,
            mean_context_precision=0.0,
            mean_context_recall=0.0,
            mean_answer_faithfulness=0.0,
            mean_answer_relevance=0.0,
            mean_citation_accuracy=0.0,
            overall_score=0.0,
            cases=[],
        )
    results = [evaluate_case(c) for c in cases]
    n = len(results)
    mean_cp = sum(r.context_precision for r in results) / n
    mean_cr = sum(r.context_recall for r in results) / n
    mean_af = sum(r.answer_faithfulness for r in results) / n
    mean_ar = sum(r.answer_relevance for r in results) / n
    mean_ca = sum(r.citation_accuracy for r in results) / n
    overall = sum(r.overall_score for r in results) / n
    return EvaluationSuiteReport(
        case_count=n,
        mean_context_precision=mean_cp,
        mean_context_recall=mean_cr,
        mean_answer_faithfulness=mean_af,
        mean_answer_relevance=mean_ar,
        mean_citation_accuracy=mean_ca,
        overall_score=overall,
        cases=results,
    )
