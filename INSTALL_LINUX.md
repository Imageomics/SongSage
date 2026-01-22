# Linux Installation

## Prerequisites

1. **Python 3.10+**
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install python3 python3-venv python3-pip

   # Fedora
   sudo dnf install python3 python3-pip
   ```

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

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p heatmaps
```

## Configure Claude Desktop

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "songsage": {
      "command": "/home/YOUR_USERNAME/SongSage/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/home/YOUR_USERNAME/SongSage"
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

**"python3: command not found"**
```bash
sudo apt install python3
```

**"No module named venv"**
```bash
sudo apt install python3-venv
```

**Setup script permission denied**
```bash
chmod +x setup.sh
```

**TensorFlow GPU support (optional)**
```bash
source venv/bin/activate
pip install tensorflow[and-cuda]
```
