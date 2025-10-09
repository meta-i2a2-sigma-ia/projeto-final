import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


def eda_overview(df: pd.DataFrame) -> dict:
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    nonnum = [c for c in df.columns if c not in numeric]

    try:
        desc = df.describe(include="all", datetime_is_numeric=True).transpose()
    except TypeError:
        desc = df.describe(include="all").transpose()
    except Exception:
        desc = pd.DataFrame()

    if numeric:
        try:
            corr = df[numeric].corr(numeric_only=True)
        except TypeError:
            corr = df[numeric].corr()
    else:
        corr = pd.DataFrame()

    missing = df.isna().mean().sort_values(ascending=False)

    return {
        "n_rows": len(df),
        "n_cols": df.shape[1],
        "numeric_cols": numeric,
        "non_numeric_cols": nonnum,
        "describe": desc,
        "missing": missing,
        "corr": corr,
    }


def readable_dtype(dtype: pd.api.extensions.ExtensionDtype | np.dtype) -> str:
    try:
        return str(dtype)
    except Exception:
        return "object"


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            s = out[col].astype(str).str.replace(",", ".", regex=False)
            looks_num = s.str.fullmatch(r"[-+]?\d*(?:\.\d+)?").fillna(False)
            if looks_num.mean() > 0.8:
                out[col] = pd.to_numeric(s, errors="ignore")
    return out


def dataframe_signature(df: pd.DataFrame, sample_size: int = 50) -> str:
    sample = df.head(sample_size).to_json(default_handler=str)
    return hashlib.md5(sample.encode("utf-8")).hexdigest()


def _format_value(value: Any) -> str:
    if isinstance(value, (float, np.floating)):
        return f"{value:.4g}"
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        try:
            return pd.to_datetime(value).isoformat()
        except Exception:
            return str(value)
    return str(value)


def detect_temporal_patterns(df: pd.DataFrame, numeric_cols: List[str]) -> Dict[str, Any]:
    temporal_columns: Dict[str, pd.Series] = {}
    insights: List[str] = []

    for col in df.columns:
        series = df[col]
        parsed = None
        if is_datetime64_any_dtype(series):
            parsed = pd.to_datetime(series, errors="coerce")
        elif series.dtype == object:
            parsed_candidate = pd.to_datetime(series, errors="coerce", utc=False, infer_datetime_format=True)
            if parsed_candidate.notna().mean() > 0.6:
                parsed = parsed_candidate
        if parsed is not None and parsed.notna().sum() > 5:
            temporal_columns[col] = parsed

    for t_col, parsed in temporal_columns.items():
        ordinals = parsed.map(lambda v: v.toordinal() if isinstance(v, pd.Timestamp) else np.nan)
        valid = ordinals.notna()
        if valid.sum() < 10:
            continue
        ordinals = ordinals[valid]
        for num_col in numeric_cols:
            series = df.loc[valid, num_col]
            if series.nunique() < 5:
                continue
            try:
                corr = series.corr(ordinals, method="spearman")
            except Exception:
                continue
            if corr is not None and np.isfinite(corr) and abs(corr) >= 0.3:
                trend = "crescente" if corr > 0 else "decrescente"
                insights.append(f"{num_col} tem tendência {trend} em relação a {t_col} (rho≈{corr:.2f}).")

    return {
        "columns": list(temporal_columns.keys()),
        "insights": insights,
    }


