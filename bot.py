import os
import sys

import aiohttp
from pipecat.frames.frames import EndFrame, LLMMessagesFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.openai import OpenAILLMService, OpenAILLMContext
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.vad.silero import SileroVADAnalyzer
from pipecat.serializers.twilio import TwilioFrameSerializer

from openai.types.chat import ChatCompletionToolParam

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
            "content": "You are a helpful LLM assistant in an audio call. Your name is Jane. You work for Bento ML. Your goal is to demonstrate your capabilities in a succinct way. Your output will be converted to audio so don't include special characters in your answers. Respond to what the user said in a helpful way while keeping your message as brief as possible. First greet with 'Hello, I am Jane from Bento ML, how may I help you?'",
        },
    ]

    tools = [
        ChatCompletionToolParam(
            type="function",
            function={
                "name": "get_deployment_count",
                "description": "Get the deployment count in a region of a specific status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "region": {
                            "type": "string",
                            "enum": ["north america", "europe", "asia"],
                            "description": "The region where the deployments are located.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["running", "scaled to zero", "terminated"],
                            "description": "The status of the deployment.",
                        },
                    },
                    "required": ["region", "status"],
                },
            },
        ),
    ]

    async def start_function(function_name, llm, context):
        logger.debug(f"Starting function: {function_name}")

    async def exec_function(function_name, tool_call_id, args, llm, context, result_callback):
        logger.debug(f"Executing function: {function_name}")

        await result_callback({"deployment_count": 10})

    llm.register_function(
        "get_deployment_count",
        exec_function,
        start_callback=start_function,
    )

    context = OpenAILLMContext(messages, tools)
    context_aggregator = llm.create_context_aggregator(context)
    pipeline = Pipeline(
        [
            transport.input(),  # Websocket input from client
            stt,  # Speech-To-Text
            context_aggregator.user(),  # User responses
            llm,  # LLM
            tts,  # Text-To-Speech
            transport.output(),  # Websocket output to client
            context_aggregator.assistant(),  # LLM responses
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
