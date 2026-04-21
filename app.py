"""
Example application demonstrating LLM and Search providers.
"""
import asyncio

from config import Config
from search import search, get_providers as get_search_providers
from constants import PROVIDERS, SEARCH_PROVIDERS


async def demo_llm():
    """Demonstrate LLM providers"""
    print("=" * 60)
    print("LLM PROVIDERS DEMO")
    print("=" * 60)
    
    config = Config()
    available_providers = config.list_providers()
    print(f"\nAvailable LLM providers: {available_providers}")
    
    if not available_providers:
        print("\nNo LLM providers configured. Please set API keys in .env file:")
        for provider_key, provider_info in PROVIDERS.items():
            api_key = provider_info["api_key_env"]
            print(f"  - {api_key} for {provider_info['name']}")
        return
    
    # Use the first available provider
    provider_name = available_providers[0]
    provider = config.get_provider(provider_name)
    
    prompt = "Explain machine learning in one sentence."
    
    try:
        print(f"\nUsing provider: {provider_name}")
        print(f"Prompt: {prompt}")
        response = await provider.generate(prompt)
        print(f"Response: {response}")
    except Exception as e:
        print(f"Error: {e}")


async def demo_search():
    """Demonstrate Search providers"""
    print("\n" + "=" * 60)
    print("SEARCH PROVIDERS DEMO")
    print("=" * 60)
    
    available_providers = get_search_providers()
    print(f"\nAvailable search providers: {available_providers}")
    
    if not available_providers:
        print("No search providers available!")
        return
    
    # Use DuckDuckGo (always available)
    query = "artificial intelligence"
    provider = "duckduckgo"
    
    try:
        print(f"\nSearching: '{query}'")
        print(f"Provider: {provider}")
        print("\nResults:")
        print("-" * 60)
        
        results = await search(query, provider=provider, num_results=3)
        
        for result in results:
            print(f"\n{result.position}. {result.title}")
            print(f"   URL: {result.url}")
            print(f"   Description: {result.description[:100]}...")
    except Exception as e:
        print(f"Error: {e}")


async def demo_integrated():
    """Demonstrate integrated LLM + Search usage"""
    print("\n" + "=" * 60)
    print("INTEGRATED LLM + SEARCH DEMO")
    print("=" * 60)
    
    config = Config()
    llm_providers = config.list_providers()
    search_providers = get_search_providers()
    
    if not llm_providers or not search_providers:
        print("Missing providers. Configure API keys in .env file.")
        return
    
    # Search for information
    query = "Python asyncio"
    print(f"\nSearching for: '{query}'")
    
    try:
        search_results = await search(query, provider="duckduckgo", num_results=2)
        
        # Use LLM to summarize first result
        if search_results:
            first_result = search_results[0]
            llm_provider = config.get_provider(llm_providers[0])
            
            summary_prompt = f"Summarize this in 2 sentences: {first_result.description}"
            print(f"\nUsing {llm_providers[0]} to summarize search result...")
            
            summary = await llm_provider.generate(summary_prompt)
            print(f"\nSummary: {summary}")
    except Exception as e:
        print(f"Error: {e}")


async def main():
    """Main demonstration function"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 58 + "║")
    print("║" + "  SELF-LEARNING AGENT - LLM & SEARCH DEMO".center(58) + "║")
    print("║" + " " * 58 + "║")
    print("╚" + "=" * 58 + "╝")
    
    await demo_llm()
    await demo_search()
    await demo_integrated()
    
    print("\n" + "=" * 60)
    print("DEMO COMPLETED")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
