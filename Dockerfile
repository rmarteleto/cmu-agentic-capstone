# Container image for hosting either transport (REST API shown; swap CMD for MCP).
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
# REST API (custom connector). For MCP instead, use:
#   CMD ["python", "-m", "sig_agent.mcp"]   # listens on :8000
CMD ["uvicorn", "sig_agent.mcp.rest_api:app", "--host", "0.0.0.0", "--port", "8080"]
