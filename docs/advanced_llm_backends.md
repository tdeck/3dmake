# LLM Backend Setup

3DMake can describe your models using a vision-capable LLM. Three backend types are supported:

| Backend                      | Config key           | Best for                   |
| ---------------------------- | -------------------- | -------------------------- |
| Any OpenAI-compatible server | `openai_compat_host` | Local / self-hosted models |
| OpenRouter                   | `openrouter_key`     | Cloud models, pay-per-use  |
| Google Gemini                | `gemini_key`         | Gemini models directly     |

**Priority order:** `openai_compat_host` → `openrouter_key` → `gemini_key`. The first one that is set wins.

All settings below go in your global `defaults.toml` or your project's `3dmake.toml`.

---

## OpenAI-Compatible Local Servers (`openai_compat_host`)

Set `openai_compat_host` to the bare URL of your server. 3DMake appends `/v1` automatically. Also set `llm_name` to a vision-capable model available on that server.

```toml
openai_compat_host = "http://localhost:11434"   # example for Ollama
llm_name = "llava"
```

The sections below show the exact URL and a recommended model for each server.

---

### Ollama

**Install:** https://ollama.com

```bash
# Pull a vision-capable model
ollama pull llava

# Or for better quality
ollama pull llama3.2-vision
```

Ollama starts automatically on login. Confirm it is running:

```bash
ollama list          # shows downloaded models
curl http://localhost:11434   # should return "Ollama is running"
```

**3dmake.toml / defaults.toml:**

```toml
openai_compat_host = "http://localhost:11434"
llm_name = "llava"
```

> **Remote Ollama:** If Ollama is on another machine, replace `localhost` with that machine's IP and make sure port 11434 is reachable. Set `OLLAMA_HOST=0.0.0.0` on the server to bind to all interfaces.

---

### LM Studio

**Install:** https://lmstudio.ai

1. Open LM Studio and download a vision model from the **Discover** tab (search for `llava` or `moondream`).
2. Go to **Local Server** (the `<->` icon in the left sidebar).
3. Select your model from the dropdown and click **Start Server**.

The default port is `1234`. Confirm it is running by visiting http://localhost:1234 in your browser.

**3dmake.toml / defaults.toml:**

```toml
openai_compat_host = "http://localhost:1234"
llm_name = "llava-v1.6-mistral-7b"   # match the exact model name shown in LM Studio
```

> **Model name:** LM Studio shows the full model identifier in the server panel. Copy it exactly into `llm_name`.

---

### llama.cpp (`llama-server`)

**Install:** https://github.com/ggerganov/llama.cpp

Build with server support and start with a GGUF vision model:

```bash
# Build (one-time)
cmake -B build -DLLAMA_SERVER=ON
cmake --build build --config Release -j

# Download a vision GGUF, e.g. LLaVA 1.6
# (find GGUFs at https://huggingface.co/mys/ggml_llava-v1.5-7b)

# Start the server
./build/bin/llama-server \
    --model ./models/llava-v1.6-mistral-7b.Q4_K_M.gguf \
    --mmproj ./models/mmproj-mistral7b-f16.gguf \
    --host 127.0.0.1 \
    --port 8080
```

**3dmake.toml / defaults.toml:**

```toml
openai_compat_host = "http://localhost:8080"
llm_name = "llava-v1.6-mistral-7b"   # can be any string; llama-server ignores it
```

> **Multimodal projection:** Vision models in llama.cpp require a separate `--mmproj` file. Both the model GGUF and the mmproj GGUF must be downloaded; check the model card on Hugging Face for the correct pair.

---

### ramalama

**Install:** https://github.com/containers/ramalama

ramalama runs models inside a container and exposes an OpenAI-compatible endpoint.

```bash
# Pull and serve a vision model
ramalama serve llama3.2-vision --port 8080
```

**3dmake.toml / defaults.toml:**

```toml
openai_compat_host = "http://localhost:8080"
llm_name = "llama3.2-vision"
```

> ramalama model names follow the same convention as Ollama. Check `ramalama list` for what is available locally.

---

### Jan

**Install:** https://jan.ai

1. Open Jan, go to **Hub** and download a vision model.
2. Go to **Local API Server** in settings and start the server (default port `1337`).

**3dmake.toml / defaults.toml:**

```toml
openai_compat_host = "http://localhost:1337"
llm_name = "llava-v1.5-7b"   # match the model ID shown in Jan
```

---

### Any Other OpenAI-Compatible Server

If your server exposes `/v1/chat/completions` (the standard OpenAI API shape), it will work:

```toml
openai_compat_host = "http://<host>:<port>"
llm_name = "<model-name-as-your-server-expects-it>"
```

---

## OpenRouter (`openrouter_key`)

OpenRouter is a cloud API aggregator that gives access to hundreds of models — including GPT-4o, Claude, Gemini, and open-source options — under a single API key and pay-per-use billing.

**Sign up:** https://openrouter.ai

1. Create an account and add credits.
2. Copy your API key from https://openrouter.ai/keys.

**3dmake.toml / defaults.toml:**

```toml
openrouter_key = "sk-or-v1-..."
llm_name = "google/gemini-2.5-pro-preview"   # default; see model list below
```

The `llm_name` value must be an OpenRouter model slug. Vision-capable models that work well for mesh description:

| Model                    | Slug                                       |
| ------------------------ | ------------------------------------------ |
| Gemini 2.5 Pro (default) | `google/gemini-2.5-pro-preview`            |
| GPT-4o                   | `openai/gpt-4o`                            |
| Claude Sonnet 3.7        | `anthropic/claude-sonnet-4-5`              |
| Llama 3.2 Vision 90B     | `meta-llama/llama-3.2-90b-vision-instruct` |
| Qwen2.5 VL 72B           | `qwen/qwen2.5-vl-72b-instruct`             |

Browse the full list at https://openrouter.ai/models — filter by **Vision** capability.

> **Cost:** The default Gemini 2.5 Pro model costs roughly $0.002–0.004 per `info` run at the default image settings. Smaller models like Llama 3.2 Vision are cheaper.

---

## Google Gemini (`gemini_key`)

Use this if you have a Google AI Studio key and prefer to call Gemini directly rather than through OpenRouter.

**Get a key:** https://aistudio.google.com/app/apikey

**3dmake.toml / defaults.toml:**

```toml
gemini_key = "AIza..."
llm_name = "gemini-2.5-pro-preview"   # bare model name, no provider prefix
```

> Note that Gemini model names here do **not** use the `google/` prefix that OpenRouter requires.

---

## Troubleshooting

**`Connection refused` / `Failed to connect`**
The server is not running or is on a different port. Check the server's own UI or logs, then verify the URL with `curl http://<host>:<port>/v1/models`.

**`Model not found` / 404 on completions**
The value of `llm_name` does not match what the server expects. For local servers, run `ollama list`, `ramalama list`, or check the server UI for the exact model identifier.

**Blank or garbled description**
The model may not support vision input. Confirm the model is multimodal — text-only models will either error or return nonsense when given image data.

**OpenRouter: `402 Payment Required`**
Your OpenRouter account has no credits. Add funds at https://openrouter.ai/credits.

**Gemini: `403 PERMISSION_DENIED`**
The API key is invalid or the model name uses the wrong format (remember: no `google/` prefix for direct Gemini keys).
