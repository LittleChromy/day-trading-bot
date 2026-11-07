FROM python:3.11-slim

WORKDIR /app

# alpaca-trade-api pins msgpack==1.0.3, which has no wheel for Python 3.11 and
# must be compiled; psycopg2-binary and the rest install from wheels.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Set INSTALL_ML=true to add TensorFlow for the neural-network model (~600MB)
ARG INSTALL_ML=false
RUN if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

COPY . .

EXPOSE 5000

# One worker so exactly one scheduler/bot runs; threads handle concurrent API requests.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "app:create_app()"]
