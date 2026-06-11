#!/bin/bash
# Double-click this file on Mac to start the Brand Generator
cd "$(dirname "$0")"
echo "Installing dependencies..."
pip3 install flask pillow --quiet --break-system-packages 2>/dev/null || pip install flask pillow --quiet
echo ""
echo "Starting Brand Generator..."
echo "Opening http://localhost:5000 in your browser..."
sleep 1
open http://localhost:5000
python3 app.py
