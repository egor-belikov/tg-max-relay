FROM public.ecr.aws/docker/library/python:3.10-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
CMD ["python", "-u", "main.py"]
