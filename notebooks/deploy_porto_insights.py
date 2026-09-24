# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy do Porto Insights
# MAGIC
# MAGIC Notebook **autocontido** para publicar o Porto Insights no **seu próprio workspace**, sem
# MAGIC CLI local e sem Asset Bundle. Ele usa apenas a REST API do Databricks (autenticado pelo
# MAGIC token do próprio notebook) e faz, de ponta a ponta:
# MAGIC
# MAGIC 1. Cria (ou reutiliza) o projeto **Lakebase** que guarda o histórico de conversas.
# MAGIC 2. Publica o código do app (backend FastAPI + frontend já buildado) no seu Workspace.
# MAGIC 3. Cria/atualiza o **Databricks App** com os *resources* (warehouse + Lakebase) e os
# MAGIC    **escopos OBO** corretos (`genie`, `model-serving`, `ai-gateway`, `catalog.tables:read`).
# MAGIC 4. Faz o *deployment*, sobe o compute e roda um *smoke-test* das rotas.
# MAGIC
# MAGIC ## Pré-requisitos
# MAGIC - Importar **a pasta inteira do repositório** no Workspace (Git folder ou import de ZIP),
# MAGIC   com este notebook em `notebooks/` — o `frontend/dist/` já vem buildado no repo.
# MAGIC - Ter pelo menos **um Genie Space** acessível ao usuário (o app usa Genie One, que descobre
# MAGIC   os spaces automaticamente — não precisa de ID).
# MAGIC - Os conectores **Google Workspace** (`system.ai.gmail`/`google_calendar`/`google_drive`) e a
# MAGIC   **busca na web** (`system.ai.web_search`) são serviços built-in: o consentimento OAuth é
# MAGIC   feito por usuário, dentro do app, na primeira vez que cada conta é usada.
# MAGIC - Um **SQL Warehouse** (deixe o widget em branco para selecionar um automaticamente).

# COMMAND ----------

# DBTITLE 1,Configuração (widgets)
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    dbutils  # type: ignore[name-defined]
except NameError:  # permite checagem de sintaxe fora do Databricks
    dbutils = None  # type: ignore[assignment]


DEFAULTS = {
    "app_name": "porto-insights",
    "warehouse_id": "",
    "porto_catalog": "main",
    "porto_schema": "porto_insights",
    "model_endpoints": (
        "databricks-claude-sonnet-5:Claude Sonnet 5,"
        "databricks-claude-opus-5:Claude Opus 5,"
        "databricks-gpt-5-5:GPT-5.5"
    ),
    "default_model_endpoint": "databricks-claude-sonnet-5",
    "lakebase_project_id": "porto-insights",
    "lakebase_min_cu": "0.5",
    "lakebase_max_cu": "1.0",
    "lakebase_scale_to_zero_seconds": "300",
    "enable_web_search": "false",  # system.ai.web_search só existe em AWS/GCP (não Azure)
    "mlflow_experiment_path": "",  # vazio = tracing desligado; informe um experimento p/ ligar
    "run_app": "true",
    "smoke_test": "true",
}

WIDGET_LABELS = {
    "app_name": "Nome do Databricks App",
    "warehouse_id": "SQL warehouse ID (em branco = seleção automática)",
    "porto_catalog": "Catálogo UC dos dados (rótulos de data asset)",
    "porto_schema": "Schema UC dos dados",
    "model_endpoints": "Endpoints de modelo (nome:Rótulo, separados por vírgula)",
    "default_model_endpoint": "Endpoint de modelo padrão",
    "lakebase_project_id": "ID do projeto Lakebase (histórico de chat)",
    "lakebase_min_cu": "Lakebase — compute mínimo (CU)",
    "lakebase_max_cu": "Lakebase — compute máximo (CU)",
    "lakebase_scale_to_zero_seconds": "Lakebase — segundos ociosos até escalar a zero",
    "enable_web_search": "Habilitar busca na web (só AWS/GCP; indisponível na Azure)",
    "mlflow_experiment_path": "MLflow: caminho do experimento p/ traces (vazio = desligado)",
    "run_app": "Iniciar o app após o deploy",
    "smoke_test": "Testar as rotas após o deploy",
}

DROPDOWN_WIDGETS = {
    "enable_web_search": ["true", "false"],
    "run_app": ["true", "false"],
    "smoke_test": ["true", "false"],
}

