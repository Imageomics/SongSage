#!/bin/bash

# SongSage Setup Script

echo "========================================="
echo "SongSage Setup"
echo "========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.10 or higher"
    exit 1
fi

echo "[1/5] Python found:"
python3 --version
echo ""

# Create virtual environment
echo "[2/5] Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to create virtual environment"
        exit 1
    fi
    echo "Virtual environment created successfully."
fi
echo ""

# Activate virtual environment and install dependencies
echo "[3/5] Installing dependencies..."
source venv/bin/activate
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to activate virtual environment"
    exit 1
fi

python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
echo "Dependencies installed successfully."
echo ""

# Create heatmaps directory
echo "[4/5] Creating directories..."
mkdir -p heatmaps
echo "Directories created."
echo ""

# Verify installation
echo "[5/5] Verifying installation..."
python -c "import mcp; print('✓ MCP package installed successfully')"
echo ""

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. (Optional) Copy .env.example to .env and configure your paths"
echo "2. Update Claude Desktop config at:"
echo "   Linux: ~/.config/Claude/claude_desktop_config.json"
echo "   macOS: ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "3. Add this server configuration:"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "songsage": {'
echo "      \"command\": \"$(pwd)/venv/bin/python\","
echo "      \"args\": [\"-m\", \"mcp_server\"],"
echo "      \"cwd\": \"$(pwd)\""
echo '    }'
echo '  }'
echo '}'
echo ""
echo "4. Restart Claude Desktop"
echo ""