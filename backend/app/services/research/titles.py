"""Short chat title generation, sanitization, and legacy backfill helpers."""

from __future__ import annotations

import logging
import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)

MAX_CHAT_TITLE_WORDS = 3
FALLBACK_TITLE_MAX_LENGTH = 80
DEFAULT_CHAT_TITLE = "New Research"

_LEADING_SCAFFOLD_RE = re.compile(
    r"^(?:"
    r"(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"please\s+|"
    r"(?:help\s+me|tell\s+me\s+about|tell\s+me|show\s+me|find\s+out)\s+|"
    r"i\s+(?:want|need|would\s+like)\s+to\s+(?:know|understand|learn)\s+(?:about\s+)?|"
    r"give\s+me\s+(?:an?\s+)?(?:overview|summary|explanation|list)\s+of\s+|"
    r"(?:explain|describe|summarize|summarise|compare|contrast|analyze|analyse|evaluate|outline|list|define|discuss)\s+|"
    r"(?:what|how|why|when|where|which|who)\s+(?:is|are|was|were|does|do|did|can|could|would|should|to)\s+(?:the\s+|a\s+|an\s+)?|"
    r"(?:what|how|why|when|where|which|who)\s+|"
    r"(?:is|are|was|were|do|does|did|can|could|would|should)\s+(?:the\s+|a\s+|an\s+)?"
    r")+",
    re.IGNORECASE,
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "so",
        "as",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "by",
        "with",
        "from",
        "about",
        "into",
        "onto",
        "upon",
        "over",
        "under",
        "between",
        "among",
        "through",
        "during",
        "before",
        "after",
        "within",
        "without",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "their",
        "them",
        "we",
        "our",
        "you",
        "your",
        "my",
        "me",
        "i",
        "he",
        "she",
        "his",
        "her",
        "there",
        "here",
        "all",
        "some",
        "any",
        "each",
        "every",
        "more",
        "most",
        "other",
        "such",
        "very",
        "just",
        "only",
        "also",
        "really",
        "actually",
        "basically",
        "how",
        "what",
        "why",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "regarding",
        "following",
        "versus",
        "vs",
    }
)

# Dropped only when at least MAX_CHAT_TITLE_WORDS stronger tokens remain.
_WEAK_FILLER_WORDS = frozenset(
    {
        "handle",
        "handles",
        "work",
        "works",
        "working",
        "happen",
        "happens",
        "exist",
        "exists",
        "occur",
        "occurs",
        "say",
        "says",
        "explain",
        "explains",
        "describe",
        "describes",
        "summarize",
        "summarise",
        "compare",
        "difference",
        "differences",
        "overview",
        "summary",
    }
)

_EDGE_PUNCTUATION = "\"'`“”‘’()[]{}<>.,!?;:–—-*#"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)
_TITLE_PREFIX_RE = re.compile(
    r"^(?:(?:here\s+is\s+(?:a|the)?\s*(?:short|concise)?\s*)?(?:chat\s+)?(?:title|topic|summary|name|heading)\s*[:\-–—]\s*)",
    re.IGNORECASE,
)
_LIST_PREFIX_RE = re.compile(r"^(?:[-*•]+|\d+[.)])\s+")


def legacy_fallback_title(question: str) -> str:
    """Return the pre-feature full-question fallback title (up to 80 chars)."""
    normalized = " ".join(question.split())
    if len(normalized) <= FALLBACK_TITLE_MAX_LENGTH:
        return normalized

    shortened = normalized[: FALLBACK_TITLE_MAX_LENGTH - 3].rstrip(" ,.;:-")
    return f"{shortened}..."


def _clean_token(raw: str) -> str:
    cleaned = raw.strip(_EDGE_PUNCTUATION)
    if not cleaned or not any(ch.isalnum() for ch in cleaned):
        return ""
    return cleaned


def _format_title_word(word: str, *, is_all_caps_input: bool) -> str:
    if word.lower() == "vs":
        return "vs"
    if not is_all_caps_input and (
        any(ch.isupper() for ch in word[1:])
        or (word.isupper() and len(word) <= 6)
    ):
        return word
    if "-" in word:
        return "-".join(
            _format_title_word(part, is_all_caps_input=is_all_caps_input)
            if part
            else ""
            for part in word.split("-")
        )
    for index, ch in enumerate(word):
        if ch.isalpha():
            return word[:index] + ch.upper() + word[index + 1 :].lower()
    return word


def _join_within_limit(words: list[str], max_length: int = FALLBACK_TITLE_MAX_LENGTH) -> str:
    capped = words[:MAX_CHAT_TITLE_WORDS]
    while capped:
        joined = " ".join(capped)
        if len(joined) <= max_length:
            return joined
        if len(capped) == 1:
            return capped[0][:max_length].rstrip(" -") or DEFAULT_CHAT_TITLE
        capped.pop()
    return DEFAULT_CHAT_TITLE


