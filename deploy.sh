#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "========================================"
echo "  CYBER-TRIAGE - DEPLOY"
echo "========================================"
echo ""

if [ ! -f ".env" ]; then
    echo -e "${RED}[ERROR] .env no encontrado${NC}"
    exit 1
fi

source .env

if [ -z "$GEMINI_API_KEY" ] || [ "$GEMINI_API_KEY" == "your-gemini-api-key-here" ]; then
    echo -e "${RED}[ERROR] GEMINI_API_KEY no configurada${NC}"
    exit 1
fi

if [ -z "$CYBERHAVEN_API_KEY" ] || [ "$CYBERHAVEN_API_KEY" == "your-cyberhaven-refresh-token" ]; then
    echo -e "${RED}[ERROR] CYBERHAVEN_API_KEY no configurada${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] Variables de entorno configuradas${NC}"

mkdir -p data/incidents logs prompts

if [ "$(docker ps -q -f name=cyber-triage)" ]; then
    echo "Deteniendo contenedor anterior..."
    docker stop cyber-triage
fi

if [ "$(docker ps -aq -f name=cyber-triage)" ]; then
    docker rm cyber-triage
fi

echo "Construyendo imagen..."
docker build -t cyber-triage:latest .

echo "Iniciando contenedor..."
docker-compose up -d

sleep 5

if [ "$(docker ps -q -f name=cyber-triage)" ]; then
    echo ""
    echo -e "${GREEN}========================================"
    echo "  DEPLOY COMPLETADO"
    echo "========================================${NC}"
    echo ""
    echo "Comandos útiles:"
    echo "  docker logs -f cyber-triage      # Ver logs en vivo"
    echo "  docker exec -it cyber-triage python3 scheduler.py --once  # Ciclo manual"
    echo "  docker stop cyber-triage         # Detener"
    echo "  docker restart cyber-triage      # Reiniciar"
    echo ""
else
    echo -e "${RED}[ERROR] Container no está corriendo${NC}"
    docker logs cyber-triage
    exit 1
fi