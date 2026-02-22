FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY fast_api_crudo/ fast_api_crudo/

RUN pip install --no-cache-dir -e .
RUN pip install --no-cache-dir uvicorn[standard] psycopg2-binary

COPY example_app.py .

EXPOSE 8001

CMD ["uvicorn", "example_app:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
