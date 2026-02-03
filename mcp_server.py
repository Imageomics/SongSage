"""
SongSage - Conversational Bioacoustic Wildlife Monitoring with BirdNET and MCP.

This server connects Claude Desktop to your BirdNET-Analyzer results,
enabling natural language queries about bird detections.
"""

import os
import glob
import json
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import platform

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP, Image

# Load environment variables
load_dotenv()

# Initialize the MCP server
mcp = FastMCP(
    "songsage"
)

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
SYSTEM = platform.system()

def _get_default_birdnet_path() -> Path:
    """Detect default BirdNET installation path based on OS."""
    # Check for BirdNET-Analyzer-Sierra first, then standard BirdNET-Analyzer
    sierra_path = Path.home() / "BirdNET-Analyzer-Sierra"
    standard_path = Path.home() / "BirdNET-Analyzer"

    if sierra_path.exists():
        return sierra_path
    elif standard_path.exists():
        return standard_path
    else:
        # Default to Sierra path (user will need to install or configure)
        return sierra_path

DEFAULT_BASE = _get_default_birdnet_path()
RESULTS_DIR = Path(os.getenv('BIRDNET_RESULTS_DIR', str(DEFAULT_BASE / "results")))
AUDIO_DIR = Path(os.getenv('BIRDNET_AUDIO_DIR', str(DEFAULT_BASE / "recordings")))
BIRDNET_ANALYZER_DIR = Path(os.getenv('BIRDNET_ANALYZER_DIR', str(DEFAULT_BASE)))
HEATMAP_DIR = SCRIPT_DIR / "heatmaps"
HEATMAP_DIR.mkdir(parents=True, exist_ok=True)


def _get_birdnet_python() -> str:
    """Find the correct Python interpreter for running BirdNET-Analyzer.

    BirdNET has its own dependencies (TensorFlow, librosa, etc.) that are
    typically NOT installed in the SongSage venv. Using sys.executable
    (the SongSage venv Python) would cause ImportErrors.

    Resolution order:
      1. BIRDNET_PYTHON environment variable (explicit override)
      2. BirdNET's own venv: {BIRDNET_ANALYZER_DIR}/venv/bin/python3
      3. System Python: /usr/bin/python3 (Linux/macOS) or python (Windows)
    """
    # 1. Explicit override
    env_python = os.getenv('BIRDNET_PYTHON')
    if env_python and Path(env_python).exists():
        return env_python

    # 2. BirdNET's own venv
    if SYSTEM == "Windows":
        birdnet_venv_python = BIRDNET_ANALYZER_DIR / "venv" / "Scripts" / "python.exe"
    else:
        birdnet_venv_python = BIRDNET_ANALYZER_DIR / "venv" / "bin" / "python3"
    if birdnet_venv_python.exists():
        return str(birdnet_venv_python)

    # 3. System Python (where BirdNET deps are typically installed)
    import shutil
    system_python = shutil.which("python3") or shutil.which("python")
    if system_python:
        return system_python

    # Last resort: current interpreter (may lack BirdNET deps)
    return sys.executable


BIRDNET_PYTHON = _get_birdnet_python()

# Only access CSV files from the results directory
SUPPORTED_FILE_PATTERN = "*.csv"

# =============================================================================
# Data Caching
# =============================================================================

_data_cache: Optional[pd.DataFrame] = None
_cache_file_mtimes: dict[str, float] = {}


def _get_csv_file_mtimes() -> dict[str, float]:
    """Get modification times for all CSV files in results directory."""
    csv_files = list(RESULTS_DIR.glob(SUPPORTED_FILE_PATTERN))
    csv_files = [f for f in csv_files if not f.name.startswith('combined')]
    return {str(f): f.stat().st_mtime for f in csv_files}


def _is_cache_valid() -> bool:
    """Check if the data cache is still valid."""
    global _data_cache, _cache_file_mtimes
    
    if _data_cache is None:
        return False
    
    current_mtimes = _get_csv_file_mtimes()
    if set(current_mtimes.keys()) != set(_cache_file_mtimes.keys()):
        return False
    
    for filepath, mtime in current_mtimes.items():
        if _cache_file_mtimes.get(filepath) != mtime:
            return False
    
    return True


# =============================================================================
# Dynamic Column Mapping Configuration
# =============================================================================

# Default column aliases for auto-detection
COLUMN_ALIASES = {
    'datetime': ['datetime', 'timestamp', 'date_time', 'time', 'recorded_at', 'detection_time'],
    'date': ['date', 'detection_date', 'record_date', 'day'],
    'hour': ['hour', 'hr', 'time_hour'],
    'species': ['common name', 'common_name', 'species', 'bird', 'species_name', 'bird_name'],
    'scientific_name': ['scientific name', 'scientific_name', 'sci_name', 'latin_name'],
    'confidence': ['confidence', 'conf', 'score', 'probability', 'prob'],
    'location': ['location', 'site', 'station', 'loc', 'place', 'recorder'],
    'file_id': ['file_id', 'file', 'filename', 'recording', 'audio_file'],
    'start_time': ['start (s)', 'start_seconds', 'start', 'begin', 'begin time (s)'],
    'end_time': ['end (s)', 'end_seconds', 'end', 'stop'],
    'count': ['count', 'detections', 'num_detections', 'n'],
    'latitude': ['lat', 'latitude', 'y'],
    'longitude': ['lon', 'longitude', 'lng', 'x'],
}


def _detect_column_mapping(df: pd.DataFrame) -> dict:
    """Auto-detect column mappings based on column names and aliases."""
    mapping = {}
    df_cols_lower = {col.lower().strip(): col for col in df.columns}

    for semantic_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df_cols_lower:
                mapping[semantic_name] = df_cols_lower[alias]
                break

    return mapping


def _detect_species_columns(df: pd.DataFrame, mapping: dict) -> list:
    """Detect which columns are likely species count columns (for wide format)."""
    exclude_cols = set()
    for col in mapping.values():
        exclude_cols.add(col.lower())
    exclude_cols.update(['total_birds', 'total', 'sum', 'count', 'index', 'row_num', 'unnamed', 'id'])

    species_cols = []
    for col in df.columns:
        col_lower = col.lower().strip()
        if col_lower in exclude_cols or col.strip().isdigit():
            continue
        if df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
            # Check if values look like counts (non-negative integers mostly)
            if df[col].min() >= 0 and (df[col] == df[col].astype(int)).all():
                species_cols.append(col)

    return species_cols


# =============================================================================
# Data Loading & Processing
# =============================================================================

def _parse_date_from_recording(recording_name: str) -> Optional[datetime]:
    """Extract date from recording name (expects format like 2024-01-15_recording)."""
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})', recording_name)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d')
        except ValueError:
            return None
    return None


def _parse_time_of_day(seconds: float) -> str:
    """Convert seconds since midnight to time of day category."""
    hour = (seconds % 86400) / 3600
    if hour < 6:
        return "Night"
    elif hour < 12:
        return "Morning"
    elif hour < 18:
        return "Afternoon"
    else:
        return "Evening"


def _is_wide_format(df: pd.DataFrame) -> bool:
    """Detect if a CSV is in wide format (species as columns)."""
    cols_lower = [c.lower() for c in df.columns]
    has_datetime = any(c in cols_lower for c in ['datetime', 'date', 'timestamp'])
    has_location = any(c in cols_lower for c in ['location', 'file_id', 'site', 'station'])
    has_birdnet_cols = 'Common name' in df.columns or 'common name' in cols_lower
    numeric_cols = df.select_dtypes(include=['number']).columns
    many_numeric = len(numeric_cols) > 5
    
    return (has_datetime or has_location) and not has_birdnet_cols and many_numeric


def _convert_wide_to_long(df: pd.DataFrame, source_file: str) -> pd.DataFrame:
    """Convert wide format (species as columns) to long format.

    Handles various datetime column formats and extracts Date and Start_Seconds.
    """
    try:
        metadata_cols = []
        species_cols = []
        datetime_col = None
        exclude_cols = ['total_birds', 'total', 'sum', 'count', 'index', 'row_num', 'unnamed', '1', '0', 'id']

        for col in df.columns:
            col_lower = col.lower().strip()
            if col_lower in exclude_cols or col.strip().isdigit():
                continue
            # Identify datetime column for special handling
            if col_lower in ['datetime', 'timestamp', 'date_time', 'time']:
                datetime_col = col
                metadata_cols.append(col)
            elif col_lower in ['date', 'location', 'file_id',
                           'site', 'station', 'lat', 'lon', 'latitude', 'longitude',
                           'hour', 'time_of_day', 'period']:
                metadata_cols.append(col)
            elif df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
                species_cols.append(col)

        if not species_cols:
            return pd.DataFrame()

        long_df = df.melt(
            id_vars=metadata_cols,
            value_vars=species_cols,
            var_name='Common name',
            value_name='Count'
        )

        long_df['Count'] = pd.to_numeric(long_df['Count'], errors='coerce').fillna(0)
        long_df = long_df[long_df['Count'] > 0].copy()

        if long_df.empty:
            return pd.DataFrame()

        # Clean species names (replace underscores with spaces)
        long_df['Common name'] = long_df['Common name'].str.replace('_', ' ')
        long_df['Confidence'] = 1.0
        long_df['Recording_Name'] = source_file

        # Parse datetime column to extract Date and Start_Seconds
        if datetime_col and datetime_col in long_df.columns:
            try:
                parsed_dt = pd.to_datetime(long_df[datetime_col], errors='coerce')
                long_df['Date'] = parsed_dt.dt.date
                long_df['Date'] = pd.to_datetime(long_df['Date'])
                # Calculate Start_Seconds from hour (seconds since midnight)
                long_df['Start_Seconds'] = (
                    parsed_dt.dt.hour * 3600 +
                    parsed_dt.dt.minute * 60 +
                    parsed_dt.dt.second
                )
                long_df['Hour'] = parsed_dt.dt.hour
            except Exception:
                pass

        # Check for separate date and hour columns
        for col in long_df.columns:
            col_lower = col.lower()
            if col_lower == 'date' and 'Date' not in long_df.columns:
                try:
                    long_df['Date'] = pd.to_datetime(long_df[col], errors='coerce')
                except Exception:
                    pass
            elif col_lower == 'hour' and 'Start_Seconds' not in long_df.columns:
                try:
                    long_df['Start_Seconds'] = pd.to_numeric(long_df[col], errors='coerce') * 3600
                except Exception:
                    pass

        return long_df

    except Exception:
        return pd.DataFrame()


