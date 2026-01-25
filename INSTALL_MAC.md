# macOS Installation

## Prerequisites

1. **Python 3.10+**
   ```bash
   brew install python@3.11
   ```
   Or download from [python.org](https://www.python.org/downloads/)

2. **BirdNET-Analyzer-Sierra** - Must be installed and accessible on your system

3. **Claude Desktop** from [claude.ai/download](https://claude.ai/download)

## Installation Steps

1. Clone the repository:

```bash
git clone https://github.com/Imageomics/SongSage.git
cd SongSage
```

2. Run the setup script:

```bash
chmod +x setup.sh
./setup.sh
```

## Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "songsage": {
      "command": "/Users/YOUR_USERNAME/SongSage/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/Users/YOUR_USERNAME/SongSage"
    }
  }
}
```

Replace `YOUR_USERNAME` (run `whoami` to find it).

Restart Claude Desktop.

## Optional: Configure BirdNET Paths

If BirdNET-Analyzer-Sierra isn't auto-detected, create `.env` in the SongSage folder:

```
BIRDNET_RESULTS_DIR=/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=/path/to/BirdNET-Analyzer-Sierra
```

## Troubleshooting

**TensorFlow fails on Apple Silicon (M1/M2/M3)**
```bash
source venv/bin/activate
pip install tensorflow-macos tensorflow-metal
```

**"xcrun: error" after macOS update**
```bash
xcode-select --install
```

**Setup script permission denied**
```bash
chmod +x setup.sh
```