def build_fallback_title(question: str) -> str:
    """Derive a deterministic phrase of at most 3 words from a research question."""
    normalized = " ".join((question or "").split())
    if not normalized:
        return DEFAULT_CHAT_TITLE

    is_all_caps = any(ch.isalpha() for ch in normalized) and normalized == normalized.upper()
    raw_tokens = [tok for raw in normalized.split() if (tok := _clean_token(raw))]
    if not raw_tokens:
        return DEFAULT_CHAT_TITLE

    stripped = _LEADING_SCAFFOLD_RE.sub("", normalized).strip()
    stripped_tokens = [tok for raw in stripped.split() if (tok := _clean_token(raw))]
    active_tokens = stripped_tokens if stripped_tokens else raw_tokens

    # Preserve "X vs Y" comparisons when "vs"/"versus" sits cleanly at position 1.
    content_words: list[str] = []
    seen_lower: set[str] = set()
    kept_vs = False
    for index, token in enumerate(active_tokens):
        lower = token.lower()
        if lower in {"vs", "versus"}:
            if (
                not kept_vs
                and len(content_words) == 1
                and index + 1 < len(active_tokens)
                and active_tokens[index + 1].lower() not in _STOPWORDS
            ):
                content_words.append("vs")
                kept_vs = True
            continue
        if lower in _STOPWORDS or lower in seen_lower:
            continue
        seen_lower.add(lower)
        content_words.append(token)

    if len(content_words) > MAX_CHAT_TITLE_WORDS and not kept_vs:
        stronger = [w for w in content_words if w.lower() not in _WEAK_FILLER_WORDS]
        if len(stronger) >= MAX_CHAT_TITLE_WORDS:
            content_words = stronger

    if not content_words:
        deduped_raw: list[str] = []
        seen_raw: set[str] = set()
        for token in active_tokens:
            lower = token.lower()
            if lower not in seen_raw:
                seen_raw.add(lower)
                deduped_raw.append(token)
        content_words = deduped_raw

    formatted = [
        _format_title_word(word, is_all_caps_input=is_all_caps)
        for word in content_words[:MAX_CHAT_TITLE_WORDS]
    ]
    return _join_within_limit(formatted)


def normalize_short_title(raw: str, *, fallback_question: str | None = None) -> str:
    """Clean model output and guarantee a non-empty phrase of at most 3 words."""
    text = _THINK_BLOCK_RE.sub(" ", raw or "")
    text = _UNCLOSED_THINK_RE.sub(" ", text).strip()

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    cleaned = _LIST_PREFIX_RE.sub("", first_line)
    cleaned = _TITLE_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    cleaned = cleaned.strip(_EDGE_PUNCTUATION + " ")
    if not cleaned:
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    tokens = [tok for part in cleaned.split() if (tok := _clean_token(part))]
    if not tokens:
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    if len(tokens) > MAX_CHAT_TITLE_WORDS:
        return build_fallback_title(cleaned)

    is_all_caps = any(ch.isalpha() for ch in cleaned) and cleaned == cleaned.upper()
    if all(tok.lower() in _STOPWORDS for tok in tokens) and fallback_question:
        return build_fallback_title(fallback_question)

    formatted = [_format_title_word(tok, is_all_caps_input=is_all_caps) for tok in tokens]
    return _join_within_limit(formatted)


def is_auto_generated_title(title: str | None, question: str) -> bool:
    """Return True when ``title`` still matches an auto-generated fallback for ``question``."""
    if not title:
        return True
    cleaned = title.strip()
    return cleaned in {
        build_fallback_title(question),
        legacy_fallback_title(question),
    }


def backfill_legacy_research_titles(session: Session) -> int:
    """Shorten existing unedited full-question chat titles to <= 3-word phrases without altering timestamps."""
    from app.models.report import ResearchReport
    from app.models.research import Research

    records = list(
        session.scalars(
            select(Research).options(selectinload(Research.report))
        ).all()
    )
    updated = 0
    for record in records:
        if len(record.title.split()) <= MAX_CHAT_TITLE_WORDS:
            continue
        if record.title != legacy_fallback_title(record.question):
            continue
        short_title = build_fallback_title(record.question)
        if short_title == record.title:
            continue
        old_title = record.title
        session.execute(
            update(Research)
            .where(Research.id == record.id)
            .values(title=short_title, updated_at=record.updated_at)
        )
        if record.report is not None and record.report.title == old_title:
            session.execute(
                update(ResearchReport)
                .where(ResearchReport.id == record.report.id)
                .values(title=short_title, updated_at=record.report.updated_at)
            )
        updated += 1
    if updated:
        session.commit()
        logger.info("Shortened legacy research chat titles", extra={"updated_count": updated})
    return updated
