# ECR Public: на части VPS docker.io недоступен.
FROM public.ecr.aws/docker/library/python:3.10-slim-bookworm
WORKDIR /app
ENV DATA_DIR=/app/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY data.py main.py max_lessons.json ./
COPY max_bot ./max_bot
CMD ["python", "-u", "main.py"]
