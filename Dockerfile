FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e ".[mcp]"

# The server binds loopback by default and owns that decision: it has no
# authentication and can launch solver jobs, so a dev checkout must never be
# reachable from the LAN. Inside a container loopback means "unreachable" —
# a published port maps to the container's external interface, so
# `docker run -p 8000:8000` handed you a port that accepted nothing.
#
# The container boundary is the isolation here. Publish the port only where
# you want it: `-p 127.0.0.1:8000:8000` keeps it on your own machine.
ENV ABAQUS_AGENT_HOST=0.0.0.0

EXPOSE 8000 8001

# Report health from the app's own probe, so `docker ps` stops saying healthy
# for a process that cannot answer.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u,sys; sys.exit(0 if u.urlopen('http://127.0.0.1:8000/health',timeout=5).status==200 else 1)"

CMD ["python", "server.py"]
