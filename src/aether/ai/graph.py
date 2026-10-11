from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from aether.ai import edges, nodes
from aether.ai.state import InteractionState


def build_interact_graph():
    """Compile the act-one interaction graph."""
    graph = StateGraph(InteractionState)

    graph.add_node("gather_context", nodes.gather_context)
    graph.add_node("decide_next_action", nodes.decide_next_action)
    graph.add_node("validate_action", nodes.validate_action)
    graph.add_node("execute_action", nodes.execute_action)
    graph.add_node("generate_dialogue", nodes.generate_dialogue)

    graph.set_entry_point("gather_context")
    graph.add_edge("gather_context", "decide_next_action")
    graph.add_conditional_edges(
        "decide_next_action",
        edges.after_decide,
        {
            "validate_action": "validate_action",
            "__end__": END,
        },
    )
    graph.add_conditional_edges(
        "validate_action",
        edges.after_validate,
        {
            "execute_action": "execute_action",
            "decide_next_action": "decide_next_action",
        },
    )
    graph.add_conditional_edges(
        "execute_action",
        edges.after_execute,
        {
            "generate_dialogue": "generate_dialogue",
            "decide_next_action": "decide_next_action",
        },
    )
    graph.add_edge("generate_dialogue", "decide_next_action")

    return graph.compile()


@lru_cache(maxsize=1)
def get_interact_graph():
    return build_interact_graph()


def clear_interact_graph_cache() -> None:
    """Drop the compiled graph cache (useful after code reloads in tests)."""
    get_interact_graph.cache_clear()
