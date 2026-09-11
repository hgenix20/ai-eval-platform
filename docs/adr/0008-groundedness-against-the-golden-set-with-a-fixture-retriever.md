# ADR-0008: groundedness runs against the golden set through a fixture retriever

Status: accepted, 2026-09-11. Spec section 4.4, Phase 3.

## Context

The groundedness suite asks an agent to find one sentence in a real SEC filing
and quote it back. That needs a retrieval tool an agent can call, and a set of
questions whose answers are known.

The obvious tool was the live SignalNodus MCP server, whose 31 tools include
`filing_section` and `edgar_search`. A network-marked test has listed those
tools since Phase 2. Calling them is paid per call, and a 52-case suite calls a
retriever three to six times per case, every time anyone reruns the suite.
A gate row has to be reproducible on a pull request, which is a hard fit for a
metered endpoint.

The questions come from the SignalNodus section-boundary golden set, MIT,
commit `97b928b`, promoted 2026-08-25. It carries 88 filings, 32 of which list
`must_contain` anchor phrases, 53 phrases in total. Those phrases are the known
answers.

## Decision

The suite runs against `eval_platform/retrievers/edgar_fixture_server.py`, an
MCP server over committed fixtures. Each fixture is one item's section of one
filing, fetched once from sec.gov, converted to paragraphs, and cut to a window
of 40 paragraphs on each side of every anchor, with overlapping windows merged.
The build yielded 31 fixtures, 1,993 paragraphs, and 52 cases from 53 anchors.
One golden filing produced nothing: `nage-0001654954-20-005725-1A` is a 10-K/A
that names Item 1A only inside body sentences and never opens a section with
it, so there is no section to cut.

Finding the section is the part that takes judgment, and the anchors are what
settles it. A filing names an item several times: in the table of contents, at
the section itself, and often once per page as a running header or a
`(Continued)` line. The builder collects candidate headings, prefers those
carrying the item's title, tries them in document order, and takes the first
whose slice contains every anchor phrase the golden set lists for that filing.
The golden set validates the extraction, so a slice that starts at a page
header is caught by the anchors missing from it.

Paragraph ids index the whole section, not the kept window, so a search result
cites an id that survives a wider rebuild. The server exposes `list_filings`,
`search_filing`, and `get_paragraph`, returns error dicts for unknown
arguments, and raises nothing, so a wrong argument costs a step.

## Alternatives rejected

- **Run the suite against the live SignalNodus server.** Paid per call, and
  every rerun is a fresh bill for the same number. It stays available as an
  option, which is the point of putting the fixture behind the same MCP
  interface.
- **Write the questions by hand.** Hand-written anchors are what the author
  expected the filing to say. The golden set's anchors were published for a
  different purpose, so they don't encode this suite's assumptions.
- **Keep whole sections in the fixtures.** Some risk-factor sections run past
  80 paragraphs, and the committed corpus is already 1.0 MB at a 40-paragraph
  window. Widening it buys distractor text the search tool would rank below the
  anchor anyway.
- **Grade with the judge alone and skip the deterministic dimensions.** A judge
  can be wrong about whether a quote is real. `quotes_in_source` checks the
  quoted span against what the tools actually returned, which no model opinion
  can overturn.

## Consequences

- The suite reaches no network at run time, costs $0.00 in retrieval, and
  reproduces from the repository.
- The same suite runs against the live server unchanged, by swapping the target
  flags: `--mcp-url https://mcp.signalnodus.ai/ --mcp-authorization <key>`
  in place of `--mcp-command` and `--mcp-args`. Cases, graders, and metrics stay
  as they are, so a live run and a fixture run are comparable on everything
  except the retriever.
- Three of the 31 fixtures are small: one holds 3 paragraphs and two hold 7.
  The 3-paragraph one is Gold Star Tutoring Services' Item 1A, which reads in
  full "As a Smaller Reporting Company we are not required to provide the
  information required by this Item." Its anchor is guessable from the question
  alone, so on that case only `quotes_in_source` forces the agent to retrieve
  anything. Read the baseline knowing a few cases are that easy.
- Questions are templated from anchors, so the suite measures retrieval and
  faithful quotation, and it does not measure open-ended financial reasoning.
- What the published numbers describe is a 3B answerer over three tools. Swap
  the answerer and every figure moves. The gate's baseline records the target
  it was measured on, so a different model in that row reports not measured.
