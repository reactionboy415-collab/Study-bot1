# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies for cloudscraper
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variables
ENV PORT=10000
ENV FLASK_APP=app.py

# Expose the port the app runs on
EXPOSE 10000

# Run the application using Gunicorn for production stability
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
