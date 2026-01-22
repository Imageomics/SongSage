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
      "args": ["-m", "mcp_server"],
      "cwd": "C:/Users/YOUR_USERNAME/SongSage"
    }
  }
}
```

Replace `YOUR_USERNAME` with your Windows username. Use forward slashes `/` in paths.

Restart Claude Desktop.

## Optional: Configure BirdNET Paths

If BirdNET-Analyzer-Sierra isn't auto-detected, create `.env` in the SongSage folder:

```
BIRDNET_RESULTS_DIR=C:/path/to/BirdNET-Analyzer-Sierra/results
BIRDNET_AUDIO_DIR=C:/path/to/BirdNET-Analyzer-Sierra/recordings
BIRDNET_ANALYZER_DIR=C:/path/to/BirdNET-Analyzer-Sierra
```

## Troubleshooting

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
