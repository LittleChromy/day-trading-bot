#!/bin/bash

# View logs
echo "📋 Day Trading Bot Logs"
echo "========================"
echo ""
echo "Showing backend logs (Ctrl+C to exit):"
echo ""
docker-compose logs -f backend
