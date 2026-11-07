set -e

git fetch origin main
git reset --hard origin/main

docker compose down
docker compose build --no-cache
docker compose up -d

docker compose logs --tail=25

