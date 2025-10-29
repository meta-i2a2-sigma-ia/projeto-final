"""Base helpers for constructing LangChain agents in the fiscal module."""

from __future__ import annotations

from typing import Any, Optional, Sequence

from langchain.agents import AgentType, initialize_agent
from langchain.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel


def build_agent(
    *,
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    memory: Optional[object] = None,
    verbose: bool = False,
) -> Any:
    init_kwargs = dict(
        tools=list(tools),
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=verbose,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )
    if memory is not None:
        init_kwargs["memory"] = memory
    agent = initialize_agent(**init_kwargs)
    return agent
