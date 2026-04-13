# DeSci Map - README

This map is a **research dataset + visualization** of DeSci, open-science, publishing, infrastructure, and adjacent entities. It mixes **factual fields** (legal form, funding disclosures, revenue model, sources) with **computed internal metrics** (commerciality, open-science fit, overlap with us).

## Most important rule
Treat these as the source of truth, in this order:
1. **`provenance.fieldSources`**
2. **`provenance.materialClaims`**
3. **`financialSummaryStrict`**
4. Computed scores

If a score and a source-backed fact seem to conflict, **the source-backed fact wins**.

## Core node fields
- **`name`, `id`**: Display name and internal identifier.
- **`desc`**: One-line description.
- **`type`**: High-level category, such as Publishing, BioDAO, Compute, HealthTech, Infrastructure.
- **`stack`**: Main layer in the map:
  - `infrastructure`
  - `application`
  - `governance`
- **`stage`**: Rough maturity label, such as Early, Beta, Live.
- **`tags`**: General topic tags.
- **`overlapTags`**: Where the node overlaps with our platform thesis, such as publishing, peer-review, reputation, compute, AI, smart contracts, data sovereignty.

## Strategic/internal metrics
These are **computed or analyst-assigned internal metrics**, not factual claims.

- **`overlapScore` (0-100)**: How much the node overlaps with our own product direction.
  - Higher = more direct strategic overlap, competition, adjacency, or partnership relevance.
- **`decen` (0-100)**: How decentralized the system appears in practice.
  - Higher = more distributed governance, infrastructure, access, or control.
- **`credScore` (0-100)**: Relevance to scientific credibility, trust, verification, peer review, or reputation.
  - Higher = more relevant to credibility infrastructure and trust workflows.

## Architecture / stack-depth metrics
The `s1`-`s5` fields describe how strongly a node participates in each layer of the stack.

Scale:
- `0` = absent
- `1` = light
- `2` = moderate
- `3` = strong

Dimensions:
- **`s1`** = Data
- **`s2`** = Ledger / on-chain layer
- **`s3`** = AI / analysis / automation
- **`s4`** = Proof / verification / cryptographic assurance
- **`s5`** = Governance

## Financial / business-model fields
These aim to describe **how the entity is financed, who pays, and what incentives shape it**.

### Short summary fields
- **`funding`**: Legacy shorthand.
- **`fundingRaised`**: Human-readable funding summary. May refer to VC, grants, treasury, ICO proceeds, or disclosed capital. Always verify against sources.
- **`finModel`**: Short business-model summary.
- **`finNote`**: Analyst note on incentives and structure.
- **`legalStructure`**: Short label such as nonprofit, foundation, DAO, hybrid, for-profit.
- **`apc`**: Whether the model includes article processing charges.

### Structured financial fields (`financials`)
- **`revenueSources`**: Main revenue/capital sources, such as grants, memberships, services, subscriptions, APCs, token sales, treasury, licensing.
- **`researcherPays`**: Whether researchers/authors/users pay directly.
- **`institutionPays`**: Whether institutions pay directly.
- **`apcAmountText`**: Human-readable APC or publication-fee note, if relevant.
- **`annualRevenueText`**: Human-readable revenue note, when disclosed.
- **`treasuryText`**: Human-readable treasury note, when relevant.
- **`tokenRole`**: What the token does, if any, such as governance, incentives, access, speculation, protocol fees.
- **`jurisdiction`**: Country / legal jurisdiction.
- **`legalForm`**: More specific legal wrapper, such as 501(c)(3), GmbH, OU, SAS, foundation, association.
- **`openScienceAlignment`**: Short qualitative read of business-model fit with open science.
- **`openScienceAlignmentNote`**: Why that alignment call was made.
- **`financialSummary`**: General summary.
- **`financialSummaryStrict`**: **Conservative source-backed summary**. Prefer this one when presenting.

## Computed score fields
These are **internal composite metrics**, not direct facts.

- **`profitScore` (0-100)**: Commerciality / profit-orientation score.
  - `0` = commons/nonprofit orientation
  - `100` = strongly commercial, investor-, fee-, or market-driven
- **`openScienceScore` (0-100)**: Open-science business-model compatibility.
  - `0` = weak fit with open-science-compatible models
  - `100` = strong fit with community/open-infrastructure norms
- **`financials.openScienceCompatibilityBand`**: Broad band, such as weak, mixed, moderate, strong.
- **`financials.openScienceCompatibilityReasons`**: Main drivers behind the open-science score.
- **`financials.scoreBreakdown`**: Components of `profitScore`:
  - `structure`
  - `revenue`
  - `capital`
  - `total`
- **`financials.scoreAudit`**: Audit trail for the latest score pass.

## Provenance / confidence fields
These fields tell you **how safe it is to rely on the entry**.

- **`provenance.confidence`**:
  - `high` = key legal/financial facts verified from official or filing-grade sources
  - `medium` = core model verified, but some details remain partial
  - `low` = identity/product exists, but financial/legal specifics are unresolved
