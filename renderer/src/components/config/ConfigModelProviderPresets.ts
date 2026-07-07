import type { ConfigFormProvider, ConfigImageProvider } from "../../api/client";

export const PROVIDER_PRESETS: ConfigFormProvider[] = [
  {
    name: "vllm",
    adapter: "openai_compatible",
    base_url: "http://localhost:8001/v1",
    api_key: "",
    model: "local-model",
    json_mode: true,
    tls_ca_file: "",
    context_window: 32768,
    max_output_tokens: 8000,
  },
  {
    name: "ollama",
    adapter: "ollama",
    base_url: "http://localhost:11434",
    api_key: "",
    model: "qwen3.6:27b-q4_K_M",
    json_mode: true,
    tls_ca_file: "",
    context_window: 262144,
    max_output_tokens: 8000,
    extra_body: { think: false },
  },
];

export const IMAGE_PROVIDER_PRESETS: ConfigImageProvider[] = [
  {
    name: "sensenova",
    adapter: "sensenova_image",
    base_url: "https://token.sensenova.cn/v1",
    endpoint_path: "/images/generations",
    api_key: "",
    model: "sensenova-u1-fast",
    tls_ca_file: "",
    resolution: "2720*1536",
    num_inference_steps: 20,
    guidance: 4,
    extra_body: {},
  },
];
