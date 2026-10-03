import os
import asyncio

import httpx
import pytest

from app.core.config import settings
from app.services.scholarly import provider_clients


pytestmark = [pytest.mark.integration, pytest.mark.live, pytest.mark.network]


@pytest.mark.skipif(
    os.getenv("RUN_PROVIDER_LIVE_TESTS") != "1",
    reason="RUN_PROVIDER_LIVE_TESTS is not enabled",
)
def test_live_crossref_and_openalex_doi_lookup() -> None:
    async def run():
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
            crossref, openalex = provider_clients(settings, client)
            doi = "10.7717/peerj.4375"
            return doi, await crossref.lookup_doi(doi), await openalex.lookup_doi(doi)

    doi, crossref_result, openalex_result = asyncio.run(run())
    assert crossref_result is not None and crossref_result.doi == doi
    assert openalex_result is not None and openalex_result.doi == doi
