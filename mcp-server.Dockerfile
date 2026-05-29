FROM python:3.12-slim

RUN pip install --no-cache-dir fastmcp httpx

COPY mcp_server/server.py /app/server.py

CMD ["fastmcp", "run", "/app/server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
