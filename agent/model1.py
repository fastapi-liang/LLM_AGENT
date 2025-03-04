from langgraph.constants import END
from langgraph.graph import StateGraph
from typing import TypedDict
from langchain.tools import BaseTool, tool
from pydantic import BaseModel, Field
# pip install -U langchain-community tavily-python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

class Overview(BaseModel):
    """Overview of a section of text."""
    summary: str = Field(description="Provide a concise summary of the content.")
    language: str = Field(description="Provide the language that the content is written in.")
    keywords: str = Field(description="Provide keywords related to the content.")

@tool("overview", args_schema=Overview)
def overview(summary: str, language: str, keywords: str):
    """Overview of a section of text."""
    return "Summary: {a}\nLanguage: {b}\nKeywords: {c}".format(a=summary, b=language, c=keywords)
tools =[overview]


class MyState(TypedDict):  #
    i: int
    j: int

# Functions on **nodes**
def fn1(state: MyState):
    print(f"Enter fn1: {state['i']}")
    return {"i": 1}

def fn2(state: MyState):
    i = state["i"]
    return {"i": i+1}

# Conditional **edge** function
def is_big_enough(state: MyState):
    if state["i"] > 10:
        return END
    else:
        return "n2"

# The Graph!  The "Program" !!
workflow = StateGraph(MyState)

workflow.add_node("n1", fn1)
workflow.add_node("n2", fn2)
workflow.set_entry_point("n1")

workflow.add_edge("n1", "n2")
workflow.add_conditional_edges(
    source="n2", path=is_big_enough
)

# Compile, and then run
graph = workflow.compile()
graph.get_graph().draw_mermaid_png(output_file_path="graph.png")

r = graph.invoke({"i": 1000, "j": 123})
print(r)