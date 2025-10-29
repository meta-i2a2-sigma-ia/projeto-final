"""Base helpers for constructing LangChain agents in the EDA app."""

from __future__ import annotations

from typing import Any, Sequence

from langchain.agents import AgentType, initialize_agent
try:
    from langchain.memory import ConversationBufferMemory
except ModuleNotFoundError:
    try:
        from langchain.chains.conversation.memory import ConversationBufferMemory  # type: ignore
    except ModuleNotFoundError:
        try:
            from langchain_core.memory import ConversationBufferMemory  # type: ignore
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "Não foi possível importar ConversationBufferMemory. Verifique a instalação do pacote 'langchain'."
            ) from exc
from langchain.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel


def build_agent(
    *,
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    memory: ConversationBufferMemory,
    verbose: bool = False,
) -> Any:
    """Create a conversational ReAct agent with the supplied tools."""

    agent = initialize_agent(
        tools=list(tools),
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        verbose=verbose,
        memory=memory,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )
    return agent
