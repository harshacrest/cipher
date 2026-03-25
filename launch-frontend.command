#!/bin/bash
cd "$(dirname "$0")/frontend"

# Kill any existing process on port 1155
lsof -ti :1155 | xargs kill -9 2>/dev/null

echo "Starting frontend at http://localhost:1155"
open "http://localhost:1155" &
npm run dev
