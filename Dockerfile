FROM python:3.10-slim

WORKDIR /app

# Ensure Python output is logged immediately
ENV PYTHONUNBUFFERED=1

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose port 10000 for Render Health Checks
EXPOSE 10000

# Execute application
CMD ["python", "bot.py"]
