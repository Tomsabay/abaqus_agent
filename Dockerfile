FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e ".[mcp]"

EXPOSE 8000 8001

CMD ["python", "server.py"]
