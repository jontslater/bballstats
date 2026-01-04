#!/bin/bash

# NBA Betting Analytics Platform - Setup Script
# This script helps set up the development environment

set -e  # Exit on error

echo "🏀 NBA Betting Analytics Platform - Setup"
echo "=========================================="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION found"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 16+"
    exit 1
fi
NODE_VERSION=$(node --version)
echo "✅ Node.js $NODE_VERSION found"

# Check PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "⚠️  PostgreSQL not found. You'll need to install it."
else
    echo "✅ PostgreSQL found"
fi

# Check Git
if ! command -v git &> /dev/null; then
    echo "⚠️  Git not found. You'll need to install it."
else
    echo "✅ Git found"
fi

echo ""
echo "Prerequisites check complete!"
echo ""

# Create backend .env file if it doesn't exist
if [ ! -f "backend/.env" ]; then
    echo "Creating backend/.env file..."
    cat > backend/.env << EOF
# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nba_betting

# API Configuration
API_HOST=localhost
API_PORT=8000

# Logging
LOG_LEVEL=INFO

# Scraping Configuration
SCRAPE_DELAY=2
USER_AGENT=Mozilla/5.0 (compatible; NBA Analytics Bot)
EOF
    echo "✅ Created backend/.env (please update with your database credentials)"
else
    echo "✅ backend/.env already exists"
fi

# Set up backend
echo ""
echo "Setting up backend..."
cd backend

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Backend dependencies installed"

cd ..

# Set up frontend (if directory exists)
if [ -d "frontend" ]; then
    echo ""
    echo "Setting up frontend..."
    cd frontend
    
    if [ ! -d "node_modules" ]; then
        echo "Installing Node dependencies..."
        npm install
        echo "✅ Frontend dependencies installed"
    else
        echo "✅ Frontend dependencies already installed"
    fi
    
    cd ..
fi

echo ""
echo "=========================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Update backend/.env with your database credentials"
echo "2. Create the database: CREATE DATABASE nba_betting;"
echo "3. Follow the EXECUTION_PLAN.md step by step"
echo ""
echo "To activate the virtual environment:"
echo "  cd backend && source venv/bin/activate"
echo ""


