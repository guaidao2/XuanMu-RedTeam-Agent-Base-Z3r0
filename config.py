import json
import secrets
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT_PATH = Path(__file__).resolve().parent
WORKSPACE = ROOT_PATH / ".xuanmu"
CONFIG_FILE = WORKSPACE / "config.json"


# strict type config base model
class StrictConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# system config
class BootstrapAdminConfig(StrictConfigModel):
    enabled: bool = Field(default=False)
    username: str = Field(default="admin", min_length=1, max_length=64)
    email: str = Field(default="admin@xuanmu.local", min_length=1, max_length=255)
    password: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_password_when_enabled(self):
        if self.enabled and not self.password:
            raise ValueError("bootstrap admin password is required when bootstrap admin is enabled")
        return self


class SystemConfig(StrictConfigModel):
    listen_addr: str = Field(default="127.0.0.1")
    listen_port: int = Field(default=8000)
    encrypt_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32), min_length=32)
    bootstrap_admin: BootstrapAdminConfig = Field(default_factory=BootstrapAdminConfig)


# database config
class DatabaseConfig(StrictConfigModel):
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=5432)
    database: str = Field(default="z3r0")
    username: str = Field(default="")
    password: str = Field(default="")
    pool_size: int = Field(default=32)
    max_overflow: int = Field(default=32)
    pool_timeout_seconds: int = Field(default=30)
    pool_recycle_seconds: int = Field(default=1800)
    pool_pre_ping: bool = Field(default=True)


# agent config
class AgentConfig(StrictConfigModel):
    code: str = Field(default="")
    name: str = Field(default="")
    description: str = Field(default="")
    base_url: str = Field(default="")
    api_key: str = Field(default="")
    model: str = Field(default="")
    use_responses: bool = Field(default=False)
    context_window: int = Field(default=1000000, ge=0)


# per-process agent runtime pool tuning
class AgentPoolConfig(StrictConfigModel):
    max_size: int = Field(default=256, ge=1)
    ttl_seconds: int = Field(default=30 * 60, ge=0)
    sweep_interval_seconds: int = Field(default=60, ge=1)


# per-process agent run tuning
class AgentRuntimeConfig(StrictConfigModel):
    main_max_turns: int = Field(default=1000, ge=1)
    subordinate_max_turns: int = Field(default=1000, ge=1)
    model_stream_idle_timeout_seconds: int = Field(default=300, ge=30)
    context_compression_enabled: bool = True
    context_compression_trigger_ratio: float = Field(default=0.90, gt=0, lt=1)
    context_compression_hard_stop_ratio: float = Field(default=0.98, gt=0, lt=1)
    context_compression_target_ratio: float = Field(default=0.20, gt=0, lt=1)
    context_budget_model_call_ratio: float = Field(default=0.80, gt=0, lt=1)
    context_compression_preserve_recent_ratio: float = Field(default=0.25, gt=0, lt=1)
    context_compression_preserve_recent_items: int = Field(default=20, ge=1)
    context_compression_min_items: int = Field(default=12, ge=1)
    context_compression_summary_max_tokens: int = Field(default=8000, ge=512)


# global config
class GlobalConfig(StrictConfigModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    agent_pool: AgentPoolConfig = Field(default_factory=AgentPoolConfig)
    agent_runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)


###
# global config instance
###
_cfg: GlobalConfig = GlobalConfig()
_LEGACY_CONTEXT_COMPRESSION_TRIGGER_RATIO = 0.95


def load_config():
    """load config from json file"""
    global _cfg

    next_cfg = read_config_file()
    for field_name in type(_cfg).model_fields:
        setattr(_cfg, field_name, getattr(next_cfg, field_name))


def get_config():
    """get config instance"""
    global _cfg
    return _cfg


def read_config_file() -> GlobalConfig:
    """read and validate config.json without mutating global state"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data = _migrate_config_data(data)
    return GlobalConfig.model_validate(data)


def write_config_file(cfg: GlobalConfig) -> None:
    """atomically write a validated config.json"""
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = cfg.model_dump(mode="json")
    payload = json.dumps(data, ensure_ascii=False, indent=4)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=WORKSPACE,
        prefix=".config.",
        suffix=".json.tmp",
        delete=False,
    ) as f:
        temp_path = Path(f.name)
        f.write(payload)
        f.write("\n")

    temp_path.replace(CONFIG_FILE)


def _migrate_config_data(data: dict[str, Any]) -> dict[str, Any]:
    runtime = data.get("agent_runtime")
    if not isinstance(runtime, dict):
        return data
    default_runtime = AgentRuntimeConfig()
    if "context_budget_model_call_ratio" not in runtime:
        runtime["context_budget_model_call_ratio"] = default_runtime.context_budget_model_call_ratio
    if runtime.get("context_compression_trigger_ratio") == _LEGACY_CONTEXT_COMPRESSION_TRIGGER_RATIO:
        runtime["context_compression_trigger_ratio"] = default_runtime.context_compression_trigger_ratio
    return data
