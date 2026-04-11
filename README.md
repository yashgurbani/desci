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
- **Score sliders** — filter by Overlap %, Decentralization %, Credibility Score
- **Credibility Score** — auto-calculated from website, GitHub, stage, funding signals
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
