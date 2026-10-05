FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY mcp-server/requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt
COPY mcp-server /app
COPY data/raw /data/raw
ENV DATA_DIR=/data MCP_HOST=0.0.0.0 MCP_PORT=8001 DEMO_MODE=true
EXPOSE 8001
CMD ["python", "server.py"]