def identify_value_frequencies(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        counts = df[col].value_counts(dropna=False)
        if counts.empty:
            continue
        most_val = counts.index[0]
        least_val = counts.index[-1]
        rows.append({
            "coluna": col,
            "valor_mais_frequente": _format_value(most_val),
            "freq_max": int(counts.iloc[0]),
            "valor_menos_frequente": _format_value(least_val),
            "freq_min": int(counts.iloc[-1]),
        })
    return pd.DataFrame(rows)


def detect_outliers(df: pd.DataFrame, numeric_cols: List[str]) -> pd.DataFrame:
    records = []
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 8:
            continue
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0 or pd.isna(iqr):
            continue
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        mask = (series < lower) | (series > upper)
        count = int(mask.sum())
        if count == 0:
            continue
        fraction = count / len(series)
        mean_shift = series.mean() - series[~mask].mean()
        records.append({
            "coluna": col,
            "outliers": count,
            "%": round(fraction * 100, 2),
            "limite_inferior": lower,
            "limite_superior": upper,
            "impacto_medio": mean_shift,
        })
    return pd.DataFrame(records)


OUTLIER_SUGGESTIONS = [
    "Remoção dos outliers para análises sensíveis à média (use apenas se forem erros claros).",
    "Aplicar cap/floor (winsorização) para limitar o impacto dos extremos sem perdê-los totalmente.",
    "Transformações log/box-cox em variáveis assimétricas para reduzir o peso de valores altos.",
    "Investigar manualmente registros atípicos com contexto de negócio antes de decidir removê-los.",
]


def detect_clusters(df: pd.DataFrame, numeric_cols: List[str]) -> Dict[str, Any]:
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {"status": "missing_dependency"}

    if len(numeric_cols) < 2:
        return {"status": "not_enough_features"}

    subset = df[numeric_cols].dropna()
    if subset.shape[0] < 50:
        return {"status": "not_enough_rows"}

    if subset.shape[0] > 5000:
        subset = subset.sample(5000, random_state=42)

    scaler = StandardScaler()
    try:
        scaled = scaler.fit_transform(subset)
    except Exception as exc:
        return {"status": "scaling_failed", "error": str(exc)}

    best = {"score": -1.0, "k": None, "labels": None}
    for k in range(2, min(6, subset.shape[0])):
        try:
            model = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = model.fit_predict(scaled)
            score = silhouette_score(scaled, labels)
        except Exception:
            continue
        if score > best["score"]:
            best.update({"score": score, "k": k, "labels": labels})

    if best["k"] is None:
        return {"status": "no_cluster"}

    counts = pd.Series(best["labels"]).value_counts().sort_index()
    return {
        "status": "ok",
        "k": int(best["k"]),
        "silhouette": round(float(best["score"]), 3),
        "cluster_sizes": {int(idx): int(val) for idx, val in counts.items()},
    }


def summarize_relationships(df: pd.DataFrame, numeric_cols: List[str], non_numeric_cols: List[str]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"correlations": [], "categorical": []}

    if numeric_cols:
        corr_matrix = df[numeric_cols].corr(method="spearman").abs()
        corr_pairs = []
        for i, col_i in enumerate(numeric_cols):
            for col_j in numeric_cols[i + 1:]:
                val = corr_matrix.loc[col_i, col_j]
                if pd.notna(val):
                    corr_pairs.append(((col_i, col_j), float(val)))
        corr_pairs.sort(key=lambda item: item[1], reverse=True)
        summary["correlations"] = [
            {"variaveis": f"{a} ~ {b}", "correlacao": round(score, 3)}
            for (a, b), score in corr_pairs[:5]
            if score >= 0.2
        ]

    for col in non_numeric_cols:
        series = df[col]
        if series.nunique(dropna=True) < 2 or series.nunique(dropna=True) > 25:
            continue
        for num_col in numeric_cols:
            grouped = df[[col, num_col]].dropna().groupby(col)[num_col]
            if grouped.size().shape[0] < 2:
                continue
            agg = grouped.mean()
            spread = agg.max() - agg.min()
            if spread <= 0:
                continue
            summary["categorical"].append({
                "driver": col,
                "target": num_col,
                "diferenca_media": round(float(spread), 4),
                "categorias": min(int(series.nunique(dropna=True)), 25),
            })

    summary["categorical"] = sorted(summary["categorical"], key=lambda r: r["diferenca_media"], reverse=True)[:5]
    return summary


def compute_advanced_analysis(df: pd.DataFrame) -> Dict[str, Any]:
    numeric_cols = [c for c in df.columns if is_numeric_dtype(df[c])]
    non_numeric_cols = [c for c in df.columns if c not in numeric_cols]

    temporal = detect_temporal_patterns(df, numeric_cols)
    frequencies = identify_value_frequencies(df)
    outliers = detect_outliers(df, numeric_cols)
    clusters = detect_clusters(df, numeric_cols)
    relationships = summarize_relationships(df, numeric_cols, non_numeric_cols)

    return {
        "numeric_cols": numeric_cols,
        "non_numeric_cols": non_numeric_cols,
        "temporal": temporal,
        "frequencies": frequencies,
        "outliers": outliers,
        "clusters": clusters,
        "relationships": relationships,
    }


@dataclass
class TemporalTrend:
    column: str
    description: str

