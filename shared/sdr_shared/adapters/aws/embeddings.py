import json
import boto3
from ...config import get_settings


class BedrockEmbedder:
    dimensoes = 1024

    def __init__(self):
        s = get_settings(); self._model = s.model_embedding
        self._c = boto3.client("bedrock-runtime", region_name=s.aws_region)

    def embed(self, texto: str) -> list[float]:
        r = self._c.invoke_model(modelId=self._model, body=json.dumps({"inputText": texto, "dimensions": 1024, "normalize": True}))
        return json.loads(r["body"].read())["embedding"]
