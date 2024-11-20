import bentoml
import json
import os
import typing as t

from pathlib import Path
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse

LANGUAGE_CODE = "en"

app = FastAPI()

@bentoml.service(
    traffic={"timeout": 30},
    resources={
        "gpu": 1,
        "gpu_type": "nvidia-tesla-t4",
    },
)
@bentoml.mount_asgi_app(app, path="/voice")
class TwilioBot:

    def __init__(self):
        import torch
        from faster_whisper import WhisperModel
        self.batch_size = 16 # reduce if low on GPU mem
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        self.whisper_model = WhisperModel("large-v3", self.device, compute_type=compute_type)

    @app.post("/start_call")
    async def start_call(self):
        service_url = os.environ.get("BENTOCLOUD_DEPLOYMENT_URL") or ""
        assert(service_url)
        if service_url.startswith("http"):
            from urllib.parse import urlparse
            service_url = urlparse(service_url).netloc
        tmpl = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
<Connect>
    <Stream url="wss://{service_url}/voice/ws"></Stream>
</Connect>
<Pause length="40"/>
</Response>
    """
        return HTMLResponse(content=tmpl.format(service_url=service_url), media_type="application/xml")

    @app.websocket("/ws")
    async def websocket_endpoint(self, websocket: WebSocket):

        from bot import run_bot
        await websocket.accept()
        start_data = websocket.iter_text()
        await start_data.__anext__()
        call_data = json.loads(await start_data.__anext__())
        stream_sid = call_data["start"]["streamSid"]
        print("WebSocket connection accepted")
        await run_bot(websocket, stream_sid, whisper_model=self.whisper_model)
