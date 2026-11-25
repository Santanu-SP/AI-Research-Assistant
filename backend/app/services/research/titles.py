"""Short chat title generation, sanitization, and legacy backfill helpers."""

from __future__ import annotations

import logging
import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)

MAX_CHAT_TITLE_WORDS = 5
FALLBACK_TITLE_MAX_LENGTH = 80
DEFAULT_CHAT_TITLE = "New Research"

_LEADING_SCAFFOLD_RE = re.compile(
    r"^(?:"
    r"(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"please\s+|"
    r"does\s+anyone\s+know\s+(?:if\s+|whether\s+|about\s+)?|"
    r"tell\s+me\s+(?:everything|all|more)?\s*(?:you\s+know\s+)?(?:about\s+)?|"
    r"(?:help\s+me|show\s+me|find\s+out)\s+|"
    r"i(?:'m|\s+am)\s+looking\s+(?:for|to\s+(?:find|understand|learn))\s+(?:about\s+)?|"
    r"i\s+(?:want|need|would\s+like)\s+to\s+(?:know|understand|learn)\s+(?:about\s+)?|"
    r"write\s+(?:me\s+)?(?:an?\s+)?(?:detailed|short|brief|full|comprehensive)?\s*(?:report|summary|essay|overview|analysis)\s+(?:on|about|of)\s+|"
    r"give\s+me\s+(?:an?|some)?\s*(?:detailed\s+)?(?:overview|summary|explanation|list|details|info|information|breakdown)\s+(?:of|on|about)\s+|"
    r"what\s+happened\s+(?:in|with|to)\s+(?:the\s+)?|"
    r"(?:is|are)\s+there\s+(?:an?|any)\s+|"
    r"(?:latest|recent|current)\s+news\s+(?:about|on)\s+|"
    r"(?:explain|describe|summarize|summarise|compare|contrast|analyze|analyse|evaluate|outline|list|define|discuss)\s+|"
    r"(?:what|how|why|when|where|which|who)\s+(?:is|are|was|were|does|do|did|can|could|would|should|to)\s+(?:the\s+|a\s+|an\s+)?|"
    r"(?:what|how|why|when|where|which|who)\s+|"
    r"(?:is|are|was|were|do|does|did|can|could|would|should)\s+(?:the\s+|a\s+|an\s+)?|"
    r"whether\s+"
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

# Minor connector words kept lowercase when in non-initial title positions.
_MINOR_TITLE_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "in",
        "on",
        "for",
        "to",
        "with",
        "vs",
        "by",
        "at",
        "from",
    }
)

# Dropped when stronger topic tokens remain so titles are not stuffed with meta chatter.
_WEAK_FILLER_WORDS = frozenset(
    {
        "handle",
        "handles",
        "work",
        "works",
        "working",
        "happen",
        "happens",
        "happened",
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
        "tell",
        "know",
        "everything",
        "something",
        "anything",
        "detailed",
        "report",
        "information",
        "details",
        "question",
        "answer",
        "write",
        "make",
        "create",
        "find",
        "check",
        "latest",
        "recent",
        "current",
        "today",
        "paper",
        "papers",
        "document",
        "documents",
        "uploaded",
        "sources",
        "file",
        "files",
        "whether",
        "possible",
        "need",
        "want",
        "looking",
        "help",
        "please",
        "understand",
        "learn",
        "really",
        "actually",
    }
)

