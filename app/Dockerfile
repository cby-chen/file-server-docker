FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["gunicorn","-w","2","-b","0.0.0.0:5000","--timeout","3600","app:app"]