if dbutils is not None:
    for _name, _value in DEFAULTS.items():
        try:
            dbutils.widgets.get(_name)  # type: ignore[union-attr]
        except Exception:
            if _name in DROPDOWN_WIDGETS:
                dbutils.widgets.dropdown(_name, _value, DROPDOWN_WIDGETS[_name], WIDGET_LABELS[_name])  # type: ignore[union-attr]
            else:
                dbutils.widgets.text(_name, _value, WIDGET_LABELS[_name])  # type: ignore[union-attr]


def widget(name: str) -> str:
    if dbutils is None:
        return DEFAULTS[name]
    value = dbutils.widgets.get(name).strip()  # type: ignore[union-attr]
    return value or DEFAULTS[name]


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def as_float(value: str, name: str) -> float:
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"`{name}` precisa ser numérico; recebi {value!r}.") from None


def as_int(value: str, name: str) -> int:
    try:
        return int(float(value))
    except ValueError:
        raise ValueError(f"`{name}` precisa ser inteiro; recebi {value!r}.") from None


def validate_lakebase_compute(min_cu: float, max_cu: float, suspend_seconds: int) -> None:
    if min_cu <= 0 or max_cu <= 0:
        raise ValueError("Os valores de CU do Lakebase precisam ser positivos.")
    if min_cu > max_cu:
        raise ValueError("`lakebase_min_cu` não pode ser maior que `lakebase_max_cu`.")
    if not (60 <= suspend_seconds <= 604800):
        raise ValueError("`lakebase_scale_to_zero_seconds` deve ficar entre 60 e 604800 segundos.")


APP_DESCRIPTION = "Porto Insights — copiloto executivo (Genie One, Google Workspace, grafo)."
APP_NAME_PATTERN = r"[a-z0-9][a-z0-9-]{1,29}"
OBO_SCOPES = ["genie", "model-serving", "ai-gateway", "catalog.tables:read"]


@dataclass(frozen=True)
class DeployConfig:
    app_name: str
    warehouse_id: str
    porto_catalog: str
    porto_schema: str
    model_endpoints: str
    default_model_endpoint: str
    lakebase_project_id: str
    lakebase_min_cu: float
    lakebase_max_cu: float
    lakebase_scale_to_zero_seconds: int
    enable_web_search: bool
    mlflow_experiment_path: str
    run_app: bool
    smoke_test: bool


CONFIG = DeployConfig(
    app_name=widget("app_name"),
    warehouse_id=widget("warehouse_id") if widget("warehouse_id") != DEFAULTS["warehouse_id"] else "",
    porto_catalog=widget("porto_catalog"),
    porto_schema=widget("porto_schema"),
    model_endpoints=widget("model_endpoints"),
    default_model_endpoint=widget("default_model_endpoint"),
    lakebase_project_id=widget("lakebase_project_id"),
    lakebase_min_cu=as_float(widget("lakebase_min_cu"), "lakebase_min_cu"),
    lakebase_max_cu=as_float(widget("lakebase_max_cu"), "lakebase_max_cu"),
    lakebase_scale_to_zero_seconds=as_int(widget("lakebase_scale_to_zero_seconds"), "lakebase_scale_to_zero_seconds"),
    enable_web_search=as_bool(widget("enable_web_search")),
    mlflow_experiment_path=widget("mlflow_experiment_path") if widget("mlflow_experiment_path") != DEFAULTS["mlflow_experiment_path"] else "",
    run_app=as_bool(widget("run_app")),
    smoke_test=as_bool(widget("smoke_test")),
)

if not re.fullmatch(APP_NAME_PATTERN, CONFIG.app_name):
    raise ValueError("O nome do app deve ter 2–30 caracteres minúsculos alfanuméricos ou hífens.")
validate_lakebase_compute(CONFIG.lakebase_min_cu, CONFIG.lakebase_max_cu, CONFIG.lakebase_scale_to_zero_seconds)

print("Plano de deploy do Porto Insights:")
print(json.dumps({
    "app_name": CONFIG.app_name,
    "warehouse_id": CONFIG.warehouse_id or "(seleção automática)",
    "lakebase_project_id": CONFIG.lakebase_project_id,
    "lakebase_autoscaling_cu": f"{CONFIG.lakebase_min_cu:g}-{CONFIG.lakebase_max_cu:g} CU",
    "lakebase_scale_to_zero_seconds": CONFIG.lakebase_scale_to_zero_seconds,
    "default_model_endpoint": CONFIG.default_model_endpoint,
    "enable_web_search": CONFIG.enable_web_search,
    "obo_scopes": OBO_SCOPES,
    "run_app": CONFIG.run_app,
    "smoke_test": CONFIG.smoke_test,
}, indent=2, ensure_ascii=False))

