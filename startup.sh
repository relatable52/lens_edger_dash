curl -LsSf https://astral.sh/uv/install.sh | sh

uv sync

./.venv/Scripts/activate

gunicorn --workers 4 --threads 2 --worker-class gthread --timeout 1000 -b 0.0.0.0:8050 main:server