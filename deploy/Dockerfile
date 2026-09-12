FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# We only need the API dependencies for this container
RUN pip install --no-cache-dir fastapi==0.110.0 uvicorn[standard]==0.29.0 SQLAlchemy==2.0.29 psycopg2-binary==2.9.9 python-dotenv==1.0.1 pydantic==2.6.4

COPY ./api /app/api

EXPOSE 8001

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
