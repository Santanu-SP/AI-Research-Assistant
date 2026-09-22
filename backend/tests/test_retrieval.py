from types import SimpleNamespace
from uuid import uuid4

from app.services.retrieval import RankedChunk, fuse


def test_rrf_deduplicates_same_chunk_and_prefers_agreement() -> None:
    shared = SimpleNamespace(id=uuid4())
    vector_only = SimpleNamespace(id=uuid4())
    keyword_only = SimpleNamespace(id=uuid4())
    result = fuse(
        [RankedChunk(shared, vector_score=0.9), RankedChunk(vector_only, vector_score=0.8)],
        [RankedChunk(shared, keyword_score=0.7), RankedChunk(keyword_only, keyword_score=0.6)],
        limit=24,
    )
    assert result[0].chunk.id == shared.id
    assert {item.chunk.id for item in result[1:]} == {vector_only.id, keyword_only.id}
    assert result[0].vector_score == 0.9
    assert result[0].keyword_score == 0.7
