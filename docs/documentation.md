# SongSage Reference

**Version:** 1.0.0
**Platform:** Cross-platform (Linux, macOS, Windows)
**Python:** 3.10+

---

## Table of Contents

1. [Overview](#overview)
2. [What is BirdNET?](#what-is-birdnet)
3. [What is MCP (Model Context Protocol)?](#what-is-mcp-model-context-protocol)
4. [Architecture](#architecture)
5. [Technology Stack](#technology-stack)
6. [Tools Reference](#tools-reference)
7. [Resources Reference](#resources-reference)
8. [Prompts Reference](#prompts-reference)
9. [Data Handling](#data-handling)
10. [Visualization System](#visualization-system)
11. [Troubleshooting](#troubleshooting)

---

## Overview

SongSage is a Model Context Protocol (MCP) server that bridges BirdNET-Analyzer with Claude Desktop. It enables natural language interaction with bird detection data, allowing users to:

- Analyze audio recordings for bird species identification
- Query detection results with flexible filtering
- Generate visualizations and heatmaps of bird activity patterns
- Export data in multiple formats
- Perform complex multi-step analyses through guided prompts

### Core Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Audio Files    │────▶│ BirdNET-Analyzer│────▶│   CSV Results   │
│  (WAV, MP3...)  │     │                  │     │  (Detections)   │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Claude Desktop  │◀───▶│   MCP Server    │◀────│   Data Cache    │
│ (User Interface)│     │ (This Project)  │     │  (pandas/numpy) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │   Heatmaps/     │
                        │ Visualizations  │
                        └─────────────────┘
```

---

## What is BirdNET?

BirdNET-Analyzer is an AI-powered acoustic bird detection system developed by the Cornell Lab of Ornithology and Chemnitz University of Technology. It uses deep learning neural networks to identify bird species from their vocalizations in audio recordings.

| Feature | Description |
|---------|-------------|
| **Species Coverage** | 6,000+ bird species worldwide |
| **Audio Formats** | WAV, MP3, FLAC, OGG, M4A, AAC, WMA |
| **Detection Method** | 3-second audio segments analyzed by CNN |
| **Confidence Scores** | 0.0 to 1.0 scale indicating detection certainty |
| **Location Filtering** | Latitude/longitude to filter unlikely species |
| **Seasonal Filtering** | Week of year (1-48) to filter by migration patterns |

### BirdNET Output Formats

| Format | Extension | Description | Use Case |
|--------|-----------|-------------|----------|
| **CSV** | `.csv` | Comma-separated values | General analysis, this MCP server |
| **R** | `.r.csv` | R-compatible format | Statistical analysis in R |
| **Audacity** | `.txt` | Audacity label format | Audio annotation |
| **Raven** | `.raven.txt` | Raven selection table | Cornell Raven Pro software |
| **Kaleidoscope** | `.kscope.csv` | Wildlife Acoustics format | Kaleidoscope software |

### Standard CSV Columns

| Column | Type | Description |
|--------|------|-------------|
| `Start (s)` | float | Detection start time in seconds |
| `End (s)` | float | Detection end time in seconds |
| `Scientific name` | string | Latin species name |
| `Common name` | string | Common English name |
| `Confidence` | float | Detection confidence (0.0-1.0) |
| `File` | string | Source audio filename |

---

## What is MCP (Model Context Protocol)?

MCP (Model Context Protocol) is Anthropic's open protocol for connecting AI assistants to external tools and data sources. It allows Claude to interact with local systems, databases, APIs, and applications in a standardized way.

### MCP Components

| Component | Purpose | Example |
|-----------|---------|---------|
| **Tools** | Functions Claude can invoke to perform actions | `analyze_audio`, `generate_heatmap` |
| **Resources** | Read-only data endpoints | `birdnet://data/species-list` |
| **Prompts** | Pre-built multi-step workflows | `species_deep_dive`, `daily_summary` |

### Communication Protocol

- **Transport:** stdio (standard input/output)
- **Format:** JSON-RPC 2.0
- **Lifecycle:** Claude Desktop spawns the server as a subprocess
- **State:** Stateless per request, state persists via filesystem

---

## Architecture

```
SongSage/
│
├── mcp_server.py          # Main server implementation
│   ├── Configuration      # Path detection, environment loading
│   ├── Data Caching       # Smart cache with modification tracking
│   ├── Column Mapping     # Dynamic column detection (50+ aliases)
│   ├── Data Loading       # CSV parsing, format conversion
│   ├── Tools              # Audio analysis, queries, visualization
│   ├── Resources          # Read-only data access
│   └── Prompts            # Guided workflows
│
├── __init__.py            # Package initialization
├── requirements.txt       # Python dependencies
├── .env.example           # Configuration template
├── setup.sh               # Linux/macOS installer
├── docs/                  # Documentation
│   ├── installation.md    # Installation and configuration guide
│   └── documentation.md   # This file
│
├── heatmaps/              # Generated visualization output
└── test_data/             # Sample CSV files
```

### Data Flow

1. **Input:** CSV files from BirdNET-Analyzer in `results/` directory
2. **Loading:** Automatic detection of file format (wide vs long)
3. **Normalization:** Column mapping to standard names
4. **Caching:** In-memory DataFrame with modification tracking
5. **Query:** Tools filter/aggregate data based on parameters
6. **Output:** JSON responses or PNG visualizations

### Caching Strategy

Cache is invalidated whenever any CSV file in `RESULTS_DIR` is modified since the last load:

```python
_data_cache: Optional[pd.DataFrame] = None
_cache_file_mtimes: dict[str, float] = {}

def _is_cache_valid() -> bool:
    current_mtimes = _get_csv_file_mtimes()
    return current_mtimes == _cache_file_mtimes
```

### Expected BirdNET Directory Structure

```
BirdNET-Analyzer-Sierra/
├── results/              # CSV detection files (auto-scanned)
│   ├── recording1.csv
│   └── ...
├── recordings/           # Audio files for analysis
│   └── birds.wav
└── analyze.py            # BirdNET analyzer script
```

---

## Technology Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| **Python** | 3.10+ | Runtime environment |
| **FastMCP** | 1.0.0+ | MCP server framework |
| **pandas** | 2.0.0+ | Data manipulation and analysis |
| **matplotlib** | 3.7.0+ | Visualization generation |
| **numpy** | 1.24.0+ | Numerical computing |
| **python-dotenv** | 1.0.0+ | Environment configuration |

---

## Tools Reference

### Audio Analysis Tools

#### `analyze_audio`

Analyze a single audio file with BirdNET.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | required | Path to audio file |
| `min_confidence` | float | 0.1 | Minimum confidence threshold (0.0-1.0) |
| `sensitivity` | float | 1.0 | Detection sensitivity (0.5-1.5) |
| `overlap` | float | 0.0 | Segment overlap (0.0-2.9 seconds) |
| `latitude` | float | None | Location latitude for species filtering |
| `longitude` | float | None | Location longitude for species filtering |
| `week` | int | None | Week of year (1-48) for seasonal filtering |
| `locale` | string | "en" | Language locale for species names |

**Timeout:** 5 minutes. **Returns:** Detection summary with species list, counts, and confidence statistics.

---

#### `analyze_audio_batch`

Batch analyze multiple audio files.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `directory` | string | None | Directory to scan (defaults to AUDIO_DIR) |
| `pattern` | string | "*.wav" | File pattern glob |
| `output_format` | string | "csv" | Output format: csv, r, table, audacity, kaleidoscope |
| `combine_results` | bool | False | Combine all results into single file |
| `threads` | int | 4 | Number of parallel threads |

**Timeout:** 1 hour.

---

#### `analyze_audio_custom`

Analyze with customizable output columns.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | required | Path to audio file |
| `output_columns` | list | All | Columns to include in output |
| `output_name` | string | Auto | Custom output filename |

---

#### `list_audio_files`

List available audio files for analysis.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `directory` | string | AUDIO_DIR | Directory to scan |
| `pattern` | string | "*" | File pattern filter |

**Returns:** List of files with sizes, formats, and paths.

---

### Data Query Tools

#### `list_detected_species`

List all detected species with statistics.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_confidence` | float | 0.0 | Minimum confidence filter |
| `date_from` | string | None | Start date (YYYY-MM-DD) |
| `date_to` | string | None | End date (YYYY-MM-DD) |
| `sort_by` | string | "count" | Sort by: count, name, confidence |

**Returns:** Species list with detection counts, average/max confidence.

---

#### `get_detections`

Retrieve individual detection records.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `species` | string | None | Filter by species (partial match) |
| `min_confidence` | float | 0.0 | Minimum confidence |
| `date_from` | string | None | Start date |
| `date_to` | string | None | End date |
| `time_of_day` | string | None | Morning, Afternoon, Evening, Night |
| `limit` | int | 50 | Maximum results |
| `sort_by` | string | "date" | Sort by: date, confidence, species |

---

#### `get_daily_summary`

Aggregate detections by day.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date_from` | string | None | Start date |
| `date_to` | string | None | End date |
| `last_n_days` | int | None | Last N days from today |

**Returns:** Daily counts, unique species, average confidence per day.

---

#### `get_species_details`

Detailed information for a specific species.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `species_name` | string | required | Species common name |
| `include_recordings` | bool | False | Include sample recording names |

**Returns:** Detection count, confidence stats, activity by time of day.

---

#### `find_rare_detections`

Find rarely-detected species (potential rare visitors).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `min_confidence` | float | 0.5 | Minimum confidence for inclusion |
| `max_occurrences` | int | 3 | Maximum occurrence count |

---

#### `get_peak_activity_times`

Analyze when bird activity peaks.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `species` | string | None | Filter by species |
| `min_confidence` | float | 0.0 | Minimum confidence |

**Returns:** Activity breakdown by time of day and peak hours.

---

#### `get_confidence_statistics`

Detailed confidence statistics per species.

**Returns:** Mean, median, range, std deviation, percentiles (P25, P75, P90) for each species.

---

### Visualization Tools

#### `generate_heatmap`

Generate activity pattern heatmaps.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `heatmap_type` | string | required | Type of heatmap (see table below) |
| `csv_file` | string | None | Specific CSV file to use |
| `species` | string | None | Filter by species |
| `min_confidence` | float | 0.0 | Minimum confidence |
| `date_from` | string | None | Start date |
| `date_to` | string | None | End date |
| `top_n` | int | 15 | Number of species/items to show |
| `colormap` | string | "YlOrRd" | Matplotlib colormap |

**Heatmap Types:**

| Type | X-Axis | Y-Axis | Description |
|------|--------|--------|-------------|
| `species_by_time` | Time of Day | Species | Species activity by time period |
| `species_by_hour` | Hour (0-23) | Species | Hourly activity patterns |
| `species_by_weekday` | Weekday | Species | Day-of-week patterns |
| `species_by_week` | Week Number | Species | Weekly trends |
| `species_by_month` | Month | Species | Monthly patterns |
| `species_by_day` | Date | Species | Daily activity over time |
| `day_by_hour` | Hour | Date | Daily patterns by hour |
| `week_by_hour` | Hour | Week | Weekly patterns by hour |
| `month_by_hour` | Hour | Month | Monthly patterns by hour |
| `weekday_by_time` | Time of Day | Weekday | Time patterns by weekday |
| `hourly_totals` | Hour | Total | Total activity by hour |
| `daily_totals` | Date | Total | Total activity by day |
| `confidence_by_species` | Confidence | Species | Confidence distribution |
| `confidence_by_hour` | Hour | Confidence | Confidence by time |

---

#### `generate_heatmap_dynamic`

Create fully customizable heatmaps from any CSV column combination.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `csv_file` | string | required | CSV file path |
| `row_column` | string | required | Column for Y-axis |
| `col_column` | string | required | Column for X-axis |
| `value_column` | string | None | Column for values (count if None) |
| `aggregation` | string | "count" | count, sum, mean, max, min |
| `row_transform` | string | None | Transform for row values |
| `col_transform` | string | None | Transform for column values |
| `top_n_rows` | int | 20 | Limit number of rows |
| `top_n_cols` | int | 24 | Limit number of columns |
| `sort_rows_by` | string | "value" | value or name |
| `sort_cols_by` | string | "name" | value or name |

**Available Transforms:**

| Transform | Input | Output |
|-----------|-------|--------|
| `hour_from_datetime` | Datetime | Hour (0-23) |
| `date_from_datetime` | Datetime | Date string |
| `day_of_week` | Datetime | Weekday name |
| `month` | Datetime | Month name |
| `time_of_day` | Datetime/Seconds | Morning/Afternoon/Evening/Night |
| `year` | Datetime | Year number |
| `week` | Datetime | Week number |
| `hour_bin_4` | Hour | 4-hour bin |
| `hour_from_seconds` | Seconds | Hour (0-23) |
| `time_of_day_from_seconds` | Seconds | Time period |
| `bin_numeric` | Number | Binned range |

---

#### `generate_heatmap_wide`

Generate heatmaps from wide-format CSVs (species as columns).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `csv_file` | string | required | Wide-format CSV file |
| `row_column` | string | required | Column for Y-axis |
| `species_columns` | list | Auto | Specific species columns |
| `row_transform` | string | None | Transform for row values |
| `top_n_species` | int | 20 | Number of species to show |
| `aggregation` | string | "sum" | Aggregation method |

---

#### `list_colormaps`

List available color schemes (45+ options).

| Category | Examples | Best For |
|----------|----------|----------|
| Sequential | viridis, plasma, YlOrRd | Single variable intensity |
| Diverging | RdBu, coolwarm | Values around a center point |
| Qualitative | Set1, tab10 | Categorical data |

Colorblind-friendly options: viridis, cividis, plasma.

---

#### `list_heatmap_types`

List all heatmap types with descriptions and recommended use cases.

---

### Utility Tools

#### `reload_data`

Force reload all CSV data from disk, clearing the cache.

**Returns:** Summary of loaded data (total detections, unique species, date range).

---

#### `inspect_csv_structure`

Analyze CSV file structure and format.

**Returns:** Row/column counts, detected format (wide vs long), column mappings, species columns (wide format), sample datetime values.

---

#### `list_csv_columns`

Detailed column information for a specific CSV.

**Returns:** For each column: data type, non-null count, unique values, samples.

---

#### `export_csv`

Export detection data to custom CSV files.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `output_path` | string | required | Output file path |
| `columns` | list | All | Columns to include |
| `format_type` | string | "long" | long, wide, summary |
| `species` | string | None | Filter by species |
| `min_confidence` | float | 0.0 | Minimum confidence |
| `top_n` | int | None | Limit to top N species |

---

#### `get_birdnet_output_formats`

Reference guide for BirdNET output formats and their columns.

---

## Resources Reference

Resources provide read-only access to data via URI patterns.

| URI | Description | Returns |
|-----|-------------|---------|
| `birdnet://data/species-list` | All detected species | JSON with counts and confidence |
| `birdnet://data/detections-summary` | Overall statistics | Total detections, date range, top species |
| `birdnet://data/csv-files` | Available CSV files | Filenames, sizes, paths |
| `birdnet://data/audio-files` | Available audio files | Filenames, formats, sizes |
| `birdnet://csv/{filename}` | Specific CSV content | First 100 rows as JSON |

---

## Prompts Reference

Prompts are pre-built multi-step workflows that guide Claude through complex analyses.

### Analysis Workflows

| Prompt | Description |
|--------|-------------|
| `analyze_rare_birds` | Find rare species with verification recommendations |
| `daily_summary` | Comprehensive daily activity summary with trends |
| `species_deep_dive` | Complete analysis of a specific species |
| `peak_activity_report` | When birds are most active, best recording times |
| `compare_time_periods` | Compare activity between two date ranges |
| `identify_new_visitors` | Find newly-detected species |
| `quality_check` | Analyze detection quality, identify false positives |

### Audio Analysis Prompts

| Prompt | Description |
|--------|-------------|
| `analyze_my_audio` | Interactive guide for analyzing audio files |
| `quick_analysis` | Quick analysis with optimized defaults |
| `complete_bird_analysis_workflow` | End-to-end analysis pipeline |
| `setup_custom_csv_columns` | Guide for custom output columns |
| `after_analysis_options` | Post-analysis workflow options |

### Visualization Prompts

| Prompt | Description |
|--------|-------------|
| `generate_activity_heatmap` | Generate and interpret activity heatmaps |
| `select_file_for_heatmap` | Interactive file and type selection |
| `choose_heatmap_colors` | Help choosing colormaps |
| `generate_custom_heatmap` | Interactive custom heatmap generation |
| `heatmap_from_any_csv` | Step-by-step guide for any CSV |

---

## Data Handling

### Column Auto-Detection

The server automatically detects column names using 50+ aliases:

```python
COLUMN_ALIASES = {
    'datetime': ['datetime', 'timestamp', 'date_time', 'time', 'recorded_at'],
    'date': ['date', 'detection_date', 'record_date', 'day'],
    'species': ['common name', 'common_name', 'species', 'bird'],
    'confidence': ['confidence', 'conf', 'score', 'probability'],
    # ... more aliases
}
```

### Wide vs Long Format

**Long Format (BirdNET Standard):**
```csv
Start (s),End (s),Scientific name,Common name,Confidence
0.0,3.0,Turdus migratorius,American Robin,0.89
3.0,6.0,Cardinalis cardinalis,Northern Cardinal,0.76
```

**Wide Format (Species as Columns):**
```csv
datetime,American Robin,Northern Cardinal,Blue Jay
2024-01-15 06:30,5,3,2
2024-01-15 07:00,8,1,0
```

The server automatically detects and converts between formats.

### Data Normalization

1. **Date Extraction:** Parses dates from filenames (`2024-01-15_recording.csv`)
2. **Time Categorization:** Converts seconds to time of day periods (Morning/Afternoon/Evening/Night)
3. **Confidence Filtering:** Applies minimum confidence thresholds
4. **Species Matching:** Case-insensitive partial matching

---

## Visualization System

### Heatmap Generation Pipeline

1. Load and filter data based on parameters
2. Create pivot table with row/column/value
3. Order rows/columns by value or name
4. Limit to top N items
5. Generate matplotlib figure
6. Save to `heatmaps/` with timestamp
7. Return MCP Image object for Claude Desktop

### Output Specifications

| Property | Value |
|----------|-------|
| Format | PNG |
| Resolution | 150 DPI |
| Max Size | 20" x 16" |
| Colorbar | Included |
| Labels | Rotated X-axis, standard Y-axis |

### Colormap Recommendations

| Use Case | Recommended |
|----------|-------------|
| General activity | YlOrRd, viridis |
| Colorblind users | viridis, cividis |
| High contrast | plasma, inferno |
| Diverging data | RdBu, coolwarm |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Server not starting** | Verify all paths in Claude config are full absolute paths |
| **No data loaded** | Check that `BIRDNET_RESULTS_DIR` points to a directory with `.csv` files |
| **Heatmap not displaying** | Ensure `heatmaps/` directory exists and is writable |
| **"Module not found"** | Activate venv and reinstall: `pip install -r requirements.txt` |
| **Windows path issues** | Use forward slashes `/` in config JSON |

See [installation.md](installation.md) for platform-specific troubleshooting and log locations.