# COMMAND ----------

# DBTITLE 1,Helpers de REST API
class DbxApiError(RuntimeError):
    def __init__(self, status: int, body: str, path: str) -> None:
        super().__init__(f"{status} em {path}: {body[:500]}")
        self.status = status
        self.body = body
        self.path = path


def fail(message: str) -> None:
    raise RuntimeError(message)


def notebook_context() -> tuple[str, str, str]:
    if dbutils is None:
        fail("Este notebook precisa rodar dentro do Databricks; `dbutils` não está disponível.")
    ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()  # type: ignore[union-attr]
    host = ctx.apiUrl().get().rstrip("/")
    token = ctx.apiToken().get()
    user = ctx.userName().get() if ctx.userName().isDefined() else ""
    if not host or not token:
        fail("Não consegui ler host/token do contexto do notebook.")
    return host, token, user


DATABRICKS_HOST, DATABRICKS_TOKEN, NOTEBOOK_USER = notebook_context()


def dbx_api(method: str, path: str, body: dict[str, Any] | None = None, timeout_s: int = 120) -> dict[str, Any]:
    url = f"{DATABRICKS_HOST}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise DbxApiError(err.code, raw, path) from err


def postgres_api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return dbx_api(method, f"/api/2.0/postgres/{path.lstrip('/')}", body)


def poll_postgres_operation(name: str, timeout_s: int = 900) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        op = postgres_api("GET", name)
        if op.get("done"):
            if op.get("error"):
                fail(f"Operação do Lakebase falhou: {json.dumps(op['error'])}")
            return
        time.sleep(5)
    fail(f"Timeout esperando a operação do Lakebase {name}")


def choose_warehouse(configured_id: str) -> str:
    if configured_id:
        return configured_id
    data = dbx_api("GET", "/api/2.0/sql/warehouses")
    warehouses = [w for w in data.get("warehouses", []) if w.get("state") != "DELETED"]
    if not warehouses:
        fail("Nenhum SQL warehouse encontrado. Crie um e preencha o widget `warehouse_id`.")
    warehouses.sort(key=lambda w: 0 if w.get("state") == "RUNNING" else 1)
    selected = warehouses[0]
    print(f"SQL warehouse selecionado: {selected['id']} ({selected.get('name', 'sem nome')})")
    return selected["id"]

# COMMAND ----------

# DBTITLE 1,Lakebase (histórico de conversas)
def ensure_lakebase_project(project_id: str, min_cu: float, max_cu: float, suspend_seconds: int) -> None:
    """Cria o projeto Lakebase se não existir (o branch `production` e o database
    `databricks_postgres` são criados automaticamente com o projeto)."""
    encoded = urllib.parse.quote(project_id, safe="")
    try:
        project = postgres_api("GET", f"projects/{encoded}")
        if project.get("delete_time"):
            fail(f"O projeto Lakebase `{project_id}` está soft-deleted. Purgue-o ou escolha outro ID.")
        print(f"Projeto Lakebase já existe: {project_id}")
        return
    except DbxApiError as err:
        if err.status != 404:
            raise

    print(f"Criando projeto Lakebase: {project_id}")
    created = postgres_api("POST", f"projects?project_id={encoded}", {
        "spec": {"display_name": project_id, "pg_version": "17", "enable_pg_native_login": True},
        "initial_endpoint_spec": {
            "autoscaling_limit_min_cu": min_cu,
            "autoscaling_limit_max_cu": max_cu,
            "suspend_timeout_duration": f"{suspend_seconds}s",
        },
    })
    if created.get("name") and created.get("done") is not True:
        poll_postgres_operation(created["name"])
    postgres_api("GET", f"projects/{encoded}")  # confirma que ficou READY


