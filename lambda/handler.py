# handler.py — ingest "string-only" (todas as colunas TEXT), CSV usa 1ª linha como cabeçalho.
import os
import io
import csv
import json
import re
import time
import logging
import datetime
from typing import Iterator, Dict, List, Tuple
from urllib import request, error

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------- utils ----------
def require(env_key: str) -> str:
    val = os.getenv(env_key)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {env_key}")
    return val

def as_bool(s: str, default: bool = False) -> bool:
    if s is None:
        return default
    return str(s).strip().lower() in ("1", "true", "t", "yes", "y", "sim", "on")

def load_settings() -> Dict[str, str]:
    return {
        "SUPABASE_URL":          require("SUPABASE_URL").rstrip("/"),
        "SUPABASE_SERVICE_KEY":  require("SUPABASE_SERVICE_ROLE_KEY"),
        "SUPABASE_PROJECT_REF":  os.getenv("SUPABASE_PROJECT_REF", ""),  # opcional (logs)
        "PG_SCHEMA":             os.getenv("PG_SCHEMA", "public"),
        "TABLE_STRATEGY":        os.getenv("TABLE_STRATEGY", "filename"),  # "filename" | "header_table"
        "TABLE_PREFIX":          os.getenv("TABLE_PREFIX", ""),
        "SAMPLE_LINES":          int(os.getenv("SAMPLE_LINES_FOR_INFERENCE", "300")),
        "BATCH_SIZE":            int(os.getenv("BATCH_SIZE", "1000")),
        "ADD_METADATA":          as_bool(os.getenv("ADD_METADATA", "false"), default=False),
    }

# ==== S3 ====
s3 = boto3.client("s3")

# ==== helpers ====
SAFE_COL_RE = re.compile(r"[^a-zA-Z0-9_]+")

def sanitize_identifier(name: str) -> str:
    name = (name or "").strip().replace(" ", "_")
    name = SAFE_COL_RE.sub("_", name).strip("_")
    if not name:
        name = "col"
    if name[0].isdigit():
        name = f"c_{name}"
    return name.lower()

def make_unique_names(raw_headers: List[str]) -> Tuple[Dict[str, str], set]:
    """
    Retorna (map_raw_to_sanitized, used_sanitized).
    Garante nomes únicos: se colidir, adiciona _2, _3, ...
    """
    used = set()
    mapping: Dict[str, str] = {}
    for h in raw_headers:
        base = sanitize_identifier(h)
        cand = base or "col"
        i = 2
        while cand in used:
            cand = f"{base or 'col'}_{i}"
            i += 1
        mapping[h] = cand
        used.add(cand)
    return mapping, used

def to_text(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() in ("null", "none", "nan"):
            return None
        return v
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)

def strip_schema_if_any(name: str) -> str:
    """
    Se vier 'schema.table', retorna apenas 'table'.
    """
    return name.split(".", 1)[-1]

