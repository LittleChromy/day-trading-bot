#!/bin/bash

# Day Trading Bot Quick Start Script

echo "🚀 Day Trading Bot - Quick Start"
echo "================================"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

echo "✅ Docker found"

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your Alpaca API keys:"
    echo "   ALPACA_API_KEY=your_key_here"
    echo "   ALPACA_SECRET_KEY=your_secret_here"
    echo ""
    echo "Open .env in your editor and update the credentials."
    echo "Then run this script again."
    exit 1
fi

echo "✅ .env file found"

# Check if API keys are set
if grep -q "your_api_key_here" .env; then
    echo "❌ API keys not configured in .env file"
    echo "Please add your Alpaca API credentials to .env"
    exit 1
fi

echo "✅ API keys configured"
echo ""
echo "🐳 Starting Docker containers..."
echo "This may take a few minutes on first run..."
echo ""

# Start Docker containers
docker-compose up -d

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All services started successfully!"
    echo ""
    echo "📊 Dashboard: http://localhost:3000"
    echo "🔌 API: http://localhost:5000/api"
    echo "🗄️  Database: postgres://trading_user:trading_password@localhost:5432/day_trading_bot"
    echo ""
    echo "📝 Useful commands:"
    echo "   docker-compose logs -f backend    # View backend logs"
    echo "   docker-compose logs -f frontend   # View frontend logs"
    echo "   docker-compose ps                 # Show service status"
    echo "   docker-compose down               # Stop all services"
    echo ""
    echo "🎉 Ready to trade! Open http://localhost:3000 in your browser."
else
    echo "❌ Failed to start services. Check Docker and try again."
    exit 1
fi
