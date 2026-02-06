#!/bin/bash
# Build frontend and copy to API static directory for production serving

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$SCRIPT_DIR"
STATIC_DIR="$SCRIPT_DIR/../api/static"

echo "Building frontend..."
cd "$WEB_DIR"
npm install
npm run build

echo "Copying to API static directory..."
rm -rf "$STATIC_DIR"/*
cp -r dist/* "$STATIC_DIR/"

echo "Build complete! Static files copied to $STATIC_DIR"
