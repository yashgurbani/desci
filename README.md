# DeSci Landscape Mapper

Interactive competitive intelligence tool mapping 78+ Decentralized Science projects, 33 key people, and 65 relationships.

## Files

- `index.html` — App (single-file, loads data.json via fetch)
- `data.json` — All landscape data (78 nodes, 65 edges, 33 people)

## Features

- **Force-directed graph** with color-coded edges by relationship type
- **Directory table** sortable by overlap %, credibility score, tech stack
- **People cards + People Graph** showing person-organization network
- **Literature tab** pulling from Zotero group 6075364
- **Overlap filter** — filter by technology overlap with your platform (12 categories)
- **Score sliders** — filter by Overlap %, Decentralization %, Credibility Score, Profit Score
- **Credibility Score** — auto-calculated from website, GitHub, stage, funding signals
- **Profit Score** — financial model assessment (0 = commons, 100 = profit-extraction)
- **Legal Structure filter** — filter by nonprofit, foundation, DAO, hybrid, for-profit
- **Tech term glossary** — hover DePIN, ZK, SBT, DAO etc. for definitions
- **Edge hover tooltips** — see connection type and label on hover
- **Collapsible legend** — click to minimize
- **GitHub sync** — auto-detects GitHub Pages URL, debounced auto-push

## Collaboration

First visit prompts for a GitHub Personal Access Token (fine-grained, Contents read+write). Edits auto-push after 2 seconds.

## Data Schema

Each node has:
- `overlapScore` (0-100): How much this project overlaps with your platform
- `credScore` (0-100): Auto-calculated credibility from web presence, GitHub, funding, stage
- `decen` (0-100): Decentralization level
- `decentNote`: Qualitative explanation of decentralization
- `compNote`: Strategic comparison to your platform
- `techStack`: Core technologies
- `overlapTags`: Technology categories for overlap filtering

### Financial Model Fields (NEW)

Each node now includes financial model data:

- `profitScore` (0-100): Financial model orientation score
- `finModel`: Description of revenue sources and funding model
- `legalStructure`: Legal entity type (nonprofit, foundation, DAO, hybrid, for-profit)
- `apc`: Whether the organization charges Article Processing Charges
- `finNote`: Detailed notes on values, incentives, and UNESCO alignment
- `fundingRaised`: Total funding raised (if known)

### Profit Score Rubric

| Score | Profile | Description |
|-------|---------|-------------|
| 0-15 | **Pure Commons** | Nonprofit, no token, no APC, grant-funded. Strong UNESCO Open Science alignment. |
| 15-35 | **Mission-Aligned** | DAO treasury, utility token with minimal speculation, grant + earned revenue mix. |
| 35-55 | **Hybrid** | Token with some speculation, services revenue, mixed incentives. |
| 55-75 | **Market-Driven** | VC-backed, token speculation, "public goods" rhetoric but commercial structure. |
| 75-100 | **Profit-Extraction** | Series A+, APC model, shareholder value maximization. |

### Scoring Methodology

The score weights multiple factors:

1. **Funding Source** (primary weight)
   - Grants/donations → lower score
   - Token sales → medium score  
   - VC rounds → higher score

2. **Revenue Model**
   - No fees for researchers → lower score
   - Platform fees/services → medium score
   - APCs or subscription paywalls → higher score

3. **Legal Structure**
   - 501(c)(3) nonprofit → lower score
   - Foundation/DAO → medium score
   - For-profit C-Corp/GmbH → higher score

4. **Incentive Alignment**
   - Funds researchers, doesn't charge them → lower score
   - Mixed (funds some, charges others) → medium score
   - Extracts value from researcher labor → higher score

### UNESCO Open Science Alignment

Organizations scoring 0-30 generally align with UNESCO's Open Science Recommendation principles:
- No financial barriers to participation
- Open access to outputs
- Community governance
- Transparent operations
- Non-extractive business models

Organizations scoring 70+ typically conflict with these principles through:
- APCs that exclude under-resourced researchers
- Token speculation creating misaligned incentives
- VC pressure for profit extraction
- Proprietary lock-in strategies
