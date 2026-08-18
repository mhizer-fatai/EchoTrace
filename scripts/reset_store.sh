#!/usr/bin/env bash
set -euo pipefail

docker compose down
rm -rf hydradb-data/store hydradb-data/cache
mkdir -p hydradb-data/store hydradb-data/cache
docker compose up -d --build
printf 'EchoTrace started with a fresh HydraDB store at http://localhost:8000\n'
