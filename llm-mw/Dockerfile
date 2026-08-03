FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code and modules
COPY main.py .
COPY config.py .
COPY api/ ./api/
COPY core/ ./core/
COPY utils/ ./utils/
COPY services/ ./services/
COPY models/ ./models/
COPY dashboard/ ./dashboard/
COPY data/ ./data/

# Copy data files (fallback if not in data/)
COPY prices.json .
COPY users.json .

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run with uvicorn
#
# Deliberately WITHOUT --proxy-headers. It reads X-Forwarded-For, but nginx builds that
# header with $proxy_add_x_forwarded_for, which APPENDS to whatever the caller sent —
# so its first element is the caller's own claim, and uvicorn takes the first element.
# Measured: `curl -H "X-Forwarded-For: 203.0.113.55"` through nginx was recorded verbatim.
# The caller's address is instead read from X-Real-IP, which nginx sets with
# `$remote_addr` (overwrite, not append) in all 12 proxy blocks — see utils/client_ip.py.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "4"]
