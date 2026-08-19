import asyncio
import logging
import urllib.parse
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

async def fetch_wikipedia_summary(query: str) -> str:
    """Uses BeautifulSoup to search and scrape Wikipedia for the topic"""
    try:
        url = f"https://en.wikipedia.org/w/index.php?search={urllib.parse.quote(query)}&title=Special%3ASearch&profile=advanced&fulltext=1"
        headers = {"User-Agent": "Mozilla/5.0 MarketResearchAgent/1.0"}
        
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url, headers=headers)
            soup = BeautifulSoup(resp.text, 'lxml')
            
            # Find first search result
            results = soup.find_all('div', class_='mw-search-result-heading')
            if not results:
                return ""
            
            first_link = results[0].find('a')['href']
            page_url = f"https://en.wikipedia.org{first_link}"
            
            # Scrape page
            page_resp = await client.get(page_url, headers=headers)
            page_soup = BeautifulSoup(page_resp.text, 'lxml')
            
            # Extract main paragraphs
            content_div = page_soup.find('div', id='mw-content-text')
            if not content_div:
                return ""
                
            paragraphs = content_div.find_all('p', recursive=True)
            text = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            return f"Source: {page_url}\n\nContent Summary:\n{text[:1500]}..."
    except Exception as e:
        logger.warning(f"Wikipedia scrape failed: {e}")
        return ""

async def research_agent(task: str) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    
    # 1. Scrape data to avoid relying purely on LLM knowledge
    scraped_data = await fetch_wikipedia_summary(task)
    
    if not scraped_data:
        scraped_data = "No external data could be retrieved. Rely on internal knowledge."

    messages = [
        {
            "role": "system",
            "content": (
                "Market research analyst. Provide concise, data-driven insights. "
                "Structure: Market Metrics (TAM/CAGR/key players) | Key Trends | Top Sources. "
                "Use bullet points. Be brief and factual. "
                "Use the provided scraped research data to form your response. "
                "If the data is insufficient, use your own knowledge."
            )
        },
        {
            "role": "user",
            "content": f"Date: {today}.\nTask: {task}\n\nScraped Research Data:\n{scraped_data}"
        }
    ]
    
    try:
        # 2. Call LLM with lower token limits to avoid exhaustion
        return await call_llm(messages, temperature=0.5, max_tokens=600)
    except Exception as e:
        logger.error(f"LLM call failed during research: {e}")
        # 3. Fallback mechanism when OpenRouter connection fails or tokens exhausted
        fallback = (
            "### Market Research (Fallback Mode)\n\n"
            "*Note: AI synthesis failed due to API connection issues. Displaying raw scraped data instead.*\n\n"
        )
        if "No external data" not in scraped_data:
            fallback += scraped_data
        else:
            fallback += "Failed to retrieve both AI insights and external scraped data."
            
        return fallback
