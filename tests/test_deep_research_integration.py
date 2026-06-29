"""
Integration tests for Deep Research Pipe.
Runs inside the openwebui-app container.
"""

import os
import sys
import asyncio
import requests

# Add /tmp to python path so it can import the tools copied there
sys.path.insert(0, "/tmp")

from deep_research_pipe import Pipe


async def run_integration_test():
    print("Running Deep Research Pipe integration test...")
    
    pipe = Pipe()
    pipe.valves.middleware_url = "http://middleware:5000/v1"
    pipe.valves.admin_token = "YOUR_SUBKEY_ADMIN"
    pipe.valves.searxng_url = "http://searxng:8080"
    
    # 1. Mock SearXNG to return constant URLs
    def mock_search_searxng(query):
        print(f"Mock Search SearXNG for query: {query}")
        return ["https://example.com/item1", "https://example.com/item2"]
        
    pipe._search_searxng = mock_search_searxng
    
    # 2. Mock page crawling to return realistic text
    def mock_crawl_webpage(url):
        print(f"Mock Crawl Webpage for URL: {url}")
        return f"Nội dung cào từ trang {url}: Thị trường xe điện tại Việt Nam năm 2026 tiếp tục tăng trưởng mạnh mẽ với sự tham gia của VinFast và các hãng xe Trung Quốc. Hạ tầng trạm sạc đang phủ rộng."
        
    pipe._crawl_webpage = mock_crawl_webpage
    
    # 3. Call the pipe generator
    body = {
        "messages": [
            {"role": "user", "content": "Nghiên cứu thị trường xe điện Việt Nam 2026"}
        ]
    }
    
    # pipe returns a generator
    generator = pipe.pipe(body)
    
    output_chunks = []
    print("Streaming generator output:")
    for chunk in generator:
        output_chunks.append(chunk)
        print(chunk, end="", flush=True)
        
    full_output = "".join(output_chunks)
    
    print("\nVerifying output content...")
    if "<thinking>" not in full_output:
        raise Exception("Missing <thinking> block in output")
    if "</thinking>" not in full_output:
        raise Exception("Missing </thinking> block in output")
    if "Tài liệu tham khảo" not in full_output:
        raise Exception("Missing 'Tài liệu tham khảo' section in generated report")
        
    print("Integration test checks: PASSED")
    print("All integration checks completed successfully!")


if __name__ == "__main__":
    asyncio.run(run_integration_test())
