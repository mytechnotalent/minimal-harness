FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN python -m compileall -q meta_harness
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
