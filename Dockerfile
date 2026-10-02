FROM python:3.12-slim
WORKDIR /opt/lab
COPY app ./app
COPY web ./web
COPY data ./data
COPY sources ./sources
COPY tools ./tools
COPY tests ./tests
RUN mkdir -p /opt/lab/state && chown -R 1000:1000 /opt/lab
USER 1000:1000
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 LAB_STATE_DIR=/opt/lab/state
EXPOSE 8787
CMD ["python", "app/server.py"]
