# Package the morning note so it runs the same on a laptop, in CI or in Kubernetes.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY sleep_slo.py config.json ./
COPY knowledge/ knowledge/
COPY data/sample_sleep.csv data/
COPY evals/ evals/
RUN python evals/run_evals.py          # the image will not build if the evaluation gate fails
RUN useradd -u 10001 app && mkdir -p /app/out && chown app /app/out
USER 10001
ENV SLEEP_OUT=/app/out
CMD ["python", "sleep_slo.py"]
