"""Formatação de eventos Server-Sent Events (SSE).

Protocolo do endpoint de chat (tipos previstos ao longo das fases):
  turn_start · token · tool_call_start · tool_progress · tool_call_result ·
  graph_delta · auth_required · warning · done · error

Cada evento é uma linha `data: {json}\\n\\n` com o campo `type`.
"""
from __future__ import annotations

import json
from typing import Any


def sse(event_type: str, **data: Any) -> str:
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
