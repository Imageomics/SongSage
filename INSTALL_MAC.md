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
      "args": ["/Users/YOUR_USERNAME/SongSage/mcp_server.py"],
      "cwd": "/Users/YOUR_USERNAME/SongSage"
    }
  }
}
```

Replace `YOUR_USERNAME` with your macOS username (run `whoami` to find it).

> **Important:** All three paths must be **full absolute paths**. If you cloned SongSage to a different location (e.g. `~/Downloads/SongSage`), use that full path instead. Run `pwd` inside the SongSage folder to get the exact path.

Restart Claude Desktop.

## Optional: Configure BirdNET Paths

If BirdNET-Analyzer-Sierra isn't auto-detected, create `.env` in the SongSage folder:

```
BIRDNET_RESULTS_DIR=/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=/path/to/BirdNET-Analyzer-Sierra
```

## Verify Your Setup

After restarting Claude Desktop, look for the MCP tools icon (hammer) in the chat input. Type one of these to confirm the connection:

> "List all detected bird species"

If you don't have BirdNET results yet, point your `.env` at the included sample data:

```
BIRDNET_RESULTS_DIR=/Users/YOUR_USERNAME/SongSage/test_data
```

## Troubleshooting

**Server won't connect / shows disconnected**
- Make sure all paths in the config are **full absolute paths** (not `~` or relative)
- If you cloned to `~/Downloads/SongSage`, use `/Users/YOUR_USERNAME/Downloads/SongSage` everywhere
- Fully quit and reopen Claude Desktop after config changes

**Broken venv after moving the project folder**
```bash
cd /path/to/SongSage
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

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

**Debug logs:** `~/Library/Logs/Claude/mcp-server-songsage.log`