# ===== RPC para DDL (sempre TEXT) =====
def ensure_columns_text_via_rpc(cfg: Dict[str, str], schema: str, table: str, sanitized_cols: List[str]):
    """
    Cria schema/tabela se necessário e adiciona colunas TEXT (idempotente).
    Requer a função public.ensure_table no banco.
    """
    table = strip_schema_if_any(table)
    if not sanitized_cols:
        return
    url = f"{cfg['SUPABASE_URL']}/rest/v1/rpc/ensure_table"
    payload = {"p_schema": schema, "p_table": table, "p_cols": {col: "text" for col in sanitized_cols}}
    headers = {
        "apikey":        cfg["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {cfg['SUPABASE_SERVICE_KEY']}",
        "Content-Type":  "application/json",
        "Prefer":        "return=minimal",
    }
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            _ = resp.read()
    except error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        logger.error("RPC ensure_table ERROR %s: %s", e.code, body[:800])
        raise

# ===== Inserção via REST =====
def supabase_rest_insert(schema: str, table: str, rows: List[Dict], cfg: Dict[str, str]) -> int:
    if not rows:
        return 0
    table = strip_schema_if_any(table)
    url = f"{cfg['SUPABASE_URL']}/rest/v1/{table}"
    headers = {
        "apikey":        cfg["SUPABASE_SERVICE_KEY"],
        "Authorization": f"Bearer {cfg['SUPABASE_SERVICE_KEY']}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }
    data = json.dumps(rows).encode("utf-8")

    # Retry curto para o caso do PostgREST ainda não ter recarregado o schema (PGRST205)
    for attempt in range(3):
        req = request.Request(url, data=data, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=60) as resp:
                _ = resp.read()
                return len(rows)
        except error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 404 and "PGRST205" in body and attempt < 2:
                logger.warning("Tabela ainda não no cache do PostgREST (tentativa %d). Aguardando e tentando de novo...", attempt + 1)
                time.sleep(0.35)
                continue
            logger.error("REST insert ERROR %s: %s", e.code, body[:800])
            raise

# ===== streaming readers =====
def stream_csv_rows(streaming_body, sample_limit: int):
    """
    CSV: PRIMEIRA LINHA = CABEÇALHO (não vira dado).
    """
    text_stream = io.TextIOWrapper(streaming_body, encoding="utf-8-sig", errors="replace", newline="")
    reader = csv.reader(text_stream)
    try:
        headers = next(reader)
    except StopIteration:
        return [], iter([])

    headers = [h.strip() if h is not None else "" for h in headers]
    sample_rows: List[Dict[str, str]] = []
    count = 0

    def gen_rows():
        # devolve só dados (sem o header)
        for r in sample_rows:
            yield r
        for cells in reader:
            row = {headers[i]: (cells[i] if i < len(cells) else None) for i in range(len(headers))}
            yield row

    for cells in reader:
        row = {headers[i]: (cells[i] if i < len(cells) else None) for i in range(len(headers))}
        if count < sample_limit:
            sample_rows.append(row)
            count += 1
        else:
            return headers, gen_rows()

    return headers, iter(sample_rows)

def stream_ndjson_rows(streaming_body, sample_limit: int):
    """
    NDJSON: sem cabeçalho fixo; cabeçalhos são derivados das chaves vistas.
    """
    text_stream = io.TextIOWrapper(streaming_body, encoding="utf-8", errors="replace")
    sample_rows: List[Dict[str, str]] = []
    headers_set = set()
    count = 0

    def gen_rows():
        for r in sample_rows:
            yield r
        for line in text_stream:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            for k in headers_set:
                obj.setdefault(k, None)
            yield obj

    for line in text_stream:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if count < sample_limit:
            sample_rows.append(obj)
            headers_set.update(obj.keys())
            count += 1
        else:
            headers = sorted(headers_set)
            for r in sample_rows:
                for k in headers:
                    r.setdefault(k, None)
            return headers, gen_rows()

    headers = sorted(headers_set) if sample_rows else []
    for r in sample_rows:
        for k in headers:
            r.setdefault(k, None)
    return headers, iter(sample_rows)

# ===== table name =====
def resolve_table_name(object_key: str, headers: List[str], first_row: Dict[str, str],
                       table_strategy: str, table_prefix: str) -> str:
    """
    filename: usa o nome do arquivo
    header_table: se existir coluna __table__ na PRIMEIRA linha, usa seu valor
    """
    if table_strategy == "header_table" and "__table__" in headers and first_row:
        val = (first_row.get("__table__") or "").strip()
        name = sanitize_identifier(val)
        if not name:
            raise ValueError("Valor de __table__ inválido")
        return table_prefix + name

    base = object_key.split("/")[-1]
    base = base.rsplit(".", 1)[0] if "." in base else base
    return table_prefix + sanitize_identifier(base)

# ===== main =====
def lambda_handler(event, context):
    try:
        cfg = load_settings()
        logger.info(
            "CFG: schema=%s, strategy=%s, prefix=%s, batch=%s, sample=%s, add_meta=%s, project_ref=%s",
            cfg["PG_SCHEMA"], cfg["TABLE_STRATEGY"], cfg["TABLE_PREFIX"],
            cfg["BATCH_SIZE"], cfg["SAMPLE_LINES"], cfg["ADD_METADATA"], cfg["SUPABASE_PROJECT_REF"]
        )

        total_processed = 0
        for rec in event.get("Records", []):
            bucket = rec["s3"]["bucket"]["name"]
            key    = rec["s3"]["object"]["key"]

            resp = s3.get_object(Bucket=bucket, Key=key)
            content_len = resp.get("ContentLength")
            logger.info("S3 object: s3://%s/%s size=%s bytes", bucket, key, content_len)
            body = resp["Body"]
            key_lower = key.lower()

            # === parser ===
            if key_lower.endswith(".csv"):
                headers_raw, rows_iter = stream_csv_rows(body, sample_limit=cfg["SAMPLE_LINES"])
            elif key_lower.endswith(".ndjson") or key_lower.endswith(".jsonl"):
                headers_raw, rows_iter = stream_ndjson_rows(body, sample_limit=cfg["SAMPLE_LINES"])
            elif key_lower.endswith(".json"):
                # CUIDADO: JSON array carrega em memória; prefira NDJSON/CSV para grandes volumes
                content = body.read()
                parsed = json.loads(content)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    headers_raw = sorted({k for obj in parsed for k in obj.keys()})
                    rows_iter = iter(parsed)
                elif isinstance(parsed, dict):
                    headers_raw = list(parsed.keys())
                    rows_iter = iter([parsed])
                else:
                    logger.warning("JSON não suportado. Use array de objetos ou NDJSON.")
                    continue
            else:
                logger.warning("Extensão não suportada: %s (pulando)", key)
                continue

            # peek primeira linha (para header_table e validações)
            try:
                first_row = next(rows_iter)
                def putback(first, it):
                    yield first
                    for r in it:
                        yield r
                rows_iter = putback(first_row, rows_iter)
            except StopIteration:
                logger.info("Arquivo sem dados: %s", key)
                continue

            table_name = resolve_table_name(
                key, headers_raw, first_row,
                table_strategy=cfg["TABLE_STRATEGY"],
                table_prefix=cfg["TABLE_PREFIX"]
            )
            table_name = strip_schema_if_any(table_name)  # evita 'public.public.tabela' no PostgREST
            logger.info("Tabela alvo: %s.%s", cfg["PG_SCHEMA"], table_name)

            # nomes únicos (a partir do header; CSV usa 1ª linha como cabeçalho)
            base_headers = list(headers_raw)

            # metadados opcionais
            meta_fields = []
            if cfg["ADD_METADATA"]:
                meta_fields = ["_s3_bucket", "_s3_key", "_ingested_at"]
                base_headers.extend(meta_fields)

            raw_to_col, used_names = make_unique_names(base_headers)

            # cria/expande tabela inicial (todas colunas TEXT)
            ensure_columns_text_via_rpc(cfg, cfg["PG_SCHEMA"], table_name, list(set(raw_to_col.values())))

            # para NDJSON/JSON: novas chaves podem surgir — criamos colunas sob demanda
            def sync_new_columns_if_needed(row: Dict[str, str]):
                new_raw = [k for k in row.keys() if k not in raw_to_col]
                if not new_raw:
                    return
                new_sanitized = []
                for h in new_raw:
                    base = sanitize_identifier(h)
                    cand = base or "col"
                    i = 2
                    while cand in used_names:
                        cand = f"{base or 'col'}_{i}"
                        i += 1
                    raw_to_col[h] = cand
                    used_names.add(cand)
                    new_sanitized.append(cand)
                ensure_columns_text_via_rpc(cfg, cfg["PG_SCHEMA"], table_name, new_sanitized)

            # iter: escreve linhas
            def final_iter():
                meta_vals = None
                if cfg["ADD_METADATA"]:
                    meta_vals = {
                        raw_to_col["_s3_bucket"]: bucket,
                        raw_to_col["_s3_key"]:    key,
                        raw_to_col["_ingested_at"]: datetime.datetime.utcnow().isoformat() + "Z",
                    }
                for row in rows_iter:
                    sync_new_columns_if_needed(row)
                    out = {raw_to_col[k]: to_text(v) for k, v in row.items() if k in raw_to_col}
                    if meta_vals:
                        out.update(meta_vals)
                    yield out

            # batch insert
            batch: List[Dict] = []
            processed = 0
            for out in final_iter():
                batch.append(out)
                if len(batch) >= cfg["BATCH_SIZE"]:
                    processed += supabase_rest_insert(cfg["PG_SCHEMA"], table_name, batch, cfg)
                    batch.clear()
            if batch:
                processed += supabase_rest_insert(cfg["PG_SCHEMA"], table_name, batch, cfg)

            logger.info("Processado %s: %d linhas", key, processed)
            total_processed += processed

        return {"status": "ok", "processed": total_processed}

    except Exception as e:
        logger.exception("UNHANDLED EXCEPTION: %s", e)
        raise
