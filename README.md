# 🎶 SongSage
SongSage is a Model Context Protocol (MCP) layer for bioacoustic analysis that augments BirdNET-Analyzer-Sierra detections with contextual reasoning, uncertainty-aware summaries, and ecologist-oriented insight extraction.

Rather than stopping at raw species detections, SongSage enables natural-language ecological interpretation of BirdNET outputs—helping researchers explore patterns, confidence, rarity, and temporal dynamics in large-scale acoustic datasets.

🌍 Motivation

BirdNET is highly effective at identifying bird species from audio recordings. However, in field-deployed acoustic monitoring, species detections alone are often insufficient for answering ecological questions at scale.

# Common challenges include:

- Large volumes of detections with limited ecological prioritization

- Difficulty identifying rare or unusual species

- Limited support for understanding temporal activity patterns

- Lack of structured reasoning about confidence and uncertainty

- Significant manual effort required for post-processing and interpretation

**SongSage was developed to address these limitations by adding a reasoning and interpretation layer on top of BirdNET outputs.**

# 🧠 What SongSage Does

SongSage augments BirdNET detections with:

🔍 **Contextual Reasoning**

Identifies rare, infrequent, or ecologically notable detections

Analyzes activity patterns across time

📊 **Uncertainty-Aware Summaries**

Aggregates detections with transparent confidence statistics

Supports quality assessment and expert review

🌱 **Ecologist-Oriented Insights**

Peak activity timing and diel patterns

Species-level behavioral signals

🗣️ **Natural Language Access**

Query bioacoustic data using natural language


# 🧩 Architecture Overview

Audio Recordings
      │
      ▼
 BirdNET Analyzer
      │
      ▼
 Detection CSVs
      │
      ▼
 ┌──────────────────┐
 │     SongSage     │   ← MCP Server 
 └──────────────────┘
      │
      ▼
 CLaude (via MCP)
      │
      ▼
 Ecological Insights

# 🔗 BirdNET Dependency

SongSage operates on detection outputs generated using
BirdNET-Analyzer-Sierra:
https://github.com/birdnet-team/BirdNET-Analyzer-Sierra

**BirdNET-Analyzer-Sierra provides large-scale acoustic inference with location- and season-aware filtering and structured CSV outputs.**

# ⚙️ Requirements

- Python 3.10+

- BirdNET Analyzer (BirdNET-Analyzer-Sierra)

- An MCP-compatible client ( Claude Desktop)

- macOS, Linux, or Windows


# 🚀 Installation
git clone https://github.com/your-org/songsage.git
cd songsage
python -m venv venv
source venv/bin/activate   # macOS / Linux
venv\Scripts\activate      # Windows
pip install -r requirements.txt


# 🌿 Real-World Usage

SongSage was developed to support real-world acoustic monitoring workflows, where BirdNET detections alone were insufficient for answering ecological questions at scale.

It has been used during acoustic monitoring at The Wilds Conservation Center as part of the SmartWilds project, informing its focus on scalability, interpretability, and uncertainty-aware summaries.

# 🧪 Example Questions

Which species were detected this week?

Which detections are rare or unusual?

When is bird activity highest?

