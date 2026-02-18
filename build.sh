#!/usr/bin/env bash
set -o errexit

# Install system dependencies for WeasyPrint (PDF generation)
apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
