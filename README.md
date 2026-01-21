# 🎶 SongSage
### Conversational Bioacoustic Wildlife Monitoring with BirdNET and MCP
SongSage is a Model Context Protocol (MCP) layer for bioacoustic analysis that augments BirdNET-Analyzer-Sierra detections with contextual reasoning, uncertainty-aware summaries, and ecologist-oriented insight extraction.

Rather than stopping at raw species detections, SongSage enables natural-language ecological interpretation of BirdNET outputs—helping researchers explore patterns, confidence, rarity, and temporal dynamics in large-scale acoustic datasets.

## Why SongSage Exists

Bioacoustic monitoring is increasingly used to study biodiversity and ecosystem health, but the outputs of state-of-the-art models like BirdNET are typically static files that require custom scripts and technical expertise to analyze.

SongSage turns these detections into an interactive, conversational analysis system. By exposing BirdNET results through a Model Context Protocol (MCP) server, ecologists, conservation practitioners, and citizen scientists can query, summarize, and visualize real-world acoustic data using natural language—without writing code.


## 🔍 Motivation: From Research to Real-World Use

Bioacoustic sensing is a scalable, low-impact approach for monitoring bird populations, but the outputs of state-of-the-art models like BirdNET are often difficult to explore without custom analysis pipelines.

Inspired by multimodal wildlife monitoring research at the SmartWilds framework, SongSage focuses on the missing interaction layer—turning BirdNET detections into an interactive system that supports human-in-the-loop exploration and real-world ecological analysis.

## 🧭 What Is SongSage?

SongSage is an interactive bioacoustic analysis system that connects BirdNET’s bird species detections with a conversational AI interface. It allows users to query, summarize, and visualize bird activity from real-world audio recordings using natural language instead of custom scripts.

Designed for ecologists, conservation practitioners, and citizen scientists, SongSage transforms static BirdNET outputs into a usable analysis layer, supporting exploratory data analysis, long-term monitoring, and human-in-the-loop ecological insight.

## 🏗️ System Architecture

```mermaid
flowchart LR
  U[Ecologist / Citizen Scientist] -->|Natural language queries| C[Claude Desktop / LLM Client]
  C -->|MCP (JSON-RPC)| S[SongSage MCP Server]

  A[Audio Recordings\n(WAV/MP3/FLAC...)] --> B[BirdNET-Analyzer]
  B -->|Detections| R[Results Directory\n(CSV/labels)]
  R -->|Load + Normalize| S

  S -->|Query + Aggregate| Q[Analytics Engine\n(pandas/numpy)]
  S -->|Visualize| V[Heatmaps / Plots\n(matplotlib)]
  S -->|Export| E[Exports\n(CSV summaries)]

  V --> O[PNG Outputs]
  Q --> O
  E --> O

