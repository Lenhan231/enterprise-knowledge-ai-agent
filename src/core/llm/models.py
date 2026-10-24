BENCHMARK_MODELS = {
    "gpt_oss_20b": {
        "model": "openai/gpt-oss-20b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": ("GROQ_API_KEY",),
    },
    "cloudflare_llama_3_1_8b": {
        "provider": "cloudflare",
        "model": "@cf/meta/llama-3.1-8b-instruct-fp8",
        "api_key_env": ("CLOUDFLARE_API_TOKEN",),
    },
    "qwen3": {
        "model": "qwen/qwen3.8-27b",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": ("GROQ_API_KEY_2",),
    },
}