def resolve_lakebase_paths(project_id: str) -> tuple[str, str]:
    """Devolve (branch_resource_name, database_resource_name) do projeto — resolvidos pela API,
    não hardcoded (o ID do database no path pode diferir do nome PG)."""
    project_name = f"projects/{project_id}"
    branches = postgres_api("GET", f"{project_name}/branches").get("branches") or []
    branch = next((b for b in branches if str(b.get("name", "")).endswith("/branches/production")), None)
    if branch is None and branches:
        branch = branches[0]
    if branch is None:
        fail(f"Nenhum branch encontrado no projeto Lakebase `{project_id}`.")
    branch_name = branch["name"]

    databases = postgres_api("GET", f"{branch_name}/databases").get("databases") or []
    database = next((d for d in databases if str(d.get("name", "")).endswith("databricks_postgres")
                     or str(d.get("name", "")).endswith("databricks-postgres")), None)
    if database is None and databases:
        database = databases[0]
    if database is None:
        fail(f"Nenhum database encontrado no branch `{branch_name}`.")
    print(f"Lakebase branch: {branch_name}")
    print(f"Lakebase database: {database['name']}")
    return branch_name, database["name"]

# COMMAND ----------

# DBTITLE 1,Localizar e preparar o código do app
RUNTIME_EXCLUDED_PARTS = {"__pycache__", "node_modules", ".git", ".venv", "tests", ".pytest_cache"}
RUNTIME_EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".map", ".tsbuildinfo"}
MAX_APP_SOURCE_FILE_BYTES = 10 * 1024 * 1024


def find_repo_root() -> Path:
    starts = [Path.cwd().resolve()]
    if dbutils is not None:
        try:
            ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()  # type: ignore[union-attr]
            nb_path = ctx.notebookPath().get()
            ws_path = Path("/Workspace" + nb_path)
            starts.extend([ws_path.parent, ws_path.parent.parent])
        except Exception:
            pass
    seen: set[Path] = set()
    for start in starts:
        for candidate in [start, *start.parents]:
            if candidate in seen:
                continue
            seen.add(candidate)
            if (candidate / "app.yaml").exists() and (candidate / "backend").is_dir() \
                    and (candidate / "frontend" / "dist").is_dir():
                return candidate
    fail(
        "Não encontrei o repositório do Porto Insights ao lado deste notebook. "
        "Importe a PASTA INTEIRA do repo no Workspace (com backend/, frontend/dist/ e app.yaml) "
        "e mantenha este notebook em notebooks/."
    )


def override_app_yaml(text: str, overrides: dict[str, str]) -> str:
    """Substitui o `value:` que segue cada `- name: <VAR>` no app.yaml (sem depender de PyYAML).
    Para chaves ausentes, acrescenta a entrada ao fim do bloco `env:`."""
    remaining = dict(overrides)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.match(r"^(\s*)-\s*name:\s*([A-Z0-9_]+)\s*$", line)
        if m and m.group(2) in remaining:
            indent, key = m.group(1), m.group(2)
            if i + 1 < len(lines) and re.match(r"^\s*value:", lines[i + 1]):
                out.append(f"{indent}  value: {json.dumps(remaining.pop(key))}")
                i += 2
                continue
        i += 1
    # chaves que não existiam ainda: adiciona no fim do arquivo dentro de env:
    if remaining:
        for key, value in remaining.items():
            out.append(f"  - name: {key}")
            out.append(f"    value: {json.dumps(value)}")
    return "\n".join(out) + "\n"


def stage_source(repo_root: Path, cfg: DeployConfig, warehouse_id: str) -> Path:
    base = Path("/local_disk0") if os.access("/local_disk0", os.W_OK) else Path(tempfile.gettempdir())
    work = Path(tempfile.mkdtemp(prefix="porto-deploy-", dir=base)) / "porto-insights"
    work.mkdir(parents=True)

    # copia backend/ e frontend/dist/, mais os arquivos de runtime da raiz
    def _copytree(src: Path, dst: Path) -> None:
        for path in sorted(src.rglob("*")):
            rel = path.relative_to(src)
            if any(part in RUNTIME_EXCLUDED_PARTS for part in rel.parts):
                continue
            if path.is_dir():
                continue
            if path.suffix.lower() in RUNTIME_EXCLUDED_SUFFIXES:
                continue
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(str(path), str(target))

    _copytree(repo_root / "backend", work / "backend")
    _copytree(repo_root / "frontend" / "dist", work / "frontend" / "dist")
    for fname in ("requirements.txt",):
        shutil.copy(str(repo_root / fname), str(work / fname))

    # app.yaml com os valores do cliente injetados
    app_yaml = (repo_root / "app.yaml").read_text(encoding="utf-8")
    app_yaml = override_app_yaml(app_yaml, {
        "SQL_WAREHOUSE_ID": warehouse_id,
        "PORTO_CATALOG": cfg.porto_catalog,
        "PORTO_SCHEMA": cfg.porto_schema,
        "MODEL_ENDPOINTS": cfg.model_endpoints,
        "DEFAULT_MODEL_ENDPOINT": cfg.default_model_endpoint,
        "MCP_WEB_SEARCH_ENABLED": "true" if cfg.enable_web_search else "false",
        # O notebook é dono de TODA a config específica de workspace: zera a observabilidade
        # (o path do experimento no repo é do ambiente de dev; tracing é opt-in por workspace).
        "MLFLOW_EXPERIMENT_PATH": cfg.mlflow_experiment_path,
    })
    (work / "app.yaml").write_text(app_yaml, encoding="utf-8")
    print(f"Código preparado em: {work}")
    return work


