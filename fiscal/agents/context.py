"""Shared mutable context used by fiscal agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class AgentDataContext:
    """Encapsula o dataframe fiscal e metadados auxiliares."""

    df: Optional[pd.DataFrame] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def require_dataframe(self) -> pd.DataFrame:
        if self.df is None:
            raise ValueError("Nenhum conjunto de dados fiscal carregado.")
        if isinstance(self.df, pd.DataFrame) and self.df.empty:
            raise ValueError("O dataset fiscal carregado está vazio.")
        return self.df

    def bump_version(self) -> None:
        self.version += 1
