FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .[web,viz]
EXPOSE 8501
CMD ["molscope-web", "--host", "0.0.0.0", "--port", "8501"]
