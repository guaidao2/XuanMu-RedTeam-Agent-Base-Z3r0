from pydantic import BaseModel, ConfigDict, Field, model_validator

from config import AgentConfig, AgentPoolConfig, AgentRuntimeConfig


class InstanceConfigSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    agent_pool: AgentPoolConfig = Field(default_factory=AgentPoolConfig)
    agent_runtime: AgentRuntimeConfig = Field(default_factory=AgentRuntimeConfig)

    @model_validator(mode="after")
    def validate_agent_codes(self):
        for code, agent in self.agents.items():
            if agent.code != code:
                raise ValueError(f"agent code mismatch: {code}")
        return self


class UpdateAgentConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=128)
    description: str
    base_url: str
    api_key: str
    model: str
    use_responses: bool
    context_window: int = Field(ge=0)


class UpdateInstanceConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: dict[str, UpdateAgentConfigRequest]
    agent_pool: AgentPoolConfig
    agent_runtime: AgentRuntimeConfig


class UpdateInstanceConfigResponse(BaseModel):
    config: InstanceConfigSchema
    restarted: bool
