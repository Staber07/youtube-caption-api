FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose the default port (Render will override it with $PORT env variable)
EXPOSE 8000

# Start the FastAPI app with uvicorn using env var for PORT
CMD ["sh", "-c", "uvicorn main:app --host=0.0.0.0 --port=${PORT:-8000}"]