- **`provenance.attributionStatus`**:
  - `strict-source-clean`
  - `source-backed-with-gaps`
  - `low-confidence`
- **`provenance.sources`**: Source URLs.
- **`provenance.fieldSources`**: Best source mapping for specific fields. This is the most useful provenance object.
- **`provenance.materialClaims`**: Short source-backed claims worth presenting.
- **`provenance.fieldStatus`**: Per-field reliability / disclosure status.
- **`provenance.hasUnverifiedClaims`**: Whether unresolved claims remain.
- **`provenance.lastVerified`**: Last audit date.
- **`sourceAsterisk`**: Visual warning flag for unresolved or weaker attribution.

## How to present this safely
- Use **`financialSummaryStrict`** and **`provenance.materialClaims`** in slides or public summaries.
- Use **`profitScore`** and **`openScienceScore`** as **interpretive lenses**, not as factual claims.
- Do not compare treasury, VC raised, grant income, AUM, and revenue as if they were the same thing.
- If a node is `source-backed-with-gaps` or `low-confidence`, present it as **partial** rather than settled.

## How to read the Values view
- **X-axis** = `profitScore`
- **Y-axis** = `openScienceScore`
- **Point size** = `overlapScore`
- **Outline strength** = `decen`
- **Ring / confidence styling** = provenance confidence
- **Color** = stack layer

This lets you quickly see:
- commons-aligned infrastructure
- hybrid/open-core models
- commercially pressured models
- nodes that matter most to us strategically

## Final note
This dataset is designed for **strategic clarity**, not for legal due diligence. It is strongest where public disclosures are good, and intentionally conservative where they are not.

## Signals collector
The dashboard now supports a local collector for targeted signals.

Files:
- `signals_config.json`: hand-curated keywords, X handles, subreddits, and RSS/blog feeds
- `signals_collector.py`: local collector that writes `signals_feed.json`
- `signals_feed.json`: output consumed by the `Signals` tab and Home widget

Basic usage:
```bash
python signals_collector.py
```

What it pulls:
- Google News RSS for targeted DeSci / metascience / publishing queries
- Reddit RSS for selected subreddits and keyword searches
- best-effort X signals via public Nitter / RSSHub adapters plus X-focused news fallbacks
- blog / RSS feeds from curated sources and top map entities
- GitHub Atom feeds for tracked technical projects

Hand-curation flow:
- add or remove `general_keywords`, `x_keywords`, and `reddit_keywords`
- add specific `x_handles`
- add specific `reddit_subreddits`
- add official blog feeds to `rss_feeds`
- use `news_keywords` for the tighter news/web watchlist that should drive daily monitoring
- keep `strict_curated_mode` on so only the sources you trust dominate the dashboard
- leave `include_map_nodes` on if you want the collector to auto-follow key orgs from the map
- leave `include_map_people` off unless you intentionally want named individuals auto-added
- keep `enable_x_keyword_search` and `enable_reddit_search` off unless you want broader discovery with more noise
- add junk phrases to `blocked_terms` when something keeps slipping through
- add low-signal domains to `blocked_domains` when you want to permanently suppress them

The frontend defaults to `signals_feed.json` when present via `signalCollectorUrl`.

## OSINT platform
The dashboard now has a broader entity-intelligence layer that treats organizations and people as tracked entities and enriches them with research, opportunity, and signal data.

Core files:
- `build_source_registry.py`: builds `source_registry.json` from `data.json` and `signals_config.json`
- `collector_research_graph.py`: builds `research_graph.json` from OpenAlex, Crossref, and optional ORCID credentials
- `collector_entity_intel.py`: builds `entity_intel.json` from entity blogs, X, GitHub, and exact-name web/news queries
- `collector_opportunities.py`: builds `opportunity_intel.json` from Grants.gov, NIH RePORTER, GDELT, and optional CORDIS
- `collect_osint_all.py`: convenience runner for the full pipeline

Outputs:
- `source_registry.json`: canonical watchlist of organizations, people, aliases, domains, handles, repos, and tracked topics
- `research_graph.json`: matched works, authors, institutions, and research-topic analytics
- `entity_intel.json`: entity-level signals grouped by organization and person
- `opportunity_intel.json`: external grant, project, and article hits by tracked topic

Suggested run order:
```bash
python build_source_registry.py
python collector_research_graph.py
python collector_entity_intel.py
python collector_opportunities.py
```

Or:
```bash
python collect_osint_all.py
```

What the UI uses:
- `People` tab: merged people + organizations as one entity-intelligence surface
- right sidebar for people: linked orgs, registry info, latest signals, research graph, opportunity intelligence
- right sidebar for organizations: registry info, latest signals, research graph, opportunity intelligence
- `Grants` tab: curated tracker plus live collector-status summary

Notes:
- ORCID is optional and requires `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET`
- CORDIS is optional and requires `CORDIS_DET_URL` and `CORDIS_API_KEY`
- the browser UI can run without these files, but the richer OSINT experience appears once the collector outputs exist