def runtime_source_files(work: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(work.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(work)
        if any(part in RUNTIME_EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.stat().st_size > MAX_APP_SOURCE_FILE_BYTES:
            fail(f"Arquivo grande demais para publicar (>10 MiB): {rel}")
        files.append(rel)
    if not any(f.as_posix() == "app.yaml" for f in files):
        fail("app.yaml ausente no código preparado.")
    return files

# COMMAND ----------

# DBTITLE 1,Publicar o código no Workspace
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_fingerprint(work: Path, files: list[Path]) -> str:
    manifest = [{"path": f.as_posix(), "sha256": file_sha256(work / f)} for f in files]
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def workspace_status(path: str) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(path, safe="")
    try:
        return dbx_api("GET", f"/api/2.0/workspace/get-status?path={encoded}")
    except DbxApiError as err:
        if err.status == 404:
            return None
        raise


def workspace_import_raw(path: str, content: bytes, timeout_s: int = 600) -> None:
    boundary = f"porto-{secrets.token_hex(16)}"
    parts: list[bytes] = []

    def field(name: str, value: str) -> None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"), b"\r\n",
        ])

    field("path", path)
    field("format", "RAW")
    field("overwrite", "true")
    filename = Path(path).name.replace('"', "")
    parts.extend([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n", content, b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        f"{DATABRICKS_HOST}/api/2.0/workspace/import",
        data=b"".join(parts), method="POST",
        headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s):
            return
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        raise DbxApiError(err.code, raw, "/api/2.0/workspace/import") from err


def user_path_segment(user: str) -> str:
    segment = user.strip()
    if not segment or segment in {".", ".."} or "/" in segment or "\\" in segment:
        fail(f"Não consigo derivar um caminho seguro em /Users a partir de {user!r}.")
    return segment


def publish_source(work: Path, app_name: str) -> str:
    files = runtime_source_files(work)
    fingerprint = source_fingerprint(work, files)
    segment = user_path_segment(NOTEBOOK_USER)
    api_root = f"/Users/{segment}/.porto-insights/releases/{app_name}/{fingerprint[:32]}"
    marker = f"{api_root}/.porto-release.json"
    source_path = f"/Workspace{api_root}"

    if workspace_status(marker) is not None:
        print(f"Código já publicado (idêntico): {source_path}")
        return source_path

    dbx_api("POST", "/api/2.0/workspace/mkdirs", {"path": api_root})
    parents = sorted({f"{api_root}/{f.parent.as_posix()}" for f in files if f.parent != Path(".")})
    for parent in parents:
        dbx_api("POST", "/api/2.0/workspace/mkdirs", {"path": parent})

    total = sum((work / f).stat().st_size for f in files)
    print(f"Publicando {len(files)} arquivos ({total / (1024 * 1024):.1f} MiB) via Workspace API…")
    for rel in files:
        workspace_import_raw(f"{api_root}/{rel.as_posix()}", (work / rel).read_bytes())

    workspace_import_raw(marker, json.dumps({"fingerprint": fingerprint, "files": len(files)}).encode("utf-8"))
    if workspace_status(marker) is None:
        fail(f"O marcador de release não foi criado: {marker}")
    print(f"Código publicado: {source_path}")
    return source_path

# COMMAND ----------

# DBTITLE 1,Criar/atualizar o Databricks App e fazer o deployment
def desired_app_resources(warehouse_id: str, branch_name: str, database_name: str) -> list[dict[str, Any]]:
    return [
        {"name": "sql-warehouse", "sql_warehouse": {"id": warehouse_id, "permission": "CAN_USE"}},
        {"name": "lakebase", "postgres": {"branch": branch_name, "database": database_name,
                                          "permission": "CAN_CONNECT_AND_CREATE"}},
    ]


def compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def wait_app_service_principal(app_name: str, timeout_s: int = 300) -> dict[str, Any]:
    encoded = urllib.parse.quote(app_name, safe="")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        meta = dbx_api("GET", f"/api/2.0/apps/{encoded}")
        if meta.get("service_principal_id") or meta.get("service_principal_client_id"):
            return meta
        time.sleep(5)
    return dbx_api("GET", f"/api/2.0/apps/{encoded}")


def wait_app_configuration(app_name: str, timeout_s: int = 300) -> dict[str, Any]:
    encoded = urllib.parse.quote(app_name, safe="")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        meta = dbx_api("GET", f"/api/2.0/apps/{encoded}")
        status = (meta.get("compute_status") or {}).get("state") or meta.get("app_status", {}).get("state")
        if status not in {"UPDATING", "STARTING", None} or meta.get("resources"):
            return meta
        time.sleep(5)
    return dbx_api("GET", f"/api/2.0/apps/{encoded}")


def ensure_app(cfg: DeployConfig, warehouse_id: str, branch_name: str, database_name: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(cfg.app_name, safe="")
    desired_resources = desired_app_resources(warehouse_id, branch_name, database_name)
    try:
        meta = dbx_api("GET", f"/api/2.0/apps/{encoded}")
        exists = True
    except DbxApiError as err:
        if err.status != 404:
            raise
        exists = False

    if not exists:
        print(f"Criando o Databricks App (sem compute): {cfg.app_name}")
        try:
            dbx_api("POST", "/api/2.0/apps?no_compute=true", {
                "name": cfg.app_name, "description": APP_DESCRIPTION,
                "resources": desired_resources, "user_api_scopes": OBO_SCOPES,
            })
        except DbxApiError as err:
            if err.status != 409:
                raise
        meta = wait_app_service_principal(cfg.app_name)
    else:
        if meta.get("description") not in (APP_DESCRIPTION, None, ""):
            fail(f"Recuso-me a alterar o App `{cfg.app_name}`: a descrição não bate com o marcador do Porto Insights.")
        current = meta.get("resources") or []
        scopes_ok = set(OBO_SCOPES).issubset(set(meta.get("effective_user_api_scopes") or meta.get("user_api_scopes") or []))
        if compact(current) == compact(desired_resources) and scopes_ok:
            print(f"Configuração OBO do App já está correta: {cfg.app_name}")
            return meta
        print(f"Reconciliando resources/escopos OBO do App: {cfg.app_name}")
        dbx_api("PATCH", f"/api/2.0/apps/{encoded}", {
            "description": APP_DESCRIPTION, "resources": desired_resources, "user_api_scopes": OBO_SCOPES,
        })
        meta = wait_app_configuration(cfg.app_name)
    return meta


def ensure_app_deployment(app_name: str, source_path: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(app_name, safe="")
    active = (dbx_api("GET", f"/api/2.0/apps/{encoded}").get("active_deployment") or {})
    if active.get("source_code_path") == source_path and active.get("status", {}).get("state") == "SUCCEEDED":
        print("Deployment ativo já aponta para este código.")
        return active

    print(f"Criando deployment a partir de {source_path}")
    created = dbx_api("POST", f"/api/2.0/apps/{encoded}/deployments", {"source_code_path": source_path})
    deployment_id = created.get("deployment_id")
    deadline = time.time() + 900
    while time.time() < deadline:
        dep = dbx_api("GET", f"/api/2.0/apps/{encoded}/deployments/{urllib.parse.quote(str(deployment_id), safe='')}")
        state = dep.get("status", {}).get("state")
        if state == "SUCCEEDED":
            print("Deployment concluído.")
            return dep
        if state in {"FAILED", "STOPPED", "CANCELLED"}:
            fail(f"Deployment terminou em {state}: {json.dumps(dep.get('status', {}))}")
        time.sleep(10)
    fail("Timeout esperando o deployment do App.")


def ensure_app_compute_active(app_name: str, timeout_s: int = 1200) -> dict[str, Any]:
    """Sobe o compute do App e espera ficar ACTIVE. Precisa acontecer ANTES do deployment:
    a API recusa deploy num app que não está RUNNING."""
    encoded = urllib.parse.quote(app_name, safe="")
    deadline = time.time() + timeout_s
    start_requested = False
    last: dict[str, Any] = {}
    while time.time() < deadline:
        meta = dbx_api("GET", f"/api/2.0/apps/{encoded}")
        compute = meta.get("compute_status", {})
        state = compute.get("state")
        last = compute
        if state == "ACTIVE":
            print(f"Compute do App ativo: {app_name}")
            return meta
        if state == "ERROR":
            fail(f"O compute do App falhou ao subir: {json.dumps(compute, indent=2)}")
        if state in {"STOPPED", None} and not start_requested:
            print(f"Iniciando o compute do App antes do deployment: {app_name}")
            try:
                dbx_api("POST", f"/api/2.0/apps/{encoded}/start", {})
            except DbxApiError as err:
                body = err.body.lower()
                transient = err.status in {400, 409} and any(
                    m in body for m in ("already", "in progress", "starting", "active", "running")
                )
                if not transient:
                    raise
                print(f"Start já em andamento: {err.body[:200]}")
            start_requested = True
        time.sleep(8)
    fail(f"Timeout esperando o compute do App ficar ACTIVE.\n{json.dumps(last, indent=2)}")


def stop_app_compute(app_name: str) -> None:
    encoded = urllib.parse.quote(app_name, safe="")
    try:
        dbx_api("POST", f"/api/2.0/apps/{encoded}/stop", {})
        print(f"Compute do App parado (run_app=false): {app_name}")
    except DbxApiError as err:
        if err.status not in {400, 409}:
            raise


def smoke_test(app_url: str) -> None:
    target = f"{app_url.rstrip('/')}/api/me"
    req = urllib.request.Request(target, headers={"Authorization": f"Bearer {DATABRICKS_TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            ok = resp.status == 200
            print(f"Smoke-test GET /api/me → HTTP {resp.status} {'OK' if ok else ''}")
    except urllib.error.HTTPError as err:
        # 401/403 aqui ainda indica que o app subiu e está roteando (auth OBO é por usuário no browser)
        print(f"Smoke-test GET /api/me → HTTP {err.code} (app respondeu; auth OBO acontece no browser)")
    except Exception as exc:  # noqa: BLE001
        print(f"Smoke-test não conclusivo: {exc}")

# COMMAND ----------

# DBTITLE 1,Executar o deploy
def main() -> None:
    print("=" * 72)
    print("Deploy do Porto Insights")
    print("=" * 72)

    warehouse_id = choose_warehouse(CONFIG.warehouse_id)

    ensure_lakebase_project(
        CONFIG.lakebase_project_id, CONFIG.lakebase_min_cu, CONFIG.lakebase_max_cu,
        CONFIG.lakebase_scale_to_zero_seconds,
    )
    branch_name, database_name = resolve_lakebase_paths(CONFIG.lakebase_project_id)

    repo_root = find_repo_root()
    print(f"Repositório encontrado em: {repo_root}")
    work = stage_source(repo_root, CONFIG, warehouse_id)
    source_path = publish_source(work, CONFIG.app_name)

    meta = ensure_app(CONFIG, warehouse_id, branch_name, database_name)
    # O compute precisa estar ACTIVE ANTES do deployment (a API recusa deploy fora de RUNNING).
    meta = ensure_app_compute_active(CONFIG.app_name)
    ensure_app_deployment(CONFIG.app_name, source_path)

    app_url = meta.get("url") or dbx_api("GET", f"/api/2.0/apps/{urllib.parse.quote(CONFIG.app_name, safe='')}").get("url", "")

    if CONFIG.smoke_test and app_url:
        smoke_test(app_url)
    if not CONFIG.run_app:
        stop_app_compute(CONFIG.app_name)

    print("=" * 72)
    print("Deploy concluído.")
    print(f"App: {CONFIG.app_name}")
    print(f"URL: {app_url or '(inicie o app para obter a URL)'}")
    print("Lembrete: os conectores Google e a busca na web pedem consentimento OAuth por usuário,")
    print("dentro do app, na primeira vez que cada conta é usada.")
    print("=" * 72)


main()
