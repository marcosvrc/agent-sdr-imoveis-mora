# Build a partir da RAIZ do repositório: docker build -f services/channels/whatsapp/Dockerfile .
# Uma imagem, dois handlers (inbound/outbound) — o CMD é sobrescrito por função no CDK.
FROM public.ecr.aws/lambda/python:3.12-arm64
COPY shared /opt/shared
COPY services/channels/whatsapp /opt/ch
RUN pip install --no-cache-dir "/opt/shared[aws]" "/opt/ch[aws]" && \
    cp -r /opt/ch/canal_whatsapp ${LAMBDA_TASK_ROOT}/canal_whatsapp
CMD ["canal_whatsapp.inbound.handler"]
