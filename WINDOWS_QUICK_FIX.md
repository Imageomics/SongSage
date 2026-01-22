# Windows Quick Fix

## The Error
```
./setup.sh: line 46: pip: command not found
ERROR: Failed to install package
```

## Why It Happens
The `setup.sh` script is for Linux/Mac. It won't work in Git Bash on Windows.

## Solution

Don't use Git Bash. Use Command Prompt or PowerShell instead:

```cmd
cd %USERPROFILE%\Downloads\birdnet-sierra-mcp
venv\Scripts\activate
pip install -r requirements.txt
mkdir heatmaps
```

That's it. See [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md) for complete setup.
