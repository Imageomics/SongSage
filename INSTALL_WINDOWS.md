# Windows Installation

## Prerequisites

1. **Python 3.10+** from [python.org](https://www.python.org/downloads/)
   - Check "Add Python to PATH" during installation
2. **BirdNET-Analyzer-Sierra** - Must be installed and accessible on your system
3. **Claude Desktop** from [claude.ai/download]

## Installation Steps

1. Clone the repository:

```cmd
git clone https://github.com/Imageomics/SongSage.git
cd SongSage
```

2. Set up the environment:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
mkdir heatmaps
```

## Configure Claude Desktop

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

Replace `YOUR_USERNAME` with your Windows username. Use forward slashes `/` in paths.

> **Important:** All three paths must be **full absolute paths**. Run `cd` inside the SongSage folder to see the exact path.

Restart Claude Desktop.

## Optional: Configure BirdNET Paths

If BirdNET-Analyzer-Sierra isn't auto-detected, create `.env` in the SongSage folder:

```
BIRDNET_RESULTS_DIR=C:/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=C:/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=C:/path/to/BirdNET-Analyzer-Sierra
```

## Verify Your Setup

After restarting Claude Desktop, look for the MCP tools icon (hammer) in the chat input. Type one of these to confirm the connection:

> "List all detected bird species"

If you don't have BirdNET results yet, point your `.env` at the included sample data:

```
BIRDNET_RESULTS_DIR=C:/Users/YOUR_USERNAME/SongSage/test_data
```

## Troubleshooting

**Server won't connect / shows disconnected**
- Make sure all paths in the config are **full absolute paths** with forward slashes `/`
- Fully quit and reopen Claude Desktop after config changes
- Check logs: `%APPDATA%\Claude\logs\mcp-server-songsage.log`

**Broken venv after moving the project folder**
```cmd
cd C:\Users\YOUR_USERNAME\SongSage
rmdir /s /q venv
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**"python: command not found"**
- Reinstall Python, check "Add Python to PATH"

**PowerShell execution policy error**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Can't activate venv**
- Command Prompt: `venv\Scripts\activate.bat`
- PowerShell: `venv\Scripts\Activate.ps1`

**"pip: command not found" in Git Bash**
- Don't use Git Bash - use Command Prompt or PowerShell
