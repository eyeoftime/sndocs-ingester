FROM python:3.12-slim

RUN pip install --no-cache-dir fastmcp httpx uvicorn

COPY mcp_server/server.py /app/server.py

CMD ["python", "/app/server.py"]
