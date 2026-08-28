import asyncio
import os
import sys

sys.path.append(os.path.dirname(__file__))

from backend.agents.planner import planner_agent
from backend.agents.research import research_agent
from backend.agents.analyst import analyst_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.writer import writer_agent

async def test():
    topic = "I sell vegetables, make about ₹400/day"
    print("--- PLANNER ---")
    plan = await planner_agent(topic)
    print(plan)
    
    print("\n--- RESEARCH ---")
    r_task = f"Gather data on product/service and business model for {topic}"
    r_out = await research_agent(r_task)
    print(r_out)
    
    print("\n--- ANALYST ---")
    a_task = f"Analyze daily/monthly income metrics for {topic}"
    a_out = await analyst_agent(a_task)
    print(a_out)
    
    print("\n--- OPPORTUNITY ---")
    o_task = f"Recommend schemes based on formal registration status for {topic}\n\nContext: {a_out}"
    o_out = await opportunity_agent(o_task)
    print(o_out)
    
    print("\n--- WRITER ---")
    w_task = f"Topic: {topic}\n\nAccumulated Findings:\n{r_out}\n\n{a_out}\n\n{o_out}\n\nWrite a comprehensive Loan Readiness Advisory report in Markdown."
    w_out = await writer_agent(w_task)
    print(w_out)

if __name__ == "__main__":
    asyncio.run(test())