def load_bird_data(force_reload: bool = False) -> pd.DataFrame:
    """Load and combine all bird detection CSV files with caching."""
    global _data_cache, _cache_file_mtimes
    
    if not force_reload and _is_cache_valid():
        return _data_cache.copy()
    
    csv_files = list(RESULTS_DIR.glob(SUPPORTED_FILE_PATTERN))
    csv_files = [f for f in csv_files if not f.name.startswith('combined')]
    
    if not csv_files:
        _data_cache = pd.DataFrame()
        _cache_file_mtimes = {}
        return _data_cache
    
    combined_data = []
    
    for csv_file in csv_files:
        try:
            recording_name = csv_file.stem
            df = pd.read_csv(csv_file)

            if df.empty:
                continue

            # Normalize column names before processing
            column_mapping = {
                'common_name': 'Common name',
                'scientific_name': 'Scientific name',
                'start': 'Start (s)',
                'end': 'End (s)',
                'confidence': 'Confidence',
                'filepath': 'File',
                'Start': 'Start (s)',
                'End': 'End (s)'
            }
            df = df.rename(columns=column_mapping)

            if _is_wide_format(df):
                df = _convert_wide_to_long(df, recording_name)
            else:
                df['Recording_Name'] = recording_name

            if not df.empty:
                combined_data.append(df)

        except Exception:
            continue
    
    if not combined_data:
        _data_cache = pd.DataFrame()
        _cache_file_mtimes = {}
        return _data_cache
    
    final_df = pd.concat(combined_data, ignore_index=True)

    # Consolidate duplicate columns (in case some weren't caught by rename)
    # Merge Start (s) and start into Start_Seconds
    for start_col in ['Start (s)', 'start', 'Start']:
        if start_col in final_df.columns:
            if 'Start_Seconds' not in final_df.columns:
                final_df['Start_Seconds'] = pd.to_numeric(final_df[start_col], errors='coerce')
            else:
                final_df['Start_Seconds'] = final_df['Start_Seconds'].fillna(
                    pd.to_numeric(final_df[start_col], errors='coerce')
                )

    # Merge Common name and common_name
    for name_col in ['Common name', 'common_name']:
        if name_col in final_df.columns:
            if name_col != 'Common name':
                if 'Common name' not in final_df.columns:
                    final_df['Common name'] = final_df[name_col]
                else:
                    final_df['Common name'] = final_df['Common name'].fillna(final_df[name_col])

    # Merge Confidence and confidence
    for conf_col in ['Confidence', 'confidence']:
        if conf_col in final_df.columns:
            if conf_col != 'Confidence':
                if 'Confidence' not in final_df.columns:
                    final_df['Confidence'] = final_df[conf_col]
                else:
                    final_df['Confidence'] = final_df['Confidence'].fillna(final_df[conf_col])

    # Parse dates - only for rows that don't already have a Date
    if 'Date' not in final_df.columns:
        final_df['Date'] = final_df['Recording_Name'].apply(_parse_date_from_recording)
    else:
        # Ensure Date column is datetime type
        final_df['Date'] = pd.to_datetime(final_df['Date'], errors='coerce')
        # Fill missing Date values from Recording_Name where possible
        missing_dates = final_df['Date'].isna()
        if missing_dates.any():
            parsed_dates = final_df.loc[missing_dates, 'Recording_Name'].apply(_parse_date_from_recording)
            final_df.loc[missing_dates, 'Date'] = pd.to_datetime(parsed_dates, errors='coerce')

    # Ensure Start_Seconds exists (if not created above)
    if 'Start_Seconds' not in final_df.columns:
        final_df['Start_Seconds'] = 0
    else:
        # Fill any remaining NaN values with 0
        final_df['Start_Seconds'] = final_df['Start_Seconds'].fillna(0)

    # Calculate time of day - only for rows that don't have it
    if 'TimeOfDay' not in final_df.columns:
        final_df['TimeOfDay'] = final_df['Start_Seconds'].apply(_parse_time_of_day)
    else:
        # Fill missing TimeOfDay values
        missing_tod = final_df['TimeOfDay'].isna()
        if missing_tod.any():
            final_df.loc[missing_tod, 'TimeOfDay'] = final_df.loc[missing_tod, 'Start_Seconds'].apply(_parse_time_of_day)

    # Ensure confidence is numeric
    if 'Confidence' in final_df.columns:
        final_df['Confidence'] = pd.to_numeric(final_df['Confidence'], errors='coerce').fillna(0)
    else:
        final_df['Confidence'] = 1.0
    
    _data_cache = final_df
    _cache_file_mtimes = _get_csv_file_mtimes()
    
    return _data_cache.copy()


def apply_filters(
    df: pd.DataFrame,
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    time_of_day: Optional[str] = None
) -> pd.DataFrame:
    """Apply common filters to the dataframe."""
    if df.empty:
        return df
    
    filtered = df.copy()
    
    if species:
        species_lower = species.lower()
        mask = filtered['Common name'].str.lower().str.contains(species_lower, na=False)
        if 'Scientific name' in filtered.columns:
            mask |= filtered['Scientific name'].str.lower().str.contains(species_lower, na=False)
        filtered = filtered[mask]
    
    if min_confidence is not None and 'Confidence' in filtered.columns:
        filtered = filtered[filtered['Confidence'] >= min_confidence]
    
    if date_from and 'Date' in filtered.columns:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            filtered = filtered[filtered['Date'] >= from_date]
        except ValueError:
            pass
    
    if date_to and 'Date' in filtered.columns:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d')
            filtered = filtered[filtered['Date'] <= to_date]
        except ValueError:
            pass
    
    if time_of_day and 'TimeOfDay' in filtered.columns:
        filtered = filtered[filtered['TimeOfDay'].str.lower() == time_of_day.lower()]
    
    return filtered


# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool()
def list_detected_species(
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = "count"
) -> str:
    """
    List all detected bird species with detection counts and confidence statistics.
    
    Args:
        min_confidence: Minimum confidence threshold (0.0-1.0)
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
        sort_by: Sort by 'count', 'name', or 'confidence'
    
    Returns:
        Formatted list of species with counts and confidence stats
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    df = apply_filters(df, min_confidence=min_confidence, date_from=date_from, date_to=date_to)
    
    if df.empty:
        return "No detections match the specified filters."
    
    stats = df.groupby('Common name').agg({
        'Confidence': ['count', 'mean', 'max']
    }).round(3)
    stats.columns = ['Count', 'Avg_Confidence', 'Max_Confidence']
    stats = stats.reset_index()
    
    if sort_by == "name":
        stats = stats.sort_values('Common name')
    elif sort_by == "confidence":
        stats = stats.sort_values('Avg_Confidence', ascending=False)
    else:
        stats = stats.sort_values('Count', ascending=False)
    
    lines = [f"Detected Species ({len(stats)} total, {len(df)} detections):", "=" * 60]
    
    for _, row in stats.iterrows():
        lines.append(
            f"  {row['Common name']}: {int(row['Count'])} detections "
            f"(avg conf: {row['Avg_Confidence']:.2f}, max: {row['Max_Confidence']:.2f})"
        )
    
    return "\n".join(lines)


@mcp.tool()
def get_detections(
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    time_of_day: Optional[str] = None,
    limit: int = 50,
    sort_by: str = "date"
) -> str:
    """
    Get raw detection data with flexible filtering.
    
    Args:
        species: Filter by species name (partial match, case-insensitive)
        min_confidence: Minimum confidence threshold (0.0-1.0)
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
        time_of_day: Filter by Morning, Afternoon, Evening, or Night
        limit: Maximum results to return (default: 50)
        sort_by: Sort by 'date', 'confidence', or 'species'
    
    Returns:
        Formatted list of individual detections
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to, time_of_day=time_of_day)
    
    if df.empty:
        return "No detections match the specified filters."
    
    if sort_by == "confidence":
        df = df.sort_values('Confidence', ascending=False)
    elif sort_by == "species":
        df = df.sort_values('Common name')
    else:
        df = df.sort_values('Date', ascending=False, na_position='last')
    
    total_count = len(df)
    df = df.head(limit)
    
    lines = [f"Detections ({len(df)} of {total_count} total):", "=" * 70]
    
    for _, row in df.iterrows():
        date_str = row['Date'].strftime('%Y-%m-%d') if pd.notna(row.get('Date')) else 'Unknown'
        lines.append(
            f"  [{date_str} {row.get('TimeOfDay', '?')}] {row['Common name']} "
            f"- Confidence: {row['Confidence']:.3f}"
        )
    
    if total_count > limit:
        lines.append(f"\n... and {total_count - limit} more detections")
    
    return "\n".join(lines)


@mcp.tool()
def get_daily_summary(
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    last_n_days: Optional[int] = None
) -> str:
    """
    Get detection summary aggregated by day.
    
    Args:
        species: Filter by species name
        min_confidence: Minimum confidence threshold (0.0-1.0)
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
        last_n_days: Only include the last N days
    
    Returns:
        Daily statistics with totals and averages
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    if last_n_days and 'Date' in df.columns:
        cutoff = datetime.now() - timedelta(days=last_n_days)
        df = df[df['Date'] >= cutoff]
    
    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to)
    
    if df.empty:
        return "No detections match the specified filters."
    
    df_with_dates = df[df['Date'].notna()].copy()
    if df_with_dates.empty:
        return "No detections have valid date information."
    
    df_with_dates['DateStr'] = df_with_dates['Date'].dt.strftime('%Y-%m-%d')
    
    daily = df_with_dates.groupby('DateStr').agg({
        'Common name': ['count', 'nunique'],
        'Confidence': 'mean'
    }).round(3)
    daily.columns = ['Total_Detections', 'Unique_Species', 'Avg_Confidence']
    daily = daily.reset_index().sort_values('DateStr', ascending=False)
    
    lines = [f"Daily Summary ({len(daily)} days):", "=" * 60]
    
    for _, row in daily.iterrows():
        lines.append(
            f"  {row['DateStr']}: {int(row['Total_Detections'])} detections, "
            f"{int(row['Unique_Species'])} species (avg conf: {row['Avg_Confidence']:.2f})"
        )
    
    lines.extend([
        "",
        "Overall Statistics:",
        f"  Total Days: {len(daily)}",
        f"  Total Detections: {int(daily['Total_Detections'].sum())}",
        f"  Avg Detections/Day: {daily['Total_Detections'].mean():.1f}"
    ])
    
    return "\n".join(lines)


@mcp.tool()
def get_species_details(species: str, include_recordings: bool = True) -> str:
    """
    Get detailed information about a specific bird species.
    
    Args:
        species: Species name to look up (required)
        include_recordings: Whether to list recordings (default: True)
    
    Returns:
        Detailed species statistics including time patterns and confidence distribution
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    if not species:
        return "Please specify a species name."
    
    df = apply_filters(df, species=species)
    
    if df.empty:
        return f"No detections found for species matching '{species}'."
    
    species_name = df['Common name'].mode().iloc[0] if not df.empty else species
    
    lines = [
        f"Species Details: {species_name}",
        "=" * 60,
        f"Total Detections: {len(df)}",
        f"Confidence Range: {df['Confidence'].min():.3f} - {df['Confidence'].max():.3f}",
        f"Average Confidence: {df['Confidence'].mean():.3f}",
        "",
        "Activity by Time of Day:"
    ]
    
    time_counts = df['TimeOfDay'].value_counts()
    for tod in ['Morning', 'Afternoon', 'Evening', 'Night']:
        count = time_counts.get(tod, 0)
        lines.append(f"  {tod}: {count} detections")
    
    if include_recordings:
        recordings = df['Recording_Name'].unique()[:10]
        lines.extend(["", f"Sample Recordings ({min(len(recordings), 10)} of {df['Recording_Name'].nunique()}):"])
        for rec in recordings:
            lines.append(f"  - {rec}")
    
    return "\n".join(lines)


