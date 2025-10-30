"""Ferramentas para o agente fiscal carregar datasets de upload ou Supabase."""

from __future__ import annotations

from typing import List

from langchain.tools import Tool

from eda.domain import coerce_numeric
from fiscal.domain import load_fiscal_dataframe, load_supabase_table

from .context import AgentDataContext


def build_data_access_tools(ctx: AgentDataContext) -> List[Tool]:
    def reload_uploaded(_: str = "") -> str:
        """Reprocessa o arquivo fiscal original e atualiza o contexto."""
        meta = ctx.metadata
        if meta.get("source") in {"supabase"}:
            return "O último carregamento veio do Supabase; use a ferramenta dedicada para atualizar." \
                " Informe um arquivo via upload para reutilizar esta ferramenta."
        raw = meta.get("raw_bytes")
        file_path = meta.get("file_path")
        filename = meta.get("filename", "dados_fiscais.csv")
        if raw is None and file_path:
            try:
                with open(file_path, "rb") as fh:
                    raw = fh.read()
            except OSError as exc:
                return f"Falha ao ler o arquivo salvo em {file_path}: {exc}"
        if raw is None:
            return "Não há conteúdo bruto do arquivo disponível para recarregar."
        try:
            loaded = load_fiscal_dataframe(file_bytes=raw, filename=filename)
        except Exception as exc:
            return f"Falha ao processar o arquivo '{filename}': {exc}"
        df = coerce_numeric(loaded.dataframe)
        ctx.df = df
        preserved_path = file_path
        meta.clear()
        meta.update(
            {
                "source": loaded.source,
                **loaded.metadata,
                "raw_bytes": raw,
                "filename": filename,
                "rows": df.shape[0],
                "columns": df.shape[1],
            }
        )
        if preserved_path:
            meta["file_path"] = preserved_path
        ctx.bump_version()
        return (
            f"Dataset fiscal recarregado a partir de '{filename}' com {df.shape[0]} linhas "
            f"e {df.shape[1]} colunas."
        )

    def load_supabase(param_text: str = "") -> str:
        """Consulta o Supabase e substitui o dataset fiscal ativo."""
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
            df = load_supabase_table(schema=schema_name, table=table_name, limit=limit_value)
        except Exception as exc:
            return f"Erro ao consultar Supabase: {exc}"
        df = coerce_numeric(df)
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
            return f"Consulta ao Supabase ({schema_name}.{table_name}) concluída sem linhas retornadas."
        return (
            f"Dataset fiscal carregado do Supabase ({schema_name}.{table_name}) com {df.shape[0]} linhas "
            f"e {df.shape[1]} colunas (limite={limit_value})."
        )

    tools: List[Tool] = [
        Tool.from_function(
            func=reload_uploaded,
            name="reload_uploaded_fiscal_dataset",
            description="Reprocessa o arquivo fiscal enviado originalmente (CSV, XLSX, XML ou ZIP).",
        )
    ]

    if (meta := ctx.metadata) and (meta.get("source") == "supabase" or meta.get("supabase_table") or meta.get("schema")):
        tools.append(
            Tool.from_function(
                func=load_supabase,
                name="load_supabase_fiscal_dataset",
                description="Carrega dados fiscais do Supabase. Use pares schema=, table= e limit= para sobrescrever o contexto atual.",
            )
        )

    return tools
