"""Base helpers for constructing LangChain agents in the EDA app."""

from __future__ import annotations

from typing import Sequence

from langchain.agents import AgentExecutor, AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain.tools import BaseTool
from langchain_core.language_models import BaseLanguageModel


def build_agent(
    *,
    llm: BaseLanguageModel,
    tools: Sequence[BaseTool],
    memory: ConversationBufferMemory,
    verbose: bool = False,
) -> AgentExecutor:
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
