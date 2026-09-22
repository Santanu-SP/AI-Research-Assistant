# Local retrieval evaluation template

Upload 3–5 research PDFs owned by one test account, confirm each reaches
`indexed`, then call `POST /api/v1/research/retrieve` for each question below.
Record whether an appropriate chunk appears in the first 24 candidates; do not
score generated answers because PR 2 has no answer-generation stage.

| Question type | Example question | Expected evidence to inspect |
| --- | --- | --- |
| Direct fact | What sample size was used? | Methods passage with the count |
| Exact term | Where is `CRISPR-Cas9` discussed? | Exact terminology |
| Abbreviation | What does `RCT` refer to here? | Definition or study-design passage |
| Method | What methodology was used? | Methods section |
| Paraphrase | How did the researchers measure outcomes? | Outcome-measurement passage |
| Multi-chunk | What limitations were reported? | More than one limitations passage |
| DOI fragment | Which paper mentions `10.1234/example`? | Metadata-adjacent chunk |
| Author name | What does the work by the listed first author conclude? | Relevant paper chunk |
| Negative control | What does the paper say about lunar geology? | No irrelevant high-ranking result |
| Comparative | How do the two included studies differ in design? | Candidates from both PDFs |
