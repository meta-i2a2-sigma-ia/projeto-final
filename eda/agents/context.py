"""Shared mutable context for EDA agent tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class AgentDataContext:
    """Holds the dataframe currently usado pelos agentes e metadados auxiliares."""

    df: Optional[pd.DataFrame] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def require_dataframe(self) -> pd.DataFrame:
        """Return the active dataframe or raise a user-friendly error."""

        if self.df is None:
            raise ValueError("Nenhum dataset carregado no contexto do agente.")
        if isinstance(self.df, pd.DataFrame) and self.df.empty:
            raise ValueError("O dataset carregado está vazio.")
        return self.df

    def bump_version(self) -> None:
        """Increment the internal version to sinalizar mudança de dataset."""

        self.version += 1
