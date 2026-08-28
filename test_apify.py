import asyncio
import os
import sys

# Add backend to path if run from project root
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from backend.agents.research import fetch_wikipedia_summary, fetch_apify_fallback, _MAX_SCRAPED_CHARS
import backend.agents.research as research_module

async def test_fallbacks():
    print("Testing Wikipedia (Primary):")
    wiki = await fetch_wikipedia_summary("Artificial Intelligence")
    print(f"Wiki result length: {len(wiki)}")
    print(wiki[:200] + ("..." if len(wiki) > 200 else ""))
    
    print("\nSimulating Wikipedia failure & Testing Apify Fallback:")
    # We don't have APIFY_API_TOKEN set, so it should cleanly warn and return ""
    apify = await fetch_apify_fallback("Artificial Intelligence market size")
    if apify:
        print(f"Apify result length: {len(apify)}")
        print(apify[:200] + ("..." if len(apify) > 200 else ""))
    else:
        print("Apify fallback returned empty (expected if no API key).")
        
    print(f"\nTruncation check: Max chars allowed = {_MAX_SCRAPED_CHARS}")
    if len(wiki) > 0 and len(wiki) <= _MAX_SCRAPED_CHARS + 100: # +100 for Source header formatting
        print("Truncation is working.")
    else:
        print(f"Truncation MIGHT NOT be working. Length is {len(wiki)}.")
        
    print("\nPhase 4 Tests Completed.")

if __name__ == "__main__":
    asyncio.run(test_fallbacks())
