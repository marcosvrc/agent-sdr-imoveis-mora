# Build a partir da RAIZ do repositório: docker build -f services/channels/telegram/Dockerfile .
# Perfil local não usa esta imagem (o worker roda com o mesmo Dockerfile.python dos demais serviços
# Python, ver local/docker-compose.yml) — esta serve o deploy aws, onde inbound vira Lambda (webhook)
# e outbound consome a fila outbound-telegram.
FROM public.ecr.aws/lambda/python:3.12-arm64
COPY shared /opt/shared
COPY services/channels/telegram /opt/ch
RUN pip install --no-cache-dir "/opt/shared[aws]" "/opt/ch[aws]" && \
    cp -r /opt/ch/canal_telegram ${LAMBDA_TASK_ROOT}/canal_telegram
CMD ["canal_telegram.inbound.handler"]
