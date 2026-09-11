"""Configuração do Porto Insights, carregada de variáveis de ambiente.

Sem segredos aqui: a autenticação é OBO (token do usuário) em produção e, em dev local,
o profile do CLI. Ver .env.example para a lista completa.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelEndpoint(BaseSettings):
    name: str
    label: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Workspace
    databricks_host: str = Field(default="fevm-pzanela-classic-aws.cloud.databricks.com")
    databricks_config_profile: str = Field(default="fevm-pzanela-classic-aws")

    # Porta do app (Databricks Apps injeta DATABRICKS_APP_PORT)
    port: int = Field(default=8000, alias="DATABRICKS_APP_PORT")

    # Dados
    porto_catalog: str = "pzanela_classic_aws_catalog"
    porto_schema: str = "porto_insights"
    sql_warehouse_id: str = "848374d85d2bad86"

    # Lakebase (histórico de chat persistente). Vazio = usa store em memória.
    lakebase_endpoint: str = "projects/porto-insights/branches/production/endpoints/primary"
    lakebase_database: str = "databricks_postgres"

    # Modelos (allowlist "nome:Rótulo,nome:Rótulo")
    model_endpoints: str = ""
    default_model_endpoint: str = ""

    # Genie One MCP
    genie_poll_initial_ms: int = 1500
    genie_poll_max_ms: int = 5000
    genie_max_wait_s: int = 260
    genie_max_rows_to_llm: int = 50

    # Google MCP Services
    mcp_google_services: str = "system.ai.gmail,system.ai.google_calendar,system.ai.google_drive"
    mcp_tool_allowlist_extra: str = ""
    mcp_tool_denylist_extra: str = ""

    # Agente / grafo
    agent_max_tool_iterations: int = 8
    semantic_linker_min_confidence: float = 0.6
    time_window_days: int = 3

    # Observabilidade
    mlflow_experiment_path: str = ""
    log_level: str = "INFO"

    @field_validator("databricks_host")
    @classmethod
    def _strip_host(cls, v: str) -> str:
        return v.replace("https://", "").replace("http://", "").rstrip("/")

    @property
    def host_url(self) -> str:
        return f"https://{self.databricks_host}"

    @property
    def genie_mcp_url(self) -> str:
        return f"{self.host_url}/api/2.0/mcp/genie"

    @property
    def serving_base_url(self) -> str:
        return f"{self.host_url}/serving-endpoints"

    @property
    def google_services(self) -> list[str]:
        return [s.strip() for s in self.mcp_google_services.split(",") if s.strip()]

    def mcp_service_url(self, service: str) -> str:
        return f"{self.host_url}/ai-gateway/mcp-services/{service}"

    @property
    def endpoints(self) -> list[ModelEndpoint]:
        out: list[ModelEndpoint] = []
        for chunk in self.model_endpoints.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            name, _, label = chunk.partition(":")
            out.append(ModelEndpoint(name=name.strip(), label=(label.strip() or name.strip())))
        return out

    @property
    def default_endpoint(self) -> str:
        return self.default_model_endpoint or (self.endpoints[0].name if self.endpoints else "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
