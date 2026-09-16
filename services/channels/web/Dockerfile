# Build a partir da RAIZ do repositório: docker build -f services/channels/web/Dockerfile .
FROM public.ecr.aws/lambda/python:3.12-arm64
COPY shared /opt/shared
COPY services/channels/web /opt/ch
RUN pip install --no-cache-dir "/opt/shared[aws]" /opt/ch && \
    cp -r /opt/ch/canal_web ${LAMBDA_TASK_ROOT}/canal_web
CMD ["canal_web.inbound.handler"]
