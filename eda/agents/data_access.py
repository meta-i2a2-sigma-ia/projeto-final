"""Tools that allow the agent to recarregar datasets a partir do upload ou Supabase."""

from __future__ import annotations

import io
import os
from typing import List

import pandas as pd
from langchain.tools import Tool

try:
    from supabase import create_client
except ImportError:  # pragma: no cover - optional dependency
    create_client = None  # type: ignore

from .context import AgentDataContext


def _load_supabase_dataframe(schema: str, table: str, limit: int) -> pd.DataFrame:
    if create_client is None:
        raise RuntimeError("Instale o pacote 'supabase' para consultar tabelas via API.")

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no ambiente.")

    client = create_client(url, key)
    table_ref = client.table(table, schema=schema)
    chunk_size = 50000
    rows: list[dict[str, object]] = []
    remaining = max(limit, 0)
    start = 0
    while remaining != 0:
        end = start + chunk_size - 1
        if remaining > 0:
            end = start + min(chunk_size, remaining) - 1
        try:
            response = table_ref.select("*").range(start, end).execute()
        except Exception as exc:  # pragma: no cover - network errors
            raise RuntimeError(f"Erro ao consultar Supabase: {exc}") from exc
        data = getattr(response, "data", None)
        if data is None:
            data = getattr(response, "get", lambda *_: None)("data")
        if not data:
            break
        rows.extend(data)
        fetched = len(data)
        if fetched < chunk_size:
            break
        if remaining > 0:
            remaining -= fetched
            if remaining <= 0:
                break
        start += chunk_size
    return pd.DataFrame(rows)


def build_data_access_tools(ctx: AgentDataContext) -> List[Tool]:
    """Expose ferramentas para o agente carregar ou recarregar dados."""

    def reload_uploaded(_: str = "") -> str:
        """Recarrega o dataframe com o conteúdo do último arquivo enviado."""
        meta = ctx.metadata
        if meta.get("source") != "upload":
            return "Nenhum arquivo enviado está vinculado ao agente no momento."
        raw = meta.get("raw_bytes")
        file_path = meta.get("file_path")
        try:
            if raw is not None:
                df = pd.read_csv(io.BytesIO(raw))
            elif file_path:
                df = pd.read_csv(file_path)
            else:
                return "O conteúdo original do arquivo não está disponível para recarregar."
        except Exception as exc:  # pragma: no cover - pandas errors
            if file_path and raw is not None:
                return f"Falha ao ler CSV do upload: {exc}"
            if file_path:
                return f"Falha ao ler CSV salvo em {file_path}: {exc}"
            return f"Falha ao ler CSV do upload: {exc}"
        ctx.df = df
        meta["rows"] = df.shape[0]
        meta["columns"] = df.shape[1]
        meta.setdefault("source", "upload")
        ctx.bump_version()
        return (
            "Dataset recarregado a partir do arquivo enviado"
            f" ({meta.get('filename', 'sem nome')}). Linhas: {df.shape[0]}, colunas: {df.shape[1]}."
        )

    def load_supabase(param_text: str = "") -> str:
        """Consulta o Supabase e substitui o dataset atual pelo resultado."""
        meta = ctx.metadata
        overrides: dict[str, str] = {}
        if param_text:
            normalized = param_text.replace(",", " ").replace(";", " ")
            for token in normalized.replace("\n", " ").split():
                if "=" not in token:
                    continue
                key, value = token.split("=", 1)
                overrides[key.strip().lower()] = value.strip()

        schema_name = overrides.get("supabase_schema") or overrides.get("schema")
        if schema_name is None:
            schema_name = meta.get("supabase_schema") or meta.get("schema") or "public"
        schema_name = schema_name.strip() or "public"

        table_name = (
            overrides.get("supabase_table")
            or overrides.get("table")
            or meta.get("supabase_table")
            or meta.get("table")
        )
        if not table_name:
            return "Informe a tabela Supabase (ex.: 'fiscal_docs')."
        limit_value_raw = (
            overrides.get("limit")
            or meta.get("limit")
            or meta.get("supabase_limit")
            or "20000"
        )
        try:
            limit_value = int(limit_value_raw)
        except (TypeError, ValueError):
            return f"Valor de limit inválido: {limit_value_raw}"
        try:
            df = _load_supabase_dataframe(schema_name, table_name, limit_value)
        except Exception as exc:
            return str(exc)
        ctx.df = df
        meta.clear()
        meta.update(
            {
                "source": "supabase",
                "supabase_schema": schema_name,
                "supabase_table": table_name,
                "limit": limit_value,
                "supabase_limit": limit_value,
                "rows": df.shape[0],
                "columns": df.shape[1],
            }
        )
        ctx.bump_version()
        if df.empty:
            return (
                f"Consulta ao Supabase concluída, mas nenhuma linha foi retornada para {schema_name}.{table_name}."
            )
        return (
            f"Dataset carregado do Supabase ({schema_name}.{table_name}) com {df.shape[0]} linhas"
            f" e {df.shape[1]} colunas (limit={limit_value})."
        )

    tools: List[Tool] = [
        Tool.from_function(
            func=reload_uploaded,
            name="reload_uploaded_dataset",
            description="Recarrega o dataset a partir do último arquivo CSV enviado pelo usuário.",
        )
    ]

    if (meta := ctx.metadata) and (meta.get("source") == "supabase" or meta.get("supabase_table") or meta.get("schema")):
        tools.append(
            Tool.from_function(
                func=load_supabase,
                name="load_supabase_dataset",
                description="Carrega dados do Supabase. Use pares schema=, table= e limit= se quiser sobrescrever o contexto.",
            )
        )

    return tools
