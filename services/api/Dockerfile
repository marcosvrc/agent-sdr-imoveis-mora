# Build a partir da RAIZ do repositório: docker build -f services/api/Dockerfile .
FROM public.ecr.aws/lambda/python:3.12-arm64
COPY shared /opt/shared
COPY services/api /opt/api
RUN pip install --no-cache-dir "/opt/shared[aws]" "/opt/api[aws]" && \
    cp -r /opt/api/src/. ${LAMBDA_TASK_ROOT}/
CMD ["api.main.handler"]
