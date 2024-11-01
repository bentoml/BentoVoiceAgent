import os
import sys

import aiohttp
from pipecat.frames.frames import EndFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_response import (
    LLMAssistantResponseAggregator,
    LLMUserResponseAggregator,
)
from pipecat.services.cartesia import CartesiaTTSService
from pipecat.services.openai import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.serializers.twilio import TwilioFrameSerializer

from loguru import logger

from whisper_bento import BentoWhisperSTTService
from simple_xtts import SimpleXTTSService

logger.remove(0)
logger.add(sys.stderr, level="DEBUG")


async def run_bot(websocket_client, stream_sid, whisper_model):
    transport = FastAPIWebsocketTransport(
        websocket=websocket_client,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
            vad_audio_passthrough=True,
            serializer=TwilioFrameSerializer(stream_sid),
        ),
    )

    openai_base_url = os.getenv("OPENAI_SERVICE_URL")
    assert openai_base_url
    llm = OpenAILLMService(
        base_url=openai_base_url,
        api_key="n/a",
        model="hugging-quants/Meta-Llama-3.1-70B-Instruct-AWQ-INT4",
    )

    stt = BentoWhisperSTTService(model=whisper_model)

    xtts_base_url = os.getenv("XTTS_SERVICE_URL")
    assert xtts_base_url
    client = aiohttp.ClientSession()
    tts = SimpleXTTSService(
        base_url=xtts_base_url,
        language="en",
        aiohttp_session=client,
    )

    messages = [
        {
            "role": "system",
            "content": "You are a helpful LLM assistant in an audio call. Your name is Jane. You work for Bento-ML. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a helpful way while keeping your message as brief as possible. First greet with 'Hello, I am Jane from Bento-ML, how may I help you?'",
        },
    ]

    tma_in = LLMUserResponseAggregator(messages)
    tma_out = LLMAssistantResponseAggregator(messages)

    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            tma_in,  # User responses
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            tma_out,  # LLM responses
        ]
    )

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # Kick off the conversation.
        messages.append({"role": "system", "content": "Please introduce yourself to the user."})
        await task.queue_frames([LLMMessagesFrame(messages)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        await task.queue_frames([EndFrame()])

    runner = PipelineRunner(handle_sigint=False)

    await runner.run(task)
