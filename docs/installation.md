# SongSage Installation

## Prerequisites

- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
  - Windows: check "Add Python to PATH" during installation
- **BirdNET-Analyzer-Sierra** — must be installed and accessible on your system
- **Claude Desktop** — [claude.ai/download](https://claude.ai/download)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Imageomics/SongSage.git
cd SongSage
```

### 2. Set up the environment

**Mac/Linux:**

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

**Windows** (Command Prompt or PowerShell — not Git Bash):

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
mkdir heatmaps
```

> **Windows note:** The `setup.sh` script is for Mac/Linux only. Do not run it in Git Bash — use Command Prompt or PowerShell instead.

---

## Configuration

### Mac/Linux Configuration

Edit `~/.config/Claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "songsage": {
      "command": "/home/YOUR_USERNAME/SongSage/venv/bin/python",
      "args": ["/home/YOUR_USERNAME/SongSage/mcp_server.py"],
      "cwd": "/home/YOUR_USERNAME/SongSage"
    }
  }
}
```

Replace `YOUR_USERNAME` with your username (run `whoami` to find it), and update the path if you cloned SongSage to a different location. Run `pwd` inside the SongSage folder to get the exact path.

### Windows Configuration

Edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "songsage": {
      "command": "C:/Users/YOUR_USERNAME/SongSage/venv/Scripts/python.exe",
      "args": ["C:/Users/YOUR_USERNAME/SongSage/mcp_server.py"],
      "cwd": "C:/Users/YOUR_USERNAME/SongSage"
    }
  }
}
```

Replace `YOUR_USERNAME` with your Windows username and use forward slashes `/` in paths. Run `cd` inside the SongSage folder to see the exact path.

> **Important (all platforms):** All three paths (`command`, `args`, `cwd`) must be **full absolute paths** — no `~`, no relative paths.

Restart Claude Desktop after editing.

### Optional: Configure BirdNET Paths

If BirdNET-Analyzer-Sierra isn't auto-detected (it looks for `~/BirdNET-Analyzer-Sierra` or `~/BirdNET-Analyzer`), create a `.env` file in the SongSage folder. See `.env.example` for a template:

**Mac/Linux:**
```
BIRDNET_RESULTS_DIR=/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=/path/to/BirdNET-Analyzer-Sierra
```

**Windows:**
```
BIRDNET_RESULTS_DIR=C:/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=C:/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=C:/path/to/BirdNET-Analyzer-Sierra
```

---

## Verify Your Setup

After restarting Claude Desktop, look for the MCP tools icon (hammer) in the chat input — it should show **songsage** as a connected server. Test with:

> "List all detected bird species"

If you don't have BirdNET results yet, point your `.env` at the included sample data:

**Mac/Linux:** `BIRDNET_RESULTS_DIR=/path/to/SongSage/test_data`
**Windows:** `BIRDNET_RESULTS_DIR=C:/path/to/SongSage/test_data`

---

## Troubleshooting

### Server won't connect / shows disconnected

- All paths in the config must be **full absolute paths** (not `~` or relative)
- Fully quit and reopen Claude Desktop (not just close the window) after config changes
- Check that `command` points to the **venv python**, not the system python

### Broken venv after moving the project folder

**Mac/Linux:**
```bash
cd /path/to/SongSage
rm -rf venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```cmd
cd C:\path\to\SongSage
rmdir /s /q venv
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Then update all paths in `claude_desktop_config.json` to match the new location.

### Mac/Linux-specific

**TensorFlow fails on Apple Silicon (M1/M2/M3):**
```bash
source venv/bin/activate
pip install tensorflow-macos tensorflow-metal
```

**"xcrun: error" after macOS update:**
```bash
xcode-select --install
```

**"python3: command not found" (Linux):**
```bash
sudo apt install python3 python3-venv python3-pip
```

**TensorFlow GPU support (Linux, optional):**
```bash
source venv/bin/activate
pip install tensorflow[and-cuda]
```

### Windows-specific

**PowerShell execution policy error:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Can't activate venv:**
- Command Prompt: `venv\Scripts\activate.bat`
- PowerShell: `venv\Scripts\Activate.ps1`

**"pip: command not found" in Git Bash:**
Don't use Git Bash — use Command Prompt or PowerShell instead.

### Debug logs

| Platform | Log location |
|----------|-------------|
| Linux | `~/.config/Claude/logs/mcp-server-songsage.log` |
| macOS | `~/Library/Logs/Claude/mcp-server-songsage.log` |
| Windows | `%APPDATA%\Claude\logs\mcp-server-songsage.log` |
