FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose port (Railway will set the PORT environment variable)
EXPOSE 8000

# Start the application (Railway sets PORT automatically)
CMD gunicorn app:app --host 0.0.0.0 --port $PORT