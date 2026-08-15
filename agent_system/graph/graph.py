from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agent_system.config import AgentConfig
from agent_system.graph.agents import (
    CrisisState,
    consensus_node,
    critic_agent,
    macro_agent,
    risk_agent,
    technical_agent,
)
from agent_system.state import AgentState, BotSnapshot


class CrisisGraph:
    """危机深度研判子图（Phase 1）：4 个专家 Agent + 共识节点。"""

    def __init__(self, config: AgentConfig) -> None:
        self.cfg = config
        self._graph = self._build()

    def _build(self) -> Any:
        graph = StateGraph(CrisisState)
        graph.add_node("macro_agent", macro_agent)
        graph.add_node("technical_agent", technical_agent)
        graph.add_node("critic_agent", critic_agent)
        graph.add_node("risk_agent", risk_agent)
        graph.add_node("consensus", consensus_node)

        graph.add_edge(START, "macro_agent")
        graph.add_edge("macro_agent", "technical_agent")
        graph.add_edge("technical_agent", "critic_agent")
        graph.add_edge("critic_agent", "risk_agent")
        graph.add_edge("risk_agent", "consensus")
        graph.add_edge("consensus", END)
        return graph.compile()

    @staticmethod
    def _snapshot_to_dict(snap: BotSnapshot) -> dict[str, Any]:
        return snap.__dict__

    def run(self, agent_state: AgentState) -> AgentState:
        gatekeeper = agent_state.gatekeeper
        crisis_state: CrisisState = {
            "config": self.cfg,
            "bot_snapshots": agent_state.bot_snapshots,
            "gatekeeper": gatekeeper.__dict__ if gatekeeper else {},
            "phase": agent_state.phase,
        }
        result = self._graph.invoke(crisis_state)
        recommendation = result.get("consensus", {}).get("recommendation")
        agent_state.recommendation = recommendation
        agent_state.phase = result.get("phase", agent_state.phase)
        # Stash the full subgraph output for transparency / post-mortem.
        agent_state.reports = {
            k: v
            for k, v in result.items()
            if k not in ("config", "bot_snapshots", "gatekeeper")
        }
        return agent_state