_EDGE_PUNCTUATION = "\"'`“”‘’()[]{}<>.,!?;:–—-*#"
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.IGNORECASE | re.DOTALL)
_TITLE_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:sure|certainly|of\s+course)[,!.]*\s+"
    r")?"
    r"(?:(?:here\s+(?:is|are)\s+(?:a|an|the)?\s*(?:short|concise|brief|suggested)?\s*(?:sidebar|chat)?\s*(?:title|topic|summary|name|heading)?\s*(?:for\s+(?:your|the)\s+question)?\s*[:\-–—]\s*)|"
    r"(?:(?:chat|sidebar)\s+)?(?:title|topic|summary|name|heading)\s*[:\-–—]\s*)",
    re.IGNORECASE,
)
_INVALID_TITLE_RE = re.compile(
    r"\b(?:cannot\s+answer|can't\s+answer|unable\s+to\s+answer|please\s+provide|more\s+context|"
    r"as\s+an\s+ai|i\s+am\s+sorry|i'm\s+sorry|sorry,|no\s+question|untitled|"
    r"not\s+enough\s+information)\b|^error\s*:",
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


def _format_title_word(
    word: str,
    *,
    is_all_caps_input: bool,
    is_first: bool = True,
) -> str:
    lower = word.lower()
    if lower == "vs":
        return "vs"
    if not is_first and lower in _MINOR_TITLE_WORDS:
        return lower
    if not is_all_caps_input and (
        any(ch.isupper() for ch in word[1:])
        or (word.isupper() and len(word) <= 6)
    ):
        return word
    if "-" in word:
        return "-".join(
            _format_title_word(
                part,
                is_all_caps_input=is_all_caps_input,
                is_first=is_first and index == 0,
            )
            if part
            else ""
            for index, part in enumerate(word.split("-"))
        )
    for index, ch in enumerate(word):
        if ch.isalpha():
            return word[:index] + ch.upper() + word[index + 1 :].lower()
    return word


def _join_within_limit(words: list[str], max_length: int = FALLBACK_TITLE_MAX_LENGTH) -> str:
    capped = words[:MAX_CHAT_TITLE_WORDS]
    while len(capped) > 1 and capped[-1].lower() in _STOPWORDS:
        capped.pop()
    while capped:
        joined = " ".join(capped)
        if len(joined) <= max_length:
            return joined
        if len(capped) == 1:
            return capped[0][:max_length].rstrip(" -") or DEFAULT_CHAT_TITLE
        capped.pop()
        while len(capped) > 1 and capped[-1].lower() in _STOPWORDS:
            capped.pop()
    return DEFAULT_CHAT_TITLE


def build_fallback_title(question: str) -> str:
    """Derive a natural, coherent phrase of at most 5 words from a research question."""
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

    # Trim leading/trailing filler & stopwords while keeping short natural phrasing intact.
    trim_mask = _STOPWORDS | _WEAK_FILLER_WORDS
    trimmed_tokens = list(active_tokens)
    while trimmed_tokens and trimmed_tokens[0].lower() in trim_mask:
        trimmed_tokens.pop(0)
    while trimmed_tokens and trimmed_tokens[-1].lower() in trim_mask:
        trimmed_tokens.pop()

    strong_count = sum(1 for tok in trimmed_tokens if tok.lower() not in trim_mask)
    if 1 <= len(trimmed_tokens) <= MAX_CHAT_TITLE_WORDS and strong_count >= 1:
        formatted = [
            _format_title_word(word, is_all_caps_input=is_all_caps, is_first=(index == 0))
            for index, word in enumerate(trimmed_tokens)
        ]
        return _join_within_limit(formatted)

    # Longer questions: pick key content tokens (preserving "X vs Y" at position 1).
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

    if not kept_vs:
        stronger = [w for w in content_words if w.lower() not in _WEAK_FILLER_WORDS]
        if len(stronger) >= 2:
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
        _format_title_word(word, is_all_caps_input=is_all_caps, is_first=(index == 0))
        for index, word in enumerate(content_words[:MAX_CHAT_TITLE_WORDS])
    ]
    return _join_within_limit(formatted)


def normalize_short_title(raw: str, *, fallback_question: str | None = None) -> str:
    """Clean model output and guarantee a coherent phrase of at most 5 words."""
    text = _THINK_BLOCK_RE.sub(" ", raw or "")
    text = _UNCLOSED_THINK_RE.sub(" ", text).strip()

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if not first_line:
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    cleaned = _LIST_PREFIX_RE.sub("", first_line)
    cleaned = _TITLE_PREFIX_RE.sub("", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").replace("`", "")
    cleaned = cleaned.strip(_EDGE_PUNCTUATION + " ")
    if not cleaned or _INVALID_TITLE_RE.search(cleaned):
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    tokens = [tok for part in cleaned.split() if (tok := _clean_token(part))]
    if not tokens:
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    if len(tokens) > MAX_CHAT_TITLE_WORDS:
        if len(tokens) > 8 and fallback_question:
            return build_fallback_title(fallback_question)
        return build_fallback_title(cleaned)

    while len(tokens) > 1 and tokens[-1].lower() in _STOPWORDS:
        tokens.pop()

    is_all_caps = any(ch.isalpha() for ch in cleaned) and cleaned == cleaned.upper()
    if all(tok.lower() in _STOPWORDS for tok in tokens):
        return build_fallback_title(fallback_question) if fallback_question else DEFAULT_CHAT_TITLE

    formatted = [
        _format_title_word(tok, is_all_caps_input=is_all_caps, is_first=(index == 0))
        for index, tok in enumerate(tokens)
    ]
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