@mcp.tool()
def find_rare_detections(
    min_confidence: float = 0.5,
    max_occurrence_count: int = 3,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Find rarely detected species (potential rare visitors).
    
    Args:
        min_confidence: Minimum confidence to consider (default: 0.5)
        max_occurrence_count: Max detections to be considered rare (default: 3)
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
    
    Returns:
        List of rare species with detection details
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    df = apply_filters(df, min_confidence=min_confidence, date_from=date_from, date_to=date_to)
    
    if df.empty:
        return "No detections match the specified filters."
    
    species_counts = df.groupby('Common name').agg({
        'Confidence': ['count', 'max']
    })
    species_counts.columns = ['count', 'max_confidence']
    species_counts = species_counts.reset_index()
    
    rare = species_counts[species_counts['count'] <= max_occurrence_count]
    rare = rare.sort_values('count')
    
    if rare.empty:
        return f"No species with {max_occurrence_count} or fewer detections found."
    
    lines = [f"Rare Detections ({len(rare)} species with ≤{max_occurrence_count} occurrences):", "=" * 60]
    
    for _, row in rare.iterrows():
        lines.append(
            f"  {row['Common name']}: {int(row['count'])} detection(s) "
            f"(max confidence: {row['max_confidence']:.3f})"
        )
    
    return "\n".join(lines)


@mcp.tool()
def get_peak_activity_times(
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Analyze when bird activity peaks during the day.
    
    Args:
        species: Filter by specific species
        min_confidence: Minimum confidence threshold
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
    
    Returns:
        Activity breakdown by time period and peak hours
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to)
    
    if df.empty:
        return "No detections match the specified filters."
    
    lines = ["Peak Activity Analysis:", "=" * 60]
    
    # By time of day
    time_counts = df['TimeOfDay'].value_counts()
    lines.append("\nBy Time of Day:")
    for tod in ['Morning', 'Afternoon', 'Evening', 'Night']:
        count = time_counts.get(tod, 0)
        pct = (count / len(df)) * 100
        bar = "█" * int(pct / 5)
        lines.append(f"  {tod:12} {bar:20} {count:5} ({pct:.1f}%)")
    
    # By hour
    df['Hour'] = ((df['Start_Seconds'] / 3600) % 24).astype(int)
    hour_counts = df['Hour'].value_counts().sort_index()
    
    peak_hour = hour_counts.idxmax()
    lines.extend([
        "",
        f"Peak Hour: {peak_hour:02d}:00 - {peak_hour:02d}:59 ({hour_counts[peak_hour]} detections)"
    ])
    
    return "\n".join(lines)


@mcp.tool()
def get_confidence_statistics(
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
) -> str:
    """
    Get detailed confidence statistics for detected species.
    
    Args:
        species: Filter by species name
        min_confidence: Minimum confidence threshold
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
    
    Returns:
        Statistics including mean, median, range, std dev, and percentiles
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."

    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to)

    if df.empty:
        return "No detections match the specified filters."

    lines = ["Confidence Statistics by Species:", "=" * 60]

    grouped = df.groupby("Common name")["Confidence"]

    for species_name, confidences in grouped:
        mean_conf = confidences.mean()
        median_conf = confidences.median()
        max_conf = confidences.max()
        min_conf = confidences.min()
        std_conf = confidences.std()
        count = len(confidences)

        lines.append(f"\n{species_name} (n={count}):")
        lines.append(f"  Mean: {mean_conf:.3f}, Median: {median_conf:.3f}")
        lines.append(f"  Range: {min_conf:.3f} - {max_conf:.3f}, Std: {std_conf:.3f}")

        # Percentiles
        p25 = confidences.quantile(0.25)
        p75 = confidences.quantile(0.75)
        p90 = confidences.quantile(0.90)
        lines.append(f"  Percentiles: P25={p25:.3f}, P75={p75:.3f}, P90={p90:.3f}")

    return "\n".join(lines)


@mcp.tool()
def inspect_csv_structure(csv_filename: Optional[str] = None) -> str:
    """
    Inspect the structure of CSV files to understand their format.
    Shows detected column mappings and suggests what data can be extracted.

    Args:
        csv_filename: Specific CSV file to inspect (optional, inspects all if not provided)

    Returns:
        Detailed information about CSV file structure, detected mappings, and species columns
    """
    if csv_filename:
        csv_path = RESULTS_DIR / csv_filename
        if not csv_path.exists():
            return f"CSV file not found: {csv_filename}"
        csv_files = [csv_path]
    else:
        csv_files = list(RESULTS_DIR.glob(SUPPORTED_FILE_PATTERN))
        csv_files = [f for f in csv_files if not f.name.startswith('combined')]

    if not csv_files:
        return "No CSV files found."

    lines = ["CSV File Structure Analysis:", "=" * 70]

    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)

            lines.append(f"\nFile: {csv_file.name}")
            lines.append(f"Rows: {len(df)}, Columns: {len(df.columns)}")

            # Detect format
            is_wide = _is_wide_format(df)
            lines.append(f"Format: {'Wide (species as columns)' if is_wide else 'Long (BirdNET standard)'}")

            # Auto-detect column mappings
            mapping = _detect_column_mapping(df)
            lines.append("\nDetected Column Mappings:")
            if mapping:
                for semantic, actual in mapping.items():
                    lines.append(f"  {semantic}: '{actual}'")
            else:
                lines.append("  (no standard columns detected)")

            # For wide format, show detected species columns
            if is_wide:
                species_cols = _detect_species_columns(df, mapping)
                lines.append(f"\nSpecies Columns Detected: {len(species_cols)}")
                if species_cols:
                    sample_species = species_cols[:10]
                    lines.append(f"  Sample: {', '.join(sample_species)}")
                    if len(species_cols) > 10:
                        lines.append(f"  ... and {len(species_cols) - 10} more")

            # Show datetime info if detected
            if 'datetime' in mapping:
                dt_col = mapping['datetime']
                sample_values = df[dt_col].head(3).tolist()
                lines.append(f"\nDatetime Sample: {sample_values}")

            # Show all columns
            lines.append(f"\nAll Columns: {', '.join(df.columns.tolist()[:15])}")
            if len(df.columns) > 15:
                lines.append(f"  ... and {len(df.columns) - 15} more")

            # Show data types
            lines.append("\nColumn Types:")
            for col in df.columns[:8]:
                lines.append(f"  {col}: {df[col].dtype}")
            if len(df.columns) > 8:
                lines.append(f"  ... and {len(df.columns) - 8} more")

            lines.append("-" * 70)

        except Exception as e:
            lines.append(f"\nFile: {csv_file.name}")
            lines.append(f"Error: {str(e)}")
            lines.append("-" * 70)

    return "\n".join(lines)


@mcp.tool()
def reload_data() -> str:
    """
    Force reload all CSV data from disk, clearing the cache.
    Use this when CSV files have been updated or new files added.

    Returns:
        Summary of reloaded data
    """
    df = load_bird_data(force_reload=True)

    if df.empty:
        return "No data loaded. Please check your CSV files."

    species_count = df['Common name'].nunique()

    lines = [
        "Data Reloaded Successfully!",
        "=" * 60,
        f"Total Detections: {len(df):,}",
        f"Unique Species: {species_count}",
        f"Date Range: {df['Date'].min()} to {df['Date'].max()}",
        "",
        "Top 10 Species:"
    ]

    top_species = df['Common name'].value_counts().head(10)
    for species, count in top_species.items():
        lines.append(f"  - {species}: {count} detections")

    return "\n".join(lines)


@mcp.tool()
def analyze_audio(
    audio_file: str,
    min_confidence: float = 0.25,
    sensitivity: float = 1.0,
    overlap: float = 0.0,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    week: Optional[int] = None,
    locale: str = "en"
) -> str:
    """
    Run BirdNET-Analyzer on an audio file.
    
    Args:
        audio_file: Name or path of audio file to analyze
        min_confidence: Minimum confidence threshold (default: 0.25)
        sensitivity: Detection sensitivity 0.5-1.5 (default: 1.0)
        overlap: Overlap of analysis segments 0.0-2.9 (default: 0.0)
        lat: Latitude for location-based filtering
        lon: Longitude for location-based filtering
        week: Week of year 1-48 for seasonal filtering
        locale: Language code for species names (default: 'en')
    
    Returns:
        Analysis summary with detected species
    """
    import subprocess
    import sys
    
    # Resolve audio file path
    audio_path = Path(audio_file)
    
    if not audio_path.is_absolute():
        audio_path = AUDIO_DIR / audio_file
    
    if not audio_path.exists():
        # Try with common extensions
        for ext in ['.wav', '.mp3', '.flac', '.ogg']:
            test_path = AUDIO_DIR / f"{audio_file}{ext}"
            if test_path.exists():
                audio_path = test_path
                break
    
    if not audio_path.exists():
        return f"Audio file not found: {audio_file}\nSearched in: {AUDIO_DIR}"
    
    # Find BirdNET analyze script
    analyze_script = BIRDNET_ANALYZER_DIR / "analyze.py"
    if not analyze_script.exists():
        return f"BirdNET-Analyzer not found at: {BIRDNET_ANALYZER_DIR}"
    
    # Build command
    cmd = [
        BIRDNET_PYTHON,
        str(analyze_script),
        "--i", str(audio_path),
        "--o", str(RESULTS_DIR),
        "--rtype", "csv",
        "--min_conf", str(min_confidence),
        "--sensitivity", str(sensitivity),
        "--overlap", str(overlap),
        "--locale", locale,
    ]
    
    if lat is not None and lon is not None:
        cmd.extend(["--lat", str(lat), "--lon", str(lon)])
    
    if week is not None and 1 <= week <= 48:
        cmd.extend(["--week", str(week)])
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(BIRDNET_ANALYZER_DIR),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            return f"Analysis failed: {result.stderr[:500]}"
        
        # Find output CSV
        audio_stem = audio_path.stem
        csv_path = None
        
        for pattern in [f"{audio_stem}.BirdNET.results.csv", f"{audio_stem}.csv"]:
            test_path = RESULTS_DIR / pattern
            if test_path.exists():
                csv_path = test_path
                break
        
        if not csv_path:
            csv_files = list(RESULTS_DIR.glob(f"{audio_stem}*.csv"))
            if csv_files:
                csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)
        
        if not csv_path or not csv_path.exists():
            return f"Analysis completed but CSV output not found."
        
        # Invalidate cache
        global _data_cache
        _data_cache = None
        
        # Read and summarize
        result_df = pd.read_csv(csv_path)
        if result_df.empty:
            return f"Analysis completed for {audio_path.name}.\nNo bird detections found."
        
        lines = [
            f"Analysis completed: {audio_path.name}",
            f"Results saved to: {csv_path.name}",
            "=" * 60,
            f"Detections: {len(result_df)}"
        ]
        
        if 'Common name' in result_df.columns:
            species_summary = result_df.groupby('Common name')['Confidence'].agg(['count', 'max']).round(3)
            species_summary.columns = ['Count', 'Max_Conf']
            species_summary = species_summary.sort_values('Max_Conf', ascending=False)
            
            lines.append(f"Unique species: {len(species_summary)}")
            lines.append("\nSpecies detected:")
            
            for species_name, row in species_summary.iterrows():
                lines.append(f"  - {species_name}: {int(row['Count'])}x (max conf: {row['Max_Conf']:.2f})")
        
        return "\n".join(lines)
        
    except subprocess.TimeoutExpired:
        return "Analysis timed out after 5 minutes."
    except Exception as e:
        return f"Error analyzing audio: {str(e)}"


@mcp.tool()
def list_audio_files(directory: Optional[str] = None) -> str:
    """
    List available audio files that can be analyzed with BirdNET.

    Args:
        directory: Optional directory path to search (defaults to AUDIO_DIR)

    Returns:
        List of audio files with their details (size, duration estimate)
    """
    search_dir = Path(directory) if directory else AUDIO_DIR

    if not search_dir.exists():
        return f"Directory not found: {search_dir}\nDefault audio directory: {AUDIO_DIR}"

    # Common audio extensions
    audio_extensions = ['.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma']

    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(search_dir.glob(f"*{ext}"))
        audio_files.extend(search_dir.glob(f"**/*{ext}"))  # Recursive

    if not audio_files:
        return f"No audio files found in: {search_dir}\nSupported formats: {', '.join(audio_extensions)}"

    # Remove duplicates and sort
    audio_files = sorted(set(audio_files), key=lambda p: p.name)

    lines = [
        f"Audio Files in: {search_dir}",
        f"Total files: {len(audio_files)}",
        "=" * 60,
        ""
    ]

    for audio_file in audio_files[:50]:  # Limit to 50 files
        size_mb = audio_file.stat().st_size / (1024 * 1024)
        rel_path = audio_file.relative_to(search_dir) if search_dir in audio_file.parents or search_dir == audio_file.parent else audio_file.name

        lines.append(f"  {rel_path}")
        lines.append(f"    Size: {size_mb:.2f} MB, Format: {audio_file.suffix}")

    if len(audio_files) > 50:
        lines.append(f"\n  ... and {len(audio_files) - 50} more files")

    lines.append("")
    lines.append("-" * 60)
    lines.append("To analyze a file, use: analyze_audio('filename.wav')")
    lines.append("To analyze all files, use: analyze_audio_batch()")

    return "\n".join(lines)


@mcp.tool()
def analyze_audio_batch(
    directory: Optional[str] = None,
    file_pattern: str = "*.wav",
    output_format: str = "csv",
    min_confidence: float = 0.25,
    sensitivity: float = 1.0,
    combine_results: bool = True,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    week: Optional[int] = None,
    locale: str = "en",
    threads: int = 4
) -> str:
    """
    Analyze multiple audio files with BirdNET-Analyzer.

    Args:
        directory: Directory containing audio files (defaults to AUDIO_DIR)
        file_pattern: Glob pattern for audio files (default: '*.wav')
        output_format: Output format - 'csv', 'r', 'table', 'audacity', 'kaleidoscope'
        min_confidence: Minimum confidence threshold (default: 0.25)
        sensitivity: Detection sensitivity 0.5-1.5 (default: 1.0)
        combine_results: Combine all results into one file (default: True)
        lat: Latitude for location-based species filtering
        lon: Longitude for location-based species filtering
        week: Week of year 1-48 for seasonal filtering
        locale: Language for species names (default: 'en')
        threads: Number of CPU threads (default: 4)

    Returns:
        Summary of batch analysis results
    """
    import subprocess
    import sys

    input_dir = Path(directory) if directory else AUDIO_DIR

    if not input_dir.exists():
        return f"Input directory not found: {input_dir}"

    # Count matching files
    audio_files = list(input_dir.glob(file_pattern))
    if not audio_files:
        return f"No files matching '{file_pattern}' found in {input_dir}"

    # Find BirdNET analyze script
    analyze_script = BIRDNET_ANALYZER_DIR / "analyze.py"
    if not analyze_script.exists():
        return f"BirdNET-Analyzer not found at: {BIRDNET_ANALYZER_DIR}"

    # Build command for directory analysis
    cmd = [
        BIRDNET_PYTHON,
        str(analyze_script),
        "--i", str(input_dir),
        "--o", str(RESULTS_DIR),
        "--rtype", output_format,
        "--min_conf", str(min_confidence),
        "--sensitivity", str(sensitivity),
        "--threads", str(threads),
        "--locale", locale,
    ]

    if combine_results:
        cmd.append("--combine_results")

    if lat is not None and lon is not None:
        cmd.extend(["--lat", str(lat), "--lon", str(lon)])

    if week is not None and 1 <= week <= 48:
        cmd.extend(["--week", str(week)])

    try:
        lines = [
            f"Starting batch analysis...",
            f"Input: {input_dir}",
            f"Files matching '{file_pattern}': {len(audio_files)}",
            f"Output format: {output_format}",
            f"Combine results: {combine_results}",
            "=" * 60,
            ""
        ]

        result = subprocess.run(
            cmd,
            cwd=str(BIRDNET_ANALYZER_DIR),
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout for batch
        )

        if result.returncode != 0:
            return f"Batch analysis failed:\n{result.stderr[:1000]}"

        # Invalidate cache
        global _data_cache
        _data_cache = None

        # Find output files
        new_csvs = list(RESULTS_DIR.glob("*.csv"))
        recent_csvs = [f for f in new_csvs if f.stat().st_mtime > (pd.Timestamp.now() - pd.Timedelta(minutes=5)).timestamp()]

        lines.append("Analysis completed!")
        lines.append(f"New/updated result files: {len(recent_csvs)}")

        if recent_csvs:
            lines.append("\nGenerated files:")
            for csv_file in recent_csvs[:10]:
                lines.append(f"  - {csv_file.name}")

        # Load and summarize combined results if available
        if combine_results:
            combined_files = list(RESULTS_DIR.glob("combined*.csv")) + list(RESULTS_DIR.glob("*combined*.csv"))
            if combined_files:
                latest_combined = max(combined_files, key=lambda p: p.stat().st_mtime)
                try:
                    df = pd.read_csv(latest_combined)
                    lines.append(f"\nCombined results summary ({latest_combined.name}):")
                    lines.append(f"  Total detections: {len(df)}")
                    if 'Common name' in df.columns:
                        lines.append(f"  Unique species: {df['Common name'].nunique()}")
                except:
                    pass

        lines.append("")
        lines.append("Use list_detected_species() or generate_heatmap() to explore results.")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "Batch analysis timed out after 1 hour."
    except Exception as e:
        return f"Error in batch analysis: {str(e)}"


@mcp.tool()
def analyze_audio_custom(
    audio_file: str,
    output_format: str = "csv",
    output_columns: Optional[list[str]] = None,
    min_confidence: float = 0.25,
    sensitivity: float = 1.0,
    overlap: float = 0.0,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    week: Optional[int] = None,
    locale: str = "en",
    custom_output_name: Optional[str] = None
) -> str:
    """
    Analyze audio with customizable output format and columns.

    Args:
        audio_file: Audio file path or name
        output_format: Format - 'csv' (standard), 'r' (R-friendly with more columns),
                       'table' (Raven selection table), 'audacity', 'kaleidoscope'
        output_columns: For post-processing - columns to keep in final output
                        Options: 'species', 'scientific', 'confidence', 'start', 'end',
                                'file', 'date', 'time', 'location'
        min_confidence: Minimum confidence threshold (default: 0.25)
        sensitivity: Detection sensitivity 0.5-1.5 (default: 1.0)
        overlap: Overlap of analysis segments 0.0-2.9 (default: 0.0)
        lat: Latitude for location filtering
        lon: Longitude for location filtering
        week: Week of year 1-48 for seasonal filtering
        locale: Language for species names (default: 'en')
        custom_output_name: Custom name for output file (optional)

    Returns:
        Analysis results with customized output
    """
    import subprocess
    import sys

    # Resolve audio file path
    audio_path = Path(audio_file)
    if not audio_path.is_absolute():
        audio_path = AUDIO_DIR / audio_file

    if not audio_path.exists():
        for ext in ['.wav', '.mp3', '.flac', '.ogg']:
            test_path = AUDIO_DIR / f"{audio_file}{ext}"
            if test_path.exists():
                audio_path = test_path
                break

    if not audio_path.exists():
        available = list(AUDIO_DIR.glob("*.*"))[:10]
        return f"Audio file not found: {audio_file}\nAvailable files: {[f.name for f in available]}"

    analyze_script = BIRDNET_ANALYZER_DIR / "analyze.py"
    if not analyze_script.exists():
        return f"BirdNET-Analyzer not found at: {BIRDNET_ANALYZER_DIR}"

    # Use 'r' format for more detailed output
    rtype = output_format if output_format in ['csv', 'r', 'table', 'audacity', 'kaleidoscope'] else 'csv'

    cmd = [
        BIRDNET_PYTHON,
        str(analyze_script),
        "--i", str(audio_path),
        "--o", str(RESULTS_DIR),
        "--rtype", rtype,
        "--min_conf", str(min_confidence),
        "--sensitivity", str(sensitivity),
        "--overlap", str(overlap),
        "--locale", locale,
    ]

    if lat is not None and lon is not None:
        cmd.extend(["--lat", str(lat), "--lon", str(lon)])

    if week is not None:
        cmd.extend(["--week", str(week)])

    try:
        result = subprocess.run(
            cmd,
            cwd=str(BIRDNET_ANALYZER_DIR),
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            return f"Analysis failed: {result.stderr[:500]}"

        # Find output file
        audio_stem = audio_path.stem
        csv_path = None

        for pattern in [f"{audio_stem}.BirdNET.results.csv", f"{audio_stem}.BirdNET.results.r.csv",
                       f"{audio_stem}.csv", f"{audio_stem}.r.csv"]:
            test_path = RESULTS_DIR / pattern
            if test_path.exists():
                csv_path = test_path
                break

        if not csv_path:
            csv_files = list(RESULTS_DIR.glob(f"{audio_stem}*"))
            if csv_files:
                csv_path = max(csv_files, key=lambda p: p.stat().st_mtime)

        if not csv_path or not csv_path.exists():
            return "Analysis completed but output not found."

        # Invalidate cache
        global _data_cache
        _data_cache = None

        # Read results
        result_df = pd.read_csv(csv_path)

        # Apply column filtering if specified
        if output_columns and not result_df.empty:
            column_mapping = {
                'species': ['Common name', 'common_name', 'species'],
                'scientific': ['Scientific name', 'scientific_name'],
                'confidence': ['Confidence', 'confidence', 'conf'],
                'start': ['Start (s)', 'start', 'Begin Time (s)'],
                'end': ['End (s)', 'end', 'End Time (s)'],
                'file': ['File', 'filename', 'Recording_Name'],
                'date': ['Date', 'date'],
                'location': ['location', 'site', 'lat', 'lon'],
            }

            cols_to_keep = []
            for requested in output_columns:
                req_lower = requested.lower()
                if req_lower in column_mapping:
                    for possible_col in column_mapping[req_lower]:
                        if possible_col in result_df.columns:
                            cols_to_keep.append(possible_col)
                            break
                elif requested in result_df.columns:
                    cols_to_keep.append(requested)

            if cols_to_keep:
                filtered_df = result_df[cols_to_keep]

                # Save filtered version
                if custom_output_name:
                    custom_path = RESULTS_DIR / f"{custom_output_name}.csv"
                else:
                    custom_path = RESULTS_DIR / f"{audio_stem}.custom.csv"

                filtered_df.to_csv(custom_path, index=False)
                csv_path = custom_path

        # Summarize results
        lines = [
            f"Analysis completed: {audio_path.name}",
            f"Output format: {rtype}",
            f"Results saved to: {csv_path.name}",
            "=" * 60,
        ]

        if result_df.empty:
            lines.append("No bird detections found.")
        else:
            lines.append(f"Total detections: {len(result_df)}")
            lines.append(f"Columns: {', '.join(result_df.columns.tolist())}")

            if 'Common name' in result_df.columns:
                species_counts = result_df['Common name'].value_counts()
                lines.append(f"Unique species: {len(species_counts)}")
                lines.append("\nTop detections:")
                for species, count in species_counts.head(10).items():
                    lines.append(f"  - {species}: {count}")

        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "Analysis timed out after 5 minutes."
    except Exception as e:
        return f"Error analyzing audio: {str(e)}"


@mcp.tool()
def get_birdnet_output_formats() -> str:
    """
    Get information about available BirdNET output formats and their columns.

    Returns:
        Description of each output format and what columns they contain
    """
    formats = """
BirdNET-Analyzer Output Formats
===============================

1. CSV (--rtype csv) - Standard format
   Columns: Start (s), End (s), Scientific name, Common name, Confidence
   Best for: Simple analysis, spreadsheets

2. R Format (--rtype r) - Extended format for R analysis
   Columns: filepath, start, end, scientific_name, common_name, confidence,
            lat, lon, week, overlap, sensitivity, min_conf, species_list, model
   Best for: Detailed analysis, includes all metadata

3. Table (--rtype table) - Raven selection table
   Columns: Selection, View, Channel, Begin Time (s), End Time (s),
            Low Freq (Hz), High Freq (Hz), Species Code, Common Name,
            Confidence, Begin Path, File Offset (s), Begin File
   Best for: Raven Pro software, acoustic analysis

4. Audacity (--rtype audacity) - Audacity label format
   Format: start_time\tend_time\tspecies (confidence)
   Best for: Audacity software labels

5. Kaleidoscope (--rtype kaleidoscope) - Wildlife Acoustics format
   Columns: IN FILE, OFFSET, DURATION, MANUAL ID
   Best for: Kaleidoscope software

Recommendations:
================
- For heatmaps and statistics: Use 'csv' or 'r'
- For maximum detail: Use 'r' format
- For audio review: Use 'audacity' or 'table'
- For custom columns: Use analyze_audio_custom() with output_columns parameter

Example:
  analyze_audio_custom('recording.wav', output_format='r',
                       output_columns=['species', 'confidence', 'start', 'end'])
"""
    return formats


@mcp.tool()
def export_csv(
    output_path: str,
    columns: Optional[list[str]] = None,
    format_type: str = "long",
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    top_n: Optional[int] = None,
    group_by: Optional[str] = None
) -> str:
    """
    Export detection data to a custom CSV file.
    
    Args:
        output_path: Path for output CSV file
        columns: List of columns to include (species, confidence, date, time_of_day, hour, filename, location, count)
        format_type: 'long' (one row per detection), 'wide' (species as columns), or 'summary'
        species: Filter by species name
        min_confidence: Minimum confidence threshold
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
        top_n: Only include top N species by count
        group_by: For wide format - group by 'hour', 'date', or 'time_of_day'
    
    Returns:
        Confirmation message with export details
    """
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."
    
    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to)
    
    if df.empty:
        return "No detections match the specified filters."
    
    if top_n:
        top_species = df['Common name'].value_counts().head(top_n).index.tolist()
        df = df[df['Common name'].isin(top_species)]
    
    output_path_obj = Path(output_path).expanduser()
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    if format_type == "summary":
        summary = df.groupby('Common name').agg({
            'Confidence': ['count', 'mean', 'max']
        }).round(3)
        summary.columns = ['count', 'avg_confidence', 'max_confidence']
        summary = summary.reset_index().sort_values('count', ascending=False)
        summary.to_csv(output_path_obj, index=False)
        return f"Exported summary ({len(summary)} species) to {output_path_obj}"
    
    elif format_type == "wide":
        if group_by == "hour":
            df['Hour'] = ((df['Start_Seconds'].fillna(0) / 3600) % 24).astype(int)
            pivot = pd.crosstab(df['Hour'], df['Common name'])
        elif group_by == "date":
            df['DateStr'] = df['Date'].dt.strftime('%Y-%m-%d')
            pivot = pd.crosstab(df['DateStr'], df['Common name'])
        else:
            pivot = pd.crosstab(df['TimeOfDay'], df['Common name'])
        
        pivot.to_csv(output_path_obj)
        return f"Exported wide format ({pivot.shape[0]} rows x {pivot.shape[1]} columns) to {output_path_obj}"
    
    else:  # long format
        if not columns:
            columns = ['species', 'confidence', 'date', 'time_of_day']
        
        output_df = pd.DataFrame()
        
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ['species', 'common_name']:
                output_df['species'] = df['Common name'].values
            elif col_lower == 'scientific_name' and 'Scientific name' in df.columns:
                output_df['scientific_name'] = df['Scientific name'].values
            elif col_lower == 'confidence':
                output_df['confidence'] = df['Confidence'].round(3).values
            elif col_lower == 'date':
                output_df['date'] = df['Date'].dt.strftime('%Y-%m-%d').values
            elif col_lower in ['time_of_day', 'time', 'period']:
                output_df['time_of_day'] = df['TimeOfDay'].values
            elif col_lower == 'hour':
                output_df['hour'] = ((df['Start_Seconds'].fillna(0) / 3600) % 24).astype(int).values
            elif col_lower in ['recording', 'file', 'filename']:
                output_df['filename'] = df['Recording_Name'].values
        
        output_df.to_csv(output_path_obj, index=False)
        return f"Exported {len(output_df)} rows to {output_path_obj}"


@mcp.tool()
def list_heatmap_types() -> str:
    """
    List all available heatmap types with descriptions.

    Returns:
        Detailed list of heatmap types and when to use each
    """
    types = """
Available Heatmap Types
=======================

**Species Activity Patterns:**
  'species_by_time'     - Species vs Time of Day (Morning/Afternoon/Evening/Night)
                          Best for: Quick overview of daily activity patterns

  'species_by_hour'     - Species vs Hour (0-23)
                          Best for: Detailed hourly activity analysis

  'species_by_weekday'  - Species vs Day of Week (Mon-Sun)
                          Best for: Weekly activity patterns

  'species_by_week'     - Species vs Week Number (1-52)
                          Best for: Seasonal patterns over the year

  'species_by_month'    - Species vs Month (Jan-Dec)
                          Best for: Monthly/seasonal trends

  'species_by_day'      - Species vs Calendar Date
                          Best for: Day-by-day tracking over time

**Temporal Patterns:**
  'day_by_hour'         - Day of Week vs Hour
                          Best for: When are birds most active during the week?

  'week_by_hour'        - Week Number vs Hour
                          Best for: How does hourly activity change seasonally?

  'month_by_hour'       - Month vs Hour
                          Best for: Seasonal shifts in daily timing

  'weekday_by_time'     - Day of Week vs Time of Day
                          Best for: Weekly patterns simplified

**Location Analysis:**
  'location_by_hour'    - Recording Location vs Hour
                          Best for: Comparing activity across sites by time

  'location_by_species' - Location vs Top Species
                          Best for: Which species are at which locations?

  'species_by_location' - Species vs Location
                          Best for: Where is each species detected?

**Detection Quality:**
  'confidence_by_species' - Species vs Confidence Bins
                            Best for: Which species have reliable detections?

  'confidence_by_hour'    - Confidence Level vs Hour
                            Best for: When are detections most reliable?

**Summary Views:**
  'hourly_totals'       - Total detections by hour (all species combined)
                          Best for: Overall daily activity pattern

  'daily_totals'        - Total detections by date
                          Best for: Day-to-day variation in activity

Example Usage:
  generate_heatmap(heatmap_type='species_by_hour', colormap='viridis', top_n=20)
  generate_heatmap(heatmap_type='location_by_species', csv_file='mydata.csv')
"""
    return types


@mcp.tool()
def generate_heatmap(
    heatmap_type: str = "species_by_time",
    csv_file: Optional[str] = None,
    species: Optional[str] = None,
    min_confidence: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    top_n: int = 15,
    colormap: str = "YlOrRd"
):
    """
    Generate a heatmap visualization of bird activity patterns.

    Args:
        heatmap_type: Type of heatmap. Use list_heatmap_types() to see all options.
                      Common types: 'species_by_time', 'species_by_hour', 'species_by_weekday',
                      'species_by_month', 'day_by_hour', 'location_by_species', 'confidence_by_species'
        csv_file: Specific CSV file to use (optional, uses all files if not provided)
        species: Filter by specific species
        min_confidence: Minimum confidence threshold
        date_from: Start date filter (YYYY-MM-DD format)
        date_to: End date filter (YYYY-MM-DD format)
        top_n: Number of top items to include (default: 15)
        colormap: Color scheme - 'YlOrRd', 'viridis', 'Blues', 'Greens', 'plasma', etc.

    Returns:
        Image object for display in Claude Desktop, or error string
    """
    # Load data from specific file or all files
    if csv_file:
        csv_path = RESULTS_DIR / csv_file
        if not csv_path.exists():
            return f"CSV file not found: {csv_file}\nAvailable files in {RESULTS_DIR}"

        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                return f"CSV file is empty: {csv_file}"

            # Add recording name
            if 'Recording_Name' not in df.columns:
                df['Recording_Name'] = csv_path.stem

            # Convert wide format if needed
            if _is_wide_format(df):
                df = _convert_wide_to_long(df, csv_path.stem)

            # Parse dates if missing
            if 'Date' not in df.columns or df['Date'].isna().all():
                df['Date'] = df['Recording_Name'].apply(_parse_date_from_recording)

            # Normalize start time column
            if 'Start_Seconds' not in df.columns:
                for col in ['Start (s)', 'Begin Time (s)', 'start', 'Start']:
                    if col in df.columns:
                        df['Start_Seconds'] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                        break
                else:
                    df['Start_Seconds'] = 0

            # Calculate time of day
            if 'TimeOfDay' not in df.columns:
                df['TimeOfDay'] = df['Start_Seconds'].apply(_parse_time_of_day)

            # Ensure confidence is numeric
            if 'Confidence' in df.columns:
                df['Confidence'] = pd.to_numeric(df['Confidence'], errors='coerce').fillna(0)
            else:
                df['Confidence'] = 1.0

        except Exception as e:
            return f"Error reading CSV file {csv_file}: {str(e)}"
    else:
        df = load_bird_data()
        if df.empty:
            return "No bird detection data available."

    # Apply filters
    df = apply_filters(df, species=species, min_confidence=min_confidence,
                       date_from=date_from, date_to=date_to)

    if df.empty:
        return "No detections match the specified filters."
    
    # Get top species
    top_species = df['Common name'].value_counts().head(top_n).index.tolist()
    df_top = df[df['Common name'].isin(top_species)].copy()

    try:
        if heatmap_type == "species_by_hour":
            df_top['Hour'] = ((df_top['Start_Seconds'] / 3600) % 24).astype(int)
            pivot = pd.crosstab(df_top['Common name'], df_top['Hour'])
            xlabel, ylabel = "Hour of Day", "Species"
        elif heatmap_type == "species_by_day":
            df_top = df_top[df_top['Date'].notna()].copy()
            df_top['DateStr'] = df_top['Date'].dt.strftime('%m-%d')
            pivot = pd.crosstab(df_top['Common name'], df_top['DateStr'])
            xlabel, ylabel = "Date", "Species"
        elif heatmap_type == "day_by_hour":
            df_top['Hour'] = ((df_top['Start_Seconds'] / 3600) % 24).astype(int)
            df_top = df_top[df_top['Date'].notna()].copy()
            df_top['DayOfWeek'] = df_top['Date'].dt.day_name()
            pivot = pd.crosstab(df_top['DayOfWeek'], df_top['Hour'])
            xlabel, ylabel = "Hour", "Day of Week"
        else:  # species_by_time
            pivot = pd.crosstab(df_top['Common name'], df_top['TimeOfDay'])
            pivot = pivot.reindex(columns=['Morning', 'Afternoon', 'Evening', 'Night'], fill_value=0)
            xlabel, ylabel = "Time of Day", "Species"
        
        # Create heatmap
        fig, ax = plt.subplots(figsize=(12, max(6, len(pivot) * 0.4)))
        im = ax.imshow(pivot.values, cmap=colormap, aspect='auto')

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, rotation=45, ha='right')
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        # Add title with file info if specific file was used
        title = f"Bird Activity: {heatmap_type.replace('_', ' ').title()}"
        if csv_file:
            title += f"\n(from {csv_file})"
        ax.set_title(title)

        plt.colorbar(im, ax=ax, label='Detection Count')
        plt.tight_layout()

        # Ensure heatmap directory exists
        HEATMAP_DIR.mkdir(parents=True, exist_ok=True)

        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"heatmap_{heatmap_type}_{timestamp}.png"
        save_path = HEATMAP_DIR / filename

        # Save to disk
        try:
            plt.savefig(save_path, format='png', dpi=150, bbox_inches='tight')
        except Exception as e:
            plt.close()
            return f"Error saving heatmap to {save_path}: {str(e)}"

        plt.close()

        # Verify file was saved
        if not save_path.exists():
            return f"Error: Heatmap file was not saved to {save_path}"

        # Return MCP Image object for proper rendering in Claude Desktop
        return Image(path=save_path)
            
    except Exception as e:
        return f"Error generating heatmap: {str(e)}\n{traceback.format_exc()}"


@mcp.tool()
def generate_heatmap_dynamic(
    csv_file: str,
    row_column: str,
    col_column: str,
    value_column: Optional[str] = None,
    aggregation: str = "count",
    top_n_rows: Optional[int] = None,
    top_n_cols: Optional[int] = None,
    row_transform: Optional[str] = None,
    col_transform: Optional[str] = None,
    title: Optional[str] = None,
    colormap: str = "YlOrRd",
    sort_rows: str = "value",
    sort_cols: str = "natural"
):
    """
    Generate a heatmap from ANY CSV file with fully customizable axes.
    Use inspect_csv_structure first to see available columns.

    Args:
        csv_file: CSV file name or full path (required)
        row_column: Column name for Y-axis/rows (e.g., 'species', 'location', 'datetime')
        col_column: Column name for X-axis/columns (e.g., 'hour', 'date', 'site')
        value_column: Column to aggregate for cell values (optional, uses count if not specified)
        aggregation: How to aggregate values - 'count', 'sum', 'mean', 'max', 'min'
        top_n_rows: Limit to top N rows by total value (optional)
        top_n_cols: Limit to top N columns by total value (optional)
        row_transform: Transform row values - 'hour_from_datetime', 'date_from_datetime',
                       'day_of_week', 'month', 'time_of_day', 'none'
        col_transform: Transform column values - same options as row_transform
        title: Custom title for the heatmap (optional)
        colormap: Matplotlib colormap name (default: 'YlOrRd')
        sort_rows: Sort rows by 'value' (total), 'name' (alphabetical), 'natural' (as-is)
        sort_cols: Sort columns by 'value', 'name', 'natural'

    Returns:
        Image object for display, or error string with column suggestions

    Examples:
        # Species by hour from any CSV with datetime column
        generate_heatmap_dynamic('mydata.csv', row_column='species', col_column='datetime',
                                 col_transform='hour_from_datetime')

        # Location by date
        generate_heatmap_dynamic('mydata.csv', row_column='site', col_column='date')

        # Any two categorical columns
        generate_heatmap_dynamic('mydata.csv', row_column='category1', col_column='category2',
                                 value_column='count', aggregation='sum')
    """
    # Try multiple paths for the CSV file
    csv_path = Path(csv_file)
    if not csv_path.exists():
        csv_path = RESULTS_DIR / csv_file
    if not csv_path.exists():
        # List available files
        available = [f.name for f in RESULTS_DIR.glob('*.csv')][:10]
        return f"CSV file not found: {csv_file}\nAvailable files: {available}"

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return f"CSV file is empty: {csv_file}"

        available_cols = df.columns.tolist()

        # Validate columns exist
        if row_column not in available_cols:
            return f"Row column '{row_column}' not found.\nAvailable columns: {available_cols}"
        if col_column not in available_cols:
            return f"Column column '{col_column}' not found.\nAvailable columns: {available_cols}"
        if value_column and value_column not in available_cols:
            return f"Value column '{value_column}' not found.\nAvailable columns: {available_cols}"

        # Apply transformations to create working columns
        df['_row'] = _apply_transform(df[row_column], row_transform)
        df['_col'] = _apply_transform(df[col_column], col_transform)

        # Remove rows with NaN in key columns
        df = df.dropna(subset=['_row', '_col'])

        if df.empty:
            return "No valid data after applying transformations. Check your column and transform settings."

        # Create pivot table based on aggregation type
        if value_column and aggregation != 'count':
            df['_value'] = pd.to_numeric(df[value_column], errors='coerce').fillna(0)
            pivot = df.pivot_table(
                index='_row',
                columns='_col',
                values='_value',
                aggfunc=aggregation,
                fill_value=0
            )
        else:
            # Count occurrences
            pivot = pd.crosstab(df['_row'], df['_col'])

        if pivot.empty:
            return "No data to display after aggregation."

        # Apply top_n filtering
        if top_n_rows:
            row_totals = pivot.sum(axis=1).nlargest(top_n_rows)
            pivot = pivot.loc[row_totals.index]

        if top_n_cols:
            col_totals = pivot.sum(axis=0).nlargest(top_n_cols)
            pivot = pivot[col_totals.index]

        # Sort rows
        if sort_rows == 'value':
            pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]
        elif sort_rows == 'name':
            pivot = pivot.sort_index()

        # Sort columns
        if sort_cols == 'value':
            pivot = pivot[pivot.sum(axis=0).sort_values(ascending=False).index]
        elif sort_cols == 'name':
            pivot = pivot.reindex(sorted(pivot.columns), axis=1)

        # Create heatmap
        fig_height = max(6, len(pivot.index) * 0.4)
        fig_width = max(10, len(pivot.columns) * 0.4)
        fig, ax = plt.subplots(figsize=(min(fig_width, 20), min(fig_height, 16)))

        im = ax.imshow(pivot.values, cmap=colormap, aspect='auto')

        # Set tick labels
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([str(c) for c in pivot.columns], rotation=45, ha='right', fontsize=8)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels([str(r) for r in pivot.index], fontsize=8)

        # Labels
        col_label = col_column + (f" ({col_transform})" if col_transform else "")
        row_label = row_column + (f" ({row_transform})" if row_transform else "")
        ax.set_xlabel(col_label)
        ax.set_ylabel(row_label)

        # Title
        if title:
            ax.set_title(title)
        else:
            ax.set_title(f"Heatmap: {row_column} vs {col_column}\n({csv_path.name})")

        # Colorbar
        agg_label = f"{aggregation.title()} of {value_column}" if value_column else "Count"
        plt.colorbar(im, ax=ax, label=agg_label)
        plt.tight_layout()

        # Save heatmap
        HEATMAP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"heatmap_dynamic_{timestamp}.png"
        save_path = HEATMAP_DIR / filename

        plt.savefig(save_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()

        return Image(path=save_path)

    except Exception as e:
        plt.close()
        return f"Error generating heatmap: {str(e)}\n{traceback.format_exc()}"


def _apply_transform(series: pd.Series, transform: Optional[str]) -> pd.Series:
    """Apply a transformation to a pandas Series for heatmap axes."""
    if not transform or transform == 'none':
        return series

    if transform == 'hour_from_datetime':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.hour

    elif transform == 'date_from_datetime':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.strftime('%Y-%m-%d')

    elif transform == 'day_of_week':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.day_name()

    elif transform == 'month':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.strftime('%Y-%m')

    elif transform == 'time_of_day':
        dt = pd.to_datetime(series, errors='coerce')
        hours = dt.dt.hour
        return hours.apply(lambda h: 'Night' if pd.isna(h) else
                          'Night' if h < 6 else
                          'Morning' if h < 12 else
                          'Afternoon' if h < 18 else 'Evening')

    elif transform == 'year':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.year

    elif transform == 'week':
        dt = pd.to_datetime(series, errors='coerce')
        return dt.dt.isocalendar().week

    elif transform == 'hour_bin_4':
        # Bin hours into 4-hour periods
        dt = pd.to_datetime(series, errors='coerce')
        hours = dt.dt.hour
        return hours.apply(lambda h: f"{(h//4)*4:02d}-{(h//4)*4+3:02d}" if pd.notna(h) else None)

    elif transform == 'hour_from_seconds':
        # Convert seconds (like BirdNET's Start (s)) to hour of day
        seconds = pd.to_numeric(series, errors='coerce')
        return ((seconds / 3600) % 24).astype(int)

    elif transform == 'time_of_day_from_seconds':
        # Convert seconds to time of day category
        seconds = pd.to_numeric(series, errors='coerce')
        hours = (seconds / 3600) % 24
        return hours.apply(lambda h: 'Night' if pd.isna(h) else
                          'Night' if h < 6 else
                          'Morning' if h < 12 else
                          'Afternoon' if h < 18 else 'Evening')

    elif transform == 'bin_numeric':
        # Bin numeric values into ranges
        numeric = pd.to_numeric(series, errors='coerce')
        return pd.cut(numeric, bins=10, labels=False)

    else:
        return series


@mcp.tool()
def list_csv_columns(csv_file: str) -> str:
    """
    List all columns in a CSV file with their types and sample values.
    Use this to understand what columns are available for heatmap generation.

    Args:
        csv_file: CSV file name or path

    Returns:
        Detailed column information including types and samples
    """
    csv_path = Path(csv_file)
    if not csv_path.exists():
        csv_path = RESULTS_DIR / csv_file
    if not csv_path.exists():
        available = [f.name for f in RESULTS_DIR.glob('*.csv')][:15]
        return f"CSV file not found: {csv_file}\nAvailable files: {available}"

    try:
        df = pd.read_csv(csv_path)

        lines = [
            f"CSV File: {csv_path.name}",
            f"Total Rows: {len(df)}",
            f"Total Columns: {len(df.columns)}",
            "=" * 70,
            ""
        ]

        for col in df.columns:
            dtype = str(df[col].dtype)
            non_null = df[col].notna().sum()
            unique = df[col].nunique()

            # Get sample values
            samples = df[col].dropna().head(3).tolist()
            sample_str = str(samples)[:50]

            lines.append(f"Column: '{col}'")
            lines.append(f"  Type: {dtype}, Non-null: {non_null}/{len(df)}, Unique: {unique}")
            lines.append(f"  Samples: {sample_str}")

            # Suggest transforms for datetime-like columns
            if dtype == 'object':
                try:
                    pd.to_datetime(df[col].head(10), errors='raise')
                    lines.append(f"  Hint: Looks like datetime - try transforms: hour_from_datetime, date_from_datetime, day_of_week")
                except:
                    pass

            lines.append("")

        lines.append("=" * 70)
        lines.append("\nAvailable transforms for generate_heatmap_dynamic:")
        lines.append("  For datetime columns:")
        lines.append("    hour_from_datetime - Extract hour (0-23)")
        lines.append("    date_from_datetime - Extract date (YYYY-MM-DD)")
        lines.append("    day_of_week - Extract day name (Monday, Tuesday, ...)")
        lines.append("    month - Extract month (YYYY-MM)")
        lines.append("    time_of_day - Categorize into Morning/Afternoon/Evening/Night")
        lines.append("    week - Extract week number")
        lines.append("    year - Extract year")
        lines.append("    hour_bin_4 - Group hours into 4-hour bins (00-03, 04-07, ...)")
        lines.append("  For numeric columns (like BirdNET's 'Start (s)'):")
        lines.append("    hour_from_seconds - Convert seconds to hour (0-23)")
        lines.append("    time_of_day_from_seconds - Convert seconds to Morning/Afternoon/Evening/Night")
        lines.append("    bin_numeric - Bin numeric values into 10 ranges")

        return "\n".join(lines)

    except Exception as e:
        return f"Error reading CSV: {str(e)}"


@mcp.tool()
def generate_heatmap_wide(
    csv_file: str,
    row_column: str,
    species_columns: Optional[list[str]] = None,
    exclude_columns: Optional[list[str]] = None,
    row_transform: Optional[str] = None,
    top_n_species: int = 20,
    aggregation: str = "sum",
    title: Optional[str] = None,
    colormap: str = "YlOrRd"
):
    """
    Generate a heatmap from a WIDE format CSV where species/categories are column names.
    Each column represents a category and cell values are counts/values.

    Use this when your CSV has columns like: datetime, location, Species1, Species2, Species3...

    Args:
        csv_file: CSV file name or full path
        row_column: Column for Y-axis (e.g., 'datetime', 'location', 'site')
        species_columns: List of columns to include as species (optional, auto-detects numeric columns)
        exclude_columns: List of columns to exclude from species detection (e.g., ['total', 'sum'])
        row_transform: Transform for row values - 'hour_from_datetime', 'date_from_datetime',
                       'day_of_week', 'month', 'time_of_day'
        top_n_species: Show only top N species by total count (default: 20)
        aggregation: How to aggregate if row_transform groups rows - 'sum', 'mean', 'max'
        title: Custom title for the heatmap
        colormap: Matplotlib colormap name (default: 'YlOrRd')

    Returns:
        Image object or error message

    Example:
        # Your CSV has: datetime, location, American_Crow, House_Finch, Blue_Jay, total_birds
        generate_heatmap_wide(
            csv_file='birds.csv',
            row_column='datetime',
            row_transform='hour_from_datetime',
            exclude_columns=['total_birds', 'location'],
            top_n_species=15
        )
    """
    csv_path = Path(csv_file)
    if not csv_path.exists():
        csv_path = RESULTS_DIR / csv_file
    if not csv_path.exists():
        available = [f.name for f in RESULTS_DIR.glob('*.csv')][:10]
        return f"CSV file not found: {csv_file}\nAvailable: {available}"

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            return f"CSV file is empty: {csv_file}"

        # Validate row column
        if row_column not in df.columns:
            return f"Row column '{row_column}' not found.\nAvailable: {df.columns.tolist()}"

        # Auto-detect species columns (numeric columns)
        if species_columns:
            # Validate provided columns
            missing = [c for c in species_columns if c not in df.columns]
            if missing:
                return f"Species columns not found: {missing}\nAvailable: {df.columns.tolist()}"
            species_cols = species_columns
        else:
            # Auto-detect: numeric columns that aren't excluded
            exclude_set = set(exclude_columns or [])
            exclude_set.add(row_column)
            # Common non-species columns
            exclude_set.update(['total', 'total_birds', 'sum', 'count', 'index', 'id', 'row_num'])

            species_cols = []
            for col in df.columns:
                if col.lower() in [e.lower() for e in exclude_set]:
                    continue
                if df[col].dtype in ['int64', 'float64', 'int32', 'float32']:
                    species_cols.append(col)

        if not species_cols:
            return f"No species columns detected. Specify species_columns parameter.\nNumeric columns: {df.select_dtypes(include='number').columns.tolist()}"

        # Apply row transform
        df['_row'] = _apply_transform(df[row_column], row_transform)
        df = df.dropna(subset=['_row'])

        if df.empty:
            return "No valid data after applying row transformation."

        # Aggregate by row (in case transform groups multiple rows)
        agg_dict = {col: aggregation for col in species_cols}
        pivot = df.groupby('_row')[species_cols].agg(agg_dict)

        # Get top N species by total
        species_totals = pivot.sum().sort_values(ascending=False)
        top_species = species_totals.head(top_n_species).index.tolist()
        pivot = pivot[top_species]

        # Clean species names (replace underscores)
        pivot.columns = [str(c).replace('_', ' ') for c in pivot.columns]

        # Transpose so species are rows and time/location are columns
        pivot = pivot.T

        # Sort rows by total value
        pivot = pivot.loc[pivot.sum(axis=1).sort_values(ascending=False).index]

        # Create heatmap
        fig_height = max(6, len(pivot.index) * 0.4)
        fig_width = max(10, len(pivot.columns) * 0.3)
        fig, ax = plt.subplots(figsize=(min(fig_width, 20), min(fig_height, 16)))

        im = ax.imshow(pivot.values, cmap=colormap, aspect='auto')

        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels([str(c) for c in pivot.columns], rotation=45, ha='right', fontsize=8)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index, fontsize=8)

        row_label = row_column + (f" ({row_transform})" if row_transform else "")
        ax.set_xlabel(row_label)
        ax.set_ylabel("Species")

        if title:
            ax.set_title(title)
        else:
            ax.set_title(f"Species Activity Heatmap\n({csv_path.name})")

        plt.colorbar(im, ax=ax, label=f'{aggregation.title()} Count')
        plt.tight_layout()

        # Save
        HEATMAP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"heatmap_wide_{timestamp}.png"
        save_path = HEATMAP_DIR / filename

        plt.savefig(save_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()

        return Image(path=save_path)

    except Exception as e:
        plt.close()
        return f"Error generating heatmap: {str(e)}\n{traceback.format_exc()}"


@mcp.tool()
def list_colormaps(category: Optional[str] = None) -> str:
    """
    List available colormaps for heatmap generation.

    Args:
        category: Filter by category - 'sequential', 'diverging', 'qualitative', or None for all

    Returns:
        List of colormap names with descriptions and recommendations
    """
    colormaps = {
        'sequential': {
            'description': 'Best for single-variable data (counts, frequencies)',
            'maps': {
                'YlOrRd': 'Yellow → Orange → Red (default, great for activity data)',
                'YlGnBu': 'Yellow → Green → Blue (cool, nature-friendly)',
                'Reds': 'Light → Dark Red (intensity focus)',
                'Blues': 'Light → Dark Blue (calm, professional)',
                'Greens': 'Light → Dark Green (nature theme)',
                'Oranges': 'Light → Dark Orange (warm)',
                'Purples': 'Light → Dark Purple (elegant)',
                'Greys': 'Light → Dark Grey (print-friendly)',
                'viridis': 'Purple → Green → Yellow (colorblind-friendly, recommended)',
                'plasma': 'Purple → Pink → Yellow (vibrant)',
                'inferno': 'Black → Red → Yellow (high contrast)',
                'magma': 'Black → Purple → White (dramatic)',
                'cividis': 'Blue → Yellow (colorblind-friendly)',
                'hot': 'Black → Red → Yellow → White (heat map style)',
                'copper': 'Black → Copper (metallic)',
            }
        },
        'diverging': {
            'description': 'Best for data with meaningful center point (deviations, comparisons)',
            'maps': {
                'RdYlGn': 'Red → Yellow → Green (traffic light style)',
                'RdYlBu': 'Red → Yellow → Blue (temperature style)',
                'RdBu': 'Red → White → Blue (simple diverging)',
                'coolwarm': 'Blue → White → Red (subtle)',
                'seismic': 'Blue → White → Red (dramatic)',
                'PiYG': 'Pink → White → Green',
                'PRGn': 'Purple → White → Green',
                'BrBG': 'Brown → White → Blue-Green',
            }
        },
        'qualitative': {
            'description': 'Best for categorical data (distinct groups)',
            'maps': {
                'Set1': '9 bold distinct colors',
                'Set2': '8 pastel distinct colors',
                'Set3': '12 light distinct colors',
                'Paired': '12 paired colors',
                'tab10': '10 Tableau colors',
                'tab20': '20 Tableau colors',
                'Pastel1': '9 pastel colors',
                'Dark2': '8 dark distinct colors',
            }
        }
    }

    lines = ["Available Colormaps for Heatmaps", "=" * 50, ""]

    categories_to_show = [category] if category else colormaps.keys()

    for cat in categories_to_show:
        if cat not in colormaps:
            continue

        info = colormaps[cat]
        lines.append(f"**{cat.upper()}**")
        lines.append(f"  {info['description']}")
        lines.append("")

        for name, desc in info['maps'].items():
            lines.append(f"  '{name}' - {desc}")

        lines.append("")

    lines.append("-" * 50)
    lines.append("\nRecommendations:")
    lines.append("  - Bird activity data: 'YlOrRd' or 'viridis'")
    lines.append("  - Colorblind-friendly: 'viridis', 'cividis', or 'plasma'")
    lines.append("  - Print/grayscale: 'Greys' or 'viridis'")
    lines.append("  - High contrast: 'inferno' or 'hot'")
    lines.append("  - Nature theme: 'Greens' or 'YlGnBu'")
    lines.append("\nUsage: generate_heatmap_dynamic(..., colormap='viridis')")

    return "\n".join(lines)


# =============================================================================
# MCP Resources
# =============================================================================

@mcp.resource("birdnet://data/species-list")
def get_species_list_resource() -> str:
    """Get a list of all detected species with basic statistics."""
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."

    stats = df.groupby('Common name').agg({
        'Confidence': ['count', 'mean', 'max']
    }).round(3)
    stats.columns = ['Count', 'Avg_Confidence', 'Max_Confidence']
    stats = stats.sort_values('Count', ascending=False)

    return stats.to_json(orient='records', indent=2)


@mcp.resource("birdnet://data/detections-summary")
def get_detections_summary_resource() -> str:
    """Get overall summary statistics of all bird detections."""
    df = load_bird_data()
    if df.empty:
        return "No bird detection data available."

    summary = {
        "total_detections": len(df),
        "unique_species": int(df['Common name'].nunique()),
        "date_range": {
            "earliest": df['Date'].min().isoformat() if pd.notna(df['Date'].min()) else None,
            "latest": df['Date'].max().isoformat() if pd.notna(df['Date'].max()) else None
        },
        "confidence_stats": {
            "mean": float(df['Confidence'].mean()),
            "min": float(df['Confidence'].min()),
            "max": float(df['Confidence'].max())
        },
        "top_5_species": df['Common name'].value_counts().head(5).to_dict()
    }

    import json
    return json.dumps(summary, indent=2)


@mcp.resource("birdnet://data/csv-files")
def list_csv_files_resource() -> str:
    """List all available CSV result files."""
    csv_files = list(RESULTS_DIR.glob(SUPPORTED_FILE_PATTERN))
    csv_files = [f for f in csv_files if not f.name.startswith('combined')]

    files_info = []
    for csv_file in sorted(csv_files, key=lambda x: x.stat().st_mtime, reverse=True):
        files_info.append({
            "filename": csv_file.name,
            "size_bytes": csv_file.stat().st_size,
            "modified": datetime.fromtimestamp(csv_file.stat().st_mtime).isoformat(),
            "path": str(csv_file)
        })

    import json
    return json.dumps(files_info, indent=2)


@mcp.resource("birdnet://data/audio-files")
def list_audio_files_resource() -> str:
    """List all available audio recording files."""
    if not AUDIO_DIR.exists():
        return f"Audio directory not found: {AUDIO_DIR}"

    audio_extensions = {'.wav', '.mp3', '.flac', '.ogg', '.m4a'}
    audio_files = []

    for f in AUDIO_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in audio_extensions:
            audio_files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                "path": str(f),
                "format": f.suffix.lower()[1:]
            })

    # Sort by modification time (newest first)
    audio_files.sort(key=lambda x: x['modified'], reverse=True)

    import json
    return json.dumps(audio_files, indent=2)


@mcp.resource("birdnet://csv/{filename}")
def get_csv_content(filename: str) -> str:
    """
    Get the content of a specific CSV file.

    Args:
        filename: Name of the CSV file to read
    """
    csv_path = RESULTS_DIR / filename

    if not csv_path.exists():
        return json.dumps({"error": f"CSV file not found: {filename}"})

    try:
        df = pd.read_csv(csv_path)

        result = {
            "filename": filename,
            "rows": len(df),
            "columns": df.columns.tolist(),
            "format": "wide" if _is_wide_format(df) else "long",
            "data": df.head(100).to_dict(orient='records')  # First 100 rows
        }

        import json
        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        import json
        return json.dumps({"error": f"Error reading CSV: {str(e)}"}, indent=2)


# =============================================================================
# MCP Prompts
# =============================================================================

@mcp.prompt()
def analyze_rare_birds(min_confidence: float = 0.7, max_occurrences: int = 3) -> str:
    """Find and analyze rare bird species in your recordings.

    Args:
        min_confidence: Minimum confidence threshold (default: 0.7)
        max_occurrences: Maximum detections to be considered rare (default: 3)
    """
    return f"""Please analyze rare bird detections in my BirdNET data:

1. Use the find_rare_detections tool with min_confidence={min_confidence} and max_occurrence_count={max_occurrences}
2. For each rare species found, use get_species_details to get more information
3. Summarize which rare birds might be worth investigating further based on:
   - Confidence scores (higher is more reliable)
   - Time of day patterns
   - Geographic likelihood for my area
4. Suggest if any detections might be false positives based on confidence scores and typical habitat ranges
5. Recommend which recordings I should listen to verify these rare sightings
"""


@mcp.prompt()
def daily_summary(last_n_days: int = 7) -> str:
    """Get a comprehensive daily bird activity summary.

    Args:
        last_n_days: Number of recent days to analyze (default: 7)
    """
    return f"""Please provide a daily summary of bird activity for the last {last_n_days} days:

1. Use get_daily_summary with last_n_days={last_n_days}
2. Identify any unusual patterns such as:
   - Days with exceptionally high or low activity
   - New species that appeared recently
   - Species that disappeared after being regular
3. Highlight the most active days and which species were dominant
4. Compare weekday vs weekend patterns if applicable
5. Suggest interesting trends worth investigating further
"""


@mcp.prompt()
def species_deep_dive(species_name: str) -> str:
    """Perform comprehensive analysis of a specific bird species.

    Args:
        species_name: Name of the species to analyze
    """
    return f"""Please perform a deep dive analysis on {species_name}:

1. Use get_species_details to get basic statistics
2. Use get_detections with species filter to see individual detection patterns
3. Analyze temporal patterns:
   - What times of day is this species most active?
   - Are there seasonal patterns in the detections?
   - Any trends over time (increasing/decreasing)?
4. Use get_confidence_statistics to understand detection reliability
5. Provide insights about:
   - Whether this is a resident or migrant species based on patterns
   - Best times to observe or record this species
   - Any unusual detection patterns that might need verification
"""


@mcp.prompt()
def peak_activity_report() -> str:
    """Analyze when bird activity peaks during the day."""
    return """Please analyze peak bird activity times:

1. Use get_peak_activity_times to see overall patterns
2. Identify the most active time periods
3. For the top 5 species, check their individual peak times using get_species_details
4. Create a summary showing:
   - When is the best time to record birds overall?
   - Which species are most active at different times?
   - Any species with unusual activity patterns (e.g., nocturnal birds)?
5. Optionally generate a heatmap visualization using generate_heatmap with type 'species_by_hour'
"""


@mcp.prompt()
def compare_time_periods(period1_start: str, period1_end: str, period2_start: str, period2_end: str) -> str:
    """Compare bird activity between two time periods.

    Args:
        period1_start: Start date for first period (YYYY-MM-DD)
        period1_end: End date for first period (YYYY-MM-DD)
        period2_start: Start date for second period (YYYY-MM-DD)
        period2_end: End date for second period (YYYY-MM-DD)
    """
    return f"""Please compare bird activity between two time periods:

**Period 1:** {period1_start} to {period1_end}
**Period 2:** {period2_start} to {period2_end}

Analysis steps:
1. Get species list for Period 1 using list_detected_species with date filters
2. Get species list for Period 2 using the same approach
3. Compare and identify:
   - Species present in both periods
   - Species only in Period 1 (disappeared)
   - Species only in Period 2 (new arrivals)
4. For common species, compare detection frequencies
5. Use get_daily_summary for each period to compare overall activity levels
6. Provide insights about:
   - Possible migration patterns
   - Seasonal changes in bird community
   - Changes in recording effort or conditions
"""


@mcp.prompt()
def generate_activity_heatmap(heatmap_type: str = "species_by_time", top_n: int = 15, csv_file: Optional[str] = None) -> str:
    """Generate visualizations of bird activity patterns.

    Args:
        heatmap_type: Type of heatmap - 'species_by_time', 'species_by_hour', 'species_by_day', or 'day_by_hour'
        top_n: Number of top species to include (default: 15)
        csv_file: Specific CSV file to analyze (optional, uses all files if not provided)
    """
    csv_instruction = f'   - csv_file="{csv_file}"' if csv_file else '   - (no csv_file specified, will use all CSV files)'

    return f"""Please generate a bird activity heatmap visualization:

1. Use generate_heatmap with:
   - heatmap_type="{heatmap_type}"
   - top_n={top_n}
{csv_instruction}
2. Analyze the visualization and describe:
   - Clear patterns in the data
   - Species with distinct temporal preferences
   - Any gaps or anomalies in the data
3. Suggest follow-up analyses based on patterns observed
4. Provide the heatmap image in your response

Common heatmap types:
- 'species_by_time': Species vs Morning/Afternoon/Evening/Night
- 'species_by_hour': Species vs Hour of day (0-23)
- 'species_by_day': Species vs Calendar days
- 'day_by_hour': Day of week vs Hour of day
"""


@mcp.prompt()
def select_file_for_heatmap() -> str:
    """Interactively select a CSV file and generate a heatmap from it."""
    return """Please help me generate a heatmap from a specific CSV file:

1. First, list all available CSV files using the list_csv_files_resource or inspect_csv_structure
2. Show me the available CSV files with their details (size, date modified, etc.)
3. Ask me which file I want to use for the heatmap
4. Once I select a file, use generate_heatmap with the csv_file parameter set to my chosen file
5. Also ask what type of heatmap I want:
   - 'species_by_time': Species vs Morning/Afternoon/Evening/Night (best for daily patterns)
   - 'species_by_hour': Species vs Hour of day 0-23 (detailed hourly breakdown)
   - 'species_by_day': Species vs Calendar days (track changes over time)
   - 'day_by_hour': Day of week vs Hour (weekly patterns)
6. Generate and display the heatmap inline

This workflow allows you to focus on specific recordings or time periods.
"""


@mcp.prompt()
def identify_new_visitors(recent_days: int = 7, comparison_days: int = 30) -> str:
    """Identify bird species detected recently that weren't seen before.

    Args:
        recent_days: Number of recent days to check (default: 7)
        comparison_days: Number of days before that to compare against (default: 30)
    """
    return f"""Please identify new bird visitors in recent recordings:

1. Get detections from the last {recent_days} days using get_detections with date filters
2. Get detections from the previous {comparison_days} days (before the recent period)
3. Identify species that appear in recent data but NOT in the comparison period
4. For each new species:
   - Use get_species_details to learn more about it
   - Check confidence scores to assess reliability
   - Note when it was first detected
5. Provide insights about:
   - Possible reasons for new arrivals (migration, weather, habitat changes)
   - Whether these are expected species for the region
   - Recommendations for confirming these detections
6. Suggest which recordings to review to verify these new visitors
"""


@mcp.prompt()
def quality_check(min_confidence_threshold: float = 0.5) -> str:
    """Analyze detection quality and identify potential issues.

    Args:
        min_confidence_threshold: Confidence threshold for reliable detections (default: 0.5)
    """
    return f"""Please perform a quality check on the BirdNET detection data:

1. Use get_confidence_statistics to see confidence distributions for all species
2. Identify species with:
   - Very low average confidence scores (possible false positives)
   - High variance in confidence (inconsistent detections)
   - Single very high confidence detection (possible anomaly)
3. Use list_detected_species with min_confidence={min_confidence_threshold} to filter reliable data
4. Compare total detections vs high-confidence detections
5. Provide recommendations:
   - Which species detections are most reliable?
   - Which species need manual verification?
   - What confidence threshold would you recommend for analysis?
   - Any recording quality issues to investigate?
"""


@mcp.prompt()
def choose_heatmap_colors() -> str:
    """Show available colormap options for heatmaps and help choose one."""
    return """Please help me choose a colormap (color scheme) for my heatmap:

Show me the available colormap options organized by category:

**Sequential (best for single-variable data like counts):**
- 'YlOrRd' - Yellow to Orange to Red (default, great for bird activity)
- 'YlGnBu' - Yellow to Green to Blue (cool tones)
- 'Reds' - Light to Dark Red
- 'Blues' - Light to Dark Blue
- 'Greens' - Light to Dark Green
- 'Oranges' - Light to Dark Orange
- 'Purples' - Light to Dark Purple
- 'Greys' - Light to Dark Grey
- 'viridis' - Purple to Yellow (colorblind-friendly)
- 'plasma' - Purple to Yellow (vibrant)
- 'inferno' - Black to Yellow (high contrast)
- 'magma' - Black to Pink/White

**Diverging (best for data with positive/negative or center point):**
- 'RdYlGn' - Red to Yellow to Green
- 'RdYlBu' - Red to Yellow to Blue
- 'RdBu' - Red to Blue
- 'coolwarm' - Blue to Red
- 'seismic' - Blue to White to Red

**Qualitative (best for categorical data):**
- 'Set1', 'Set2', 'Set3' - Distinct colors
- 'Paired' - Paired colors
- 'tab10', 'tab20' - Tableau colors

After I choose a colormap, generate the heatmap with my selection using the `colormap` parameter.
"""


@mcp.prompt()
def generate_custom_heatmap() -> str:
    """Interactive guide for generating heatmaps from any CSV file."""
    return """Please help me create a custom heatmap from my CSV data:

**Step 1: Explore my CSV file**
Use `list_csv_columns('filename.csv')` to show me all columns, their types, and sample values.

**Step 2: Choose the heatmap type based on my CSV format**

If my CSV has species/categories as COLUMNS (wide format):
- Use `generate_heatmap_wide()`
- Example: datetime, location, Species1, Species2, Species3...

If my CSV has data in ROWS (long format):
- Use `generate_heatmap_dynamic()`
- Example: each row has species, datetime, count, etc.

**Step 3: Ask me these questions:**
1. Which column should be on the Y-axis (rows)?
2. Which column should be on the X-axis (columns)?
3. Do I need to transform any column? (e.g., extract hour from datetime)
4. What colormap do I want? Options:
   - 'YlOrRd' (warm, default)
   - 'viridis' (colorblind-friendly)
   - 'Blues' (cool)
   - 'Greens' (nature theme)
   - 'plasma' (vibrant)
   - 'inferno' (high contrast)
5. How many top items to show? (top_n_rows, top_n_species)

**Step 4: Generate the heatmap with my choices**

Example for wide format:
```
generate_heatmap_wide(
    csv_file='my_data.csv',
    row_column='datetime',
    row_transform='hour_from_datetime',
    colormap='viridis',
    top_n_species=15
)
```

Example for long format:
```
generate_heatmap_dynamic(
    csv_file='my_data.csv',
    row_column='species',
    col_column='timestamp',
    col_transform='day_of_week',
    colormap='YlGnBu',
    top_n_rows=20
)
```
"""


@mcp.prompt()
def heatmap_from_any_csv() -> str:
    """Step-by-step guide for generating heatmaps from any CSV structure."""
    return """I want to generate a heatmap from a CSV file. Please guide me through:

**1. First, show me available CSV files:**
Use `inspect_csv_structure()` to list all CSV files and their structure.

**2. Once I pick a file, analyze its columns:**
Use `list_csv_columns('my_file.csv')` to show:
- All column names
- Data types
- Sample values
- Suggested transforms

**3. Help me decide:**
- What goes on Y-axis (rows)?
- What goes on X-axis (columns)?
- Do I need transforms? Available transforms:
  - `hour_from_datetime` - Extract hour (0-23)
  - `day_of_week` - Extract day name
  - `time_of_day` - Morning/Afternoon/Evening/Night
  - `month` - Extract YYYY-MM
  - `hour_from_seconds` - For BirdNET's Start (s) column

**4. Choose a color scheme:**
- 'YlOrRd' - Yellow-Orange-Red (warm, default)
- 'viridis' - Purple-Green-Yellow (colorblind-safe)
- 'Blues' - Light to dark blue
- 'Greens' - Nature theme
- 'plasma' - Vibrant purple-yellow
- 'coolwarm' - Blue to red

**5. Generate the heatmap based on format:**

For WIDE format (species as columns):
→ `generate_heatmap_wide(...)`

For LONG format (one observation per row):
→ `generate_heatmap_dynamic(...)`

Show me the generated heatmap inline.
"""


@mcp.prompt()
def compare_colormaps(csv_file: str = "WildsBird_Every_Hour.csv") -> str:
    """Generate the same heatmap with different colormaps for comparison.

    Args:
        csv_file: CSV file to use for comparison (default: WildsBird_Every_Hour.csv)
    """
    return f"""Please generate multiple heatmaps with different color schemes so I can compare them:

Using the file '{csv_file}', generate 3-4 heatmaps with different colormaps:

1. **Warm colors** - colormap='YlOrRd' (Yellow-Orange-Red)
2. **Cool colors** - colormap='Blues' or 'YlGnBu'
3. **Colorblind-friendly** - colormap='viridis'
4. **High contrast** - colormap='inferno' or 'plasma'

Use the same data and settings for each, only changing the colormap parameter.

After generating, ask me which color scheme I prefer for future heatmaps.
"""


@mcp.prompt()
def complete_bird_analysis_workflow() -> str:
    """Complete end-to-end workflow: Upload audio → Analyze → Explore → Visualize."""
    return """Let's go through the complete bird audio analysis workflow:

**STEP 1: Check Available Audio Files**
First, let me see what audio files are available for analysis.
→ Use `list_audio_files()` to show available recordings

**STEP 2: Analyze Audio with BirdNET**
Choose how to analyze:

Option A - Single file:
```
analyze_audio('recording.wav', min_confidence=0.25)
```

Option B - Multiple files with custom output:
```
analyze_audio_batch(
    file_pattern='*.wav',
    output_format='csv',  # or 'r' for more columns
    combine_results=True,
    min_confidence=0.25
)
```

Option C - Custom columns:
```
analyze_audio_custom(
    'recording.wav',
    output_format='r',
    output_columns=['species', 'confidence', 'start', 'end']
)
```

**STEP 3: Review Results**
After analysis, explore the data:
- `list_detected_species()` - See all species found
- `get_detections()` - View detailed detections
- `get_confidence_statistics()` - Check detection quality

**STEP 4: Generate Visualizations**
Create heatmaps from the results:
- `generate_heatmap(heatmap_type='species_by_hour')` - Activity by hour
- `generate_heatmap_dynamic(...)` - Custom heatmaps
- `list_colormaps()` - Choose color schemes

**STEP 5: Export or Further Analysis**
- `export_csv(...)` - Export filtered data
- Ask questions about patterns, species, trends

What would you like to do? I'll guide you through each step.
"""


@mcp.prompt()
def analyze_my_audio() -> str:
    """Interactive prompt to analyze user's audio files."""
    return """I'll help you analyze your audio files with BirdNET. Let's start:

**Step 1: Where are your audio files?**

First, let me check the default audio directory:
→ `list_audio_files()`

If your files are elsewhere, tell me the path and I'll check:
→ `list_audio_files('/path/to/your/audio')`

**Step 2: Choose analysis options**

Once we find your files, I'll ask you about:
1. **Which files?** - Single file, specific files, or all files
2. **Output format?**
   - 'csv' - Standard (species, confidence, time)
   - 'r' - Extended (includes location, settings metadata)
3. **Detection settings?**
   - Minimum confidence (0.1-0.99, default 0.25)
   - Sensitivity (0.5-1.5, default 1.0)
4. **Location filtering?** - Latitude/longitude to filter unlikely species
5. **Custom output?** - Which columns do you want in the results?

**Step 3: Run the analysis**

I'll run BirdNET-Analyzer and show you the results summary.

**Step 4: Explore & Visualize**

After analysis, you can:
- View statistics and species lists
- Generate heatmaps with your preferred colors
- Export custom reports

Let's start - show me your audio files!
"""


@mcp.prompt()
def quick_analysis() -> str:
    """Quick analysis with default settings for immediate results."""
    return """Let's do a quick analysis of your audio files:

**Quick Start:**

1. First, I'll list your audio files:
   → `list_audio_files()`

2. Then analyze with optimized defaults:
   → `analyze_audio_batch(min_confidence=0.25, combine_results=True)`

3. Show what we found:
   → `list_detected_species()`

4. Generate a heatmap:
   → `generate_heatmap(heatmap_type='species_by_hour')`

This uses default settings optimized for most recordings:
- Confidence threshold: 0.25 (balanced accuracy)
- Sensitivity: 1.0 (standard)
- Output: Combined CSV for easy analysis

Want me to proceed with the quick analysis?
"""


@mcp.prompt()
def setup_custom_csv_columns() -> str:
    """Guide for setting up custom CSV output columns from BirdNET."""
    return """I'll help you set up custom output columns for your BirdNET analysis.

**Available Output Formats:**

1. **Standard CSV** (default)
   - Start (s), End (s), Scientific name, Common name, Confidence

2. **R Format** (extended)
   - All standard columns PLUS:
   - filepath, lat, lon, week, overlap, sensitivity, min_conf, species_list, model

3. **Custom Selection** - Pick only what you need:
   - `species` - Common name
   - `scientific` - Scientific name
   - `confidence` - Detection confidence
   - `start` - Start time (seconds)
   - `end` - End time (seconds)
   - `file` - Source file name
   - `date` - Detection date
   - `location` - Recording location

**Example: Create a minimal output**
```
analyze_audio_custom(
    'recording.wav',
    output_format='r',
    output_columns=['species', 'confidence', 'start'],
    custom_output_name='my_minimal_results'
)
```

**Example: Create location-aware output**
```
analyze_audio_custom(
    'recording.wav',
    output_format='r',
    lat=35.6762,
    lon=-105.9378,
    output_columns=['species', 'confidence', 'start', 'end', 'location']
)
```

What columns would you like in your output?
"""


@mcp.prompt()
def after_analysis_options() -> str:
    """What to do after BirdNET analysis is complete."""
    return """Great! Your audio has been analyzed. Here's what you can do now:

**📊 View Statistics**
- `list_detected_species()` - All species with counts
- `get_confidence_statistics()` - Detection quality analysis
- `get_detections(top_n=20)` - Most confident detections

**🔍 Filter & Search**
- `get_detections(species='Northern Cardinal')` - Specific species
- `get_detections(min_confidence=0.7)` - High-confidence only
- `get_detections(time_of_day='Morning')` - By time period

**📈 Generate Heatmaps**
- `generate_heatmap(heatmap_type='species_by_hour')` - Activity by hour
- `generate_heatmap(heatmap_type='species_by_time')` - By time of day
- `generate_heatmap_dynamic(...)` - Fully custom heatmaps
- `list_colormaps()` - Choose colors

**📁 Export Data**
- `export_csv('my_report.csv', format_type='summary')` - Summary report
- `export_csv('detailed.csv', columns=['species','confidence','date'])` - Custom columns

**🎨 Customize Visualizations**
- Choose colormaps: 'viridis', 'YlOrRd', 'Blues', 'plasma'
- Filter by confidence, date range, or species

What would you like to explore?
"""


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Run the MCP server."""
    import sys
    print(f"Starting SongSage v2.1.0...", file=sys.stderr)
    print(f"Results directory: {RESULTS_DIR}", file=sys.stderr)
    print(f"Audio directory: {AUDIO_DIR}", file=sys.stderr)
    print(f"BirdNET Python: {BIRDNET_PYTHON}", file=sys.stderr)
    
    # Pre-load data
    try:
        df = load_bird_data()
        if not df.empty:
            species_count = df['Common name'].nunique()
            print(f"Loaded {len(df)} detections across {species_count} species", file=sys.stderr)
        else:
            print("No data loaded - check your CSV files", file=sys.stderr)
    except Exception as e:
        print(f"Error loading data: {e}", file=sys.stderr)
    
    mcp.run()


if __name__ == "__main__":
    main()
