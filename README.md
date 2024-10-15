## Deployment Instruction

1. Deploy Bentos at https://github.com/bentoml/BentoXTTSStreaming and https://github.com/bentoml/BentoVLLM/tree/main/llama3.1-70b-instruct-awq
2. Deploy this Bento.
3. At deployment page of this Bento, fill in the urls of deployments from step 1. An example is `XTTS_SERVICE_URL=https://xtts-streaming-rvpg-d3767914.mt-guc1.bentoml.ai` and `OPENAI_SERVICE_URL=https://llama-3-1-zwu6-d3767914.mt-guc1.bentoml.ai/v1`. Note that `OPENAI_SERVICE_URL` should end with `/v1`.
4. Got to twilio number voice configuration page, fill in this bento's deployment url + "/voice/start_call". An example is `https://twilio-bot-k4s9-d3767914.mt-guc1.bentoml.ai/voice/start_call`.

![twilio example setup](twilio_setup.png)
