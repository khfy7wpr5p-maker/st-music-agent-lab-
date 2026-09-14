from __future__ import annotations

import os
import time
import uuid

import torch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = os.environ.get("ST_QWEN_MODEL_ID", "Qwen/Qwen3-4B")
PUBLIC_MODEL_NAME = os.environ.get("ST_QWEN_MODEL_NAME", "qwen3:4b")
API_KEY = os.environ["ST_QWEN_API_KEY"]
MAX_INPUT_TOKENS = int(os.environ.get("ST_QWEN_MAX_INPUT_TOKENS", "4096"))
MAX_OUTPUT_TOKENS = int(os.environ.get("ST_QWEN_MAX_OUTPUT_TOKENS", "1152"))

quantization = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.float16,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=quantization,
    device_map="auto",
    torch_dtype=torch.float16,
    low_cpu_mem_usage=True,
)
model.eval()

app = FastAPI()


def _authorized(request: Request) -> bool:
    return request.headers.get("authorization", "") == f"Bearer {API_KEY}"


@app.get("/health")
async def health(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    free, total = torch.cuda.mem_get_info()
    return {
        "status": "ok",
        "model": PUBLIC_MODEL_NAME,
        "quantization": "4bit-nf4",
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "gpu_free_gb": round(free / 1024**3, 2),
        "gpu_total_gb": round(total / 1024**3, 2),
    }


@app.post("/v1/chat/completions")
async def chat(request: Request):
    if not _authorized(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
        messages = body.get("messages", [])
        requested_max_tokens = int(body.get("max_tokens", MAX_OUTPUT_TOKENS))
        max_tokens = min(max(requested_max_tokens, 1), MAX_OUTPUT_TOKENS)

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=MAX_INPUT_TOKENS,
        ).to(model.device)

        torch.cuda.empty_cache()
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
                use_cache=False,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = output[:, inputs["input_ids"].shape[1] :]
        text = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()

        del output, generated, inputs
        torch.cuda.empty_cache()

        return {
            "id": "chatcmpl-" + uuid.uuid4().hex,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": PUBLIC_MODEL_NAME,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }
    except Exception as exc:
        torch.cuda.empty_cache()
        return JSONResponse(
            {"error": {"type": type(exc).__name__, "message": str(exc)}},
            status_code=500,
        )
