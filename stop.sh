#!/bin/bash

# Stop and remove containers
echo "🛑 Stopping Day Trading Bot..."
docker-compose down

echo "✅ Services stopped"
echo ""
echo "To restart, run: ./start.sh"
