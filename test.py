from ddgs import DDGS

def search_duckduckgo(query, max_results=5):
    results = []
    
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r["title"],
                "link": r["href"],
                "snippet": r["body"]
            })

    return results


# Example usage
if __name__ == "__main__":
    results = search_duckduckgo("RAG chatbot architecture")
    
    for r in results:
        print(r)