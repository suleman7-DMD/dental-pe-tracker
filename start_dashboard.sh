#!/bin/bash
cd ~/dental-pe-tracker
echo "Starting Dental PE Consolidation Intelligence Dashboard..."
echo "Open http://localhost:8501 in your browser"
streamlit run dashboard/app.py --server.port 8501 --server.headless false
