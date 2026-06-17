from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_CHAT_RAW_OUTPUT_DIR = "./vaults/default/raw/chats"
DEFAULT_MARKDOWN_RAW_OUTPUT_DIR = "./vaults/default/raw/notes"
DEFAULT_MINERU_MARKDOWN_OUTPUT_DIR = "./vaults/default/raw/documents/markdown"
MINERU_ADVANCED_FIELD_KEYS = {
    "backend",
    "return_md",
    "return_middle_json",
    "return_model_output",
    "return_content_list",
    "return_images",
    "response_format_zip",
    "lang_list",
    "formula_enable",
    "table_enable",
    "server_url",
    "start_page_id",
    "end_page_id",
}
DEFAULT_CHAT_SESSION_DIRS = {
    "codex": "~/.codex/sessions",
    "hermes": "~/.hermes/sessions",
    "openclaw": "~/.openclaw/agents/main/sessions",
    "claude_code": "~/.claude/projects",
}


class UiConfigResponse(BaseModel):
    config_path: str
    exists: bool
    content: str
    summary: dict[str, object] = Field(default_factory=dict)


class UiConfigUpdateRequest(BaseModel):
    config_path: str | None = None
    content: str = Field(..., min_length=1)


class UiConfigUpdateResponse(BaseModel):
    config_path: str
    saved: bool
    summary: dict[str, object] = Field(default_factory=dict)


class UiModelProviderForm(BaseModel):
    name: str
    adapter: str = "openai_compatible"
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    json_mode: bool = True
    verify_tls: bool = True
    tls_ca_file: str = ""
    context_window: int | None = None
    max_output_tokens: int | None = None
    extra_body: dict[str, object] = Field(default_factory=dict)
    api_key_configured: bool = False


class UiVaultProfileForm(BaseModel):
    id: str
    name: str
    path: str
    active: bool = False


class UiConfigDiagnosticItem(BaseModel):
    name: str
    category: str
    enabled: bool = True
    ok: bool = True
    code: str = "ok"
    path: str | None = None
    count: int | None = None
    detail: str = ""
    version: str | None = None
    source_types: list[str] = Field(default_factory=list)
    supports_checkpoint: bool | None = None
    supports_segmentation_hint: bool | None = None
    requires_external_service: bool | None = None


class UiConfigDiagnostics(BaseModel):
    connectors: list[UiConfigDiagnosticItem] = Field(default_factory=list)
    processors: list[UiConfigDiagnosticItem] = Field(default_factory=list)
    providers: list[UiConfigDiagnosticItem] = Field(default_factory=list)
    paths: list[UiConfigDiagnosticItem] = Field(default_factory=list)


class UiConfigFormResponse(BaseModel):
    project_name: str
    vault_path: str
    vault_id: str = "default"
    vaults: list[UiVaultProfileForm] = Field(default_factory=list)
    server_host: str
    server_port: int
    default_provider: str = ""
    default_max_tokens: int | None = None
    request_timeout_seconds: float
    providers: list[UiModelProviderForm] = Field(default_factory=list)
    enabled_connectors: list[str] = Field(default_factory=list)
    codex_enabled: bool = False
    codex_sessions_dir: str = ""
    codex_raw_output_dir: str = ""
    hermes_enabled: bool = False
    hermes_sessions_dir: str = ""
    hermes_raw_output_dir: str = ""
    openclaw_enabled: bool = False
    openclaw_sessions_dir: str = ""
    openclaw_raw_output_dir: str = ""
    claude_code_enabled: bool = False
    claude_code_sessions_dir: str = ""
    claude_code_raw_output_dir: str = ""
    generic_chat_enabled: bool = False
    generic_chat_roots: list[str] = Field(default_factory=list)
    generic_chat_raw_output_dir: str = ""
    markdown_enabled: bool = True
    markdown_roots: list[str] = Field(default_factory=list)
    markdown_raw_output_dir: str = ""
    mineru_enabled: bool = False
    mineru_endpoint: str = ""
    mineru_input_dir: str = ""
    mineru_output_dir: str = ""
    mineru_parse_method: str = "auto"
    mineru_backend: str = "pipeline"
    mineru_timeout_seconds: float = 600.0
    mineru_patterns: list[str] = Field(default_factory=lambda: ["*.pdf", "*.docx", "*.pptx"])
    mineru_recursive: bool = True
    mineru_return_md: bool = True
    mineru_return_middle_json: bool = False
    mineru_return_model_output: bool = False
    mineru_return_content_list: bool = False
    mineru_return_images: bool = False
    mineru_response_format_zip: bool = False
    mineru_lang_list: str = "ch"
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_server_url: str = ""
    mineru_start_page_id: int = 0
    mineru_end_page_id: int = 99999
    mineru_extra_fields_json: str = "{}"
    diagnostics: UiConfigDiagnostics = Field(default_factory=UiConfigDiagnostics)


class UiConfigFormUpdateRequest(BaseModel):
    config_path: str | None = None
    project_name: str = Field(default="My Knowledge Base", min_length=1)
    vault_path: str = Field(..., min_length=1)
    vault_id: str = "default"
    vaults: list[UiVaultProfileForm] = Field(default_factory=list)
    server_host: str = Field(default="127.0.0.1", min_length=1)
    server_port: int = Field(default=8000, ge=1, le=65535)
    default_provider: str = ""
    default_max_tokens: int | None = Field(default=12000, ge=1)
    request_timeout_seconds: float = Field(default=300.0, ge=1)
    providers: list[UiModelProviderForm] = Field(default_factory=list)
    codex_enabled: bool = False
    codex_sessions_dir: str = ""
    codex_raw_output_dir: str = ""
    hermes_enabled: bool = False
    hermes_sessions_dir: str = ""
    hermes_raw_output_dir: str = ""
    openclaw_enabled: bool = False
    openclaw_sessions_dir: str = ""
    openclaw_raw_output_dir: str = ""
    claude_code_enabled: bool = False
    claude_code_sessions_dir: str = ""
    claude_code_raw_output_dir: str = ""
    generic_chat_enabled: bool = False
    generic_chat_roots: list[str] = Field(default_factory=list)
    generic_chat_raw_output_dir: str = ""
    markdown_enabled: bool = True
    markdown_roots: list[str] = Field(default_factory=list)
    markdown_raw_output_dir: str = ""
    mineru_enabled: bool = False
    mineru_endpoint: str = ""
    mineru_input_dir: str = ""
    mineru_output_dir: str = ""
    mineru_parse_method: str = "auto"
    mineru_backend: str = "pipeline"
    mineru_timeout_seconds: float = Field(default=600.0, ge=1)
    mineru_patterns: list[str] = Field(default_factory=lambda: ["*.pdf", "*.docx", "*.pptx"])
    mineru_recursive: bool = True
    mineru_return_md: bool = True
    mineru_return_middle_json: bool = False
    mineru_return_model_output: bool = False
    mineru_return_content_list: bool = False
    mineru_return_images: bool = False
    mineru_response_format_zip: bool = False
    mineru_lang_list: str = "ch"
    mineru_formula_enable: bool = True
    mineru_table_enable: bool = True
    mineru_server_url: str = ""
    mineru_start_page_id: int = Field(default=0, ge=0)
    mineru_end_page_id: int = Field(default=99999, ge=0)
    mineru_extra_fields_json: str = "{}"
