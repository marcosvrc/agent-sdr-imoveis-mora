# Build a partir da RAIZ do repositório (o agente depende de shared/):
#   docker build -f services/agent/Dockerfile .
# No CDK: DockerImageCode.from_image_asset("..", file="services/agent/Dockerfile")
FROM public.ecr.aws/lambda/python:3.12-arm64
COPY shared /opt/shared
COPY services/agent /opt/agent
RUN pip install --no-cache-dir "/opt/shared[aws]" /opt/agent && \
    cp -r /opt/agent/src/. ${LAMBDA_TASK_ROOT}/
CMD ["agent.handler.handler"]
