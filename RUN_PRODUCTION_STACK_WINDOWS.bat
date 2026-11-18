@echo off
setlocal
cd /d "%~dp0"
if not exist config\production.env copy config\production.example.env config\production.env >nul
docker compose --env-file config\production.env -f docker-compose.production.yml up --build
