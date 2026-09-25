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

    # Web search MCP Service (system.ai.web_search): busca pública com citações, via AI Gateway
    # (mesmo caminho OBO dos MCP Services do Google; escopo ai-gateway já cobre). Desligado por
    # padrão — é a única fonte EXTERNA; ligar via MCP_WEB_SEARCH_ENABLED=true.
    mcp_web_search_enabled: bool = Field(default=False, alias="MCP_WEB_SEARCH_ENABLED")
    mcp_web_search_service: str = "system.ai.web_search"

    # Agente / grafo
    agent_max_tool_iterations: int = 14
    semantic_linker_min_confidence: float = 0.6
    time_window_days: int = 3
    # Modelo do linker semântico (extração de relações em JSON). Vazio = usa o modelo da conversa;
    # um modelo mais rápido/barato (Haiku) corta latência sem perder qualidade nessa tarefa mecânica.
    linker_model: str = Field(default="", alias="LINKER_MODEL")
    # Auth das CHAMADAS DE MODELO: false = OBO (token do usuário); true = service principal do app
    # (M2M). Dados (Genie/Google) seguem SEMPRE OBO. Billing/auditoria/rate-limit passam ao SP.
    models_use_sp: bool = Field(default=False, alias="MODELS_USE_SP")

    # Observabilidade
    mlflow_experiment_path: str = ""
    log_level: str = "INFO"

    # Depuração do grafo: painel de staging + GET /api/debug/graph (só ligar em dev local).
    debug_graph: bool = Field(default=False, alias="DEBUG_GRAPH")

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

    @property
    def mcp_services(self) -> list[str]:
        """Serviços MCP a descobrir no início do turno: Google + web_search (se habilitado)."""
        svcs = list(self.google_services)
        if self.mcp_web_search_enabled:
            svcs.append(self.mcp_web_search_service)
        return svcs

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
