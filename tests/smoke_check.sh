#!/bin/bash

echo "=== SHIBLI C2 Smoke Test ==="

echo ""
echo "[1] Checking SHIBLI Core..."
curl -s http://127.0.0.1:8080/api/health || echo "SHIBLI Core not responding"

echo ""
echo "[2] Checking go2rtc..."
curl -s http://127.0.0.1:1984/api/streams || echo "go2rtc not responding"

echo ""
echo "[3] Checking Hardware Controls..."
curl -s http://127.0.0.1:8001/health || echo "Controls service not responding"

echo ""
echo "[4] Checking open ports..."
ss -ltnp | grep -E "8080|1984|8001" || echo "Required ports not active"

echo ""
echo "Smoke test completed."
