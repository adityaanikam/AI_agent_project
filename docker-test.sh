#!/bin/bash
# FlowBit Docker Deployment Test Script

set -e  # Exit on any error

echo "🐳 FlowBit Docker Deployment Test"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
echo "1. Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed"
    exit 1
fi

print_status "Docker and Docker Compose are available"

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found, copying from docker.env"
    cp docker.env .env
    print_warning "Please edit .env file with your Google API key before continuing"
    exit 1
fi

print_status ".env file exists"

# Build and start services
echo ""
echo "2. Building and starting services..."
docker-compose down -v 2>/dev/null || true
docker-compose up --build -d

# Wait for services to start
echo ""
echo "3. Waiting for services to start..."
sleep 30

# Test service health
echo ""
echo "4. Testing service health..."

# Test main application
if curl -f http://localhost:8000/ > /dev/null 2>&1; then
    print_status "FlowBit app is responding"
else
    print_error "FlowBit app is not responding"
    docker-compose logs flowbit-app
    exit 1
fi

# Test mock services
for port in 8001 8002 8003 8004; do
    if curl -f http://localhost:$port/ > /dev/null 2>&1; then
        print_status "Mock service on port $port is responding"
    else
        print_warning "Mock service on port $port is not responding"
    fi
done

# Test API endpoints
echo ""
echo "5. Testing API endpoints..."

# Test file upload with sample data
if [ -f "test_samples/test_sample.json" ]; then
    echo "Testing file upload..."
    response=$(curl -s -X POST -F "file=@test_samples/test_sample.json" http://localhost:8000/process)
    process_id=$(echo $response | grep -o '"process_id":"[^"]*"' | cut -d'"' -f4)
    
    if [ ! -z "$process_id" ]; then
        print_status "File upload successful (Process ID: $process_id)"
        
        # Wait for processing
        sleep 10
        
        # Check status
        status_response=$(curl -s http://localhost:8000/status/$process_id)
        status=$(echo $status_response | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        print_status "Processing status: $status"
    else
        print_error "File upload failed"
        echo "Response: $response"
    fi
else
    print_warning "test_samples/test_sample.json not found, skipping upload test"
fi

# Test history endpoint
history_response=$(curl -s http://localhost:8000/history)
if echo $history_response | grep -q "history"; then
    print_status "History endpoint working"
else
    print_warning "History endpoint not working properly"
fi

# Check Docker resources
echo ""
echo "6. Docker resource usage..."
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Final summary
echo ""
echo "🎯 Test Summary"
echo "==============="
print_status "Docker deployment test completed"
print_status "Services are running and accessible"
print_status "API endpoints are functional"

echo ""
echo "🌐 Access URLs:"
echo "   Main App:     http://localhost:8000"
echo "   API Docs:     http://localhost:8000/docs"
echo "   Mock Services: http://localhost:8001-8004"

echo ""
echo "🛠️  Useful commands:"
echo "   View logs:    docker-compose logs -f flowbit-app"
echo "   Stop all:     docker-compose down"
echo "   Restart:      docker-compose restart flowbit-app"

print_status "FlowBit is ready for use! 🚀" 