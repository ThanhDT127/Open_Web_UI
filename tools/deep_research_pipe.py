"""
title: Deep Research Pipeline
author: Antigravity
version: 1.0.0
requirements: requests, beautifulsoup4
"""

import json
import logging
import re
import urllib.parse
from typing import Generator, Union, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Pipe:
    class Valves(BaseModel):
        middleware_url: str = Field(
            default="http://middleware:5000/v1",
            description="Base URL of the Middleware API (internal container address)"
        )
        admin_token: str = Field(
            default="YOUR_SUBKEY_ADMIN",
            description="Admin key for authenticating with the Middleware API"
        )
        searxng_url: str = Field(
            default="http://searxng:8080",
            description="SearXNG internal container URL"
        )
        max_hops: int = Field(
            default=2,
            description="Maximum search iterations (hops)"
        )

    def __init__(self):
        self.valves = self.Valves()

    def _generate_queries(self, prompt: str) -> List[str]:
        """Call LLM via Middleware to generate 3 search queries."""
        url = f"{self.valves.middleware_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.valves.admin_token}",
            "Content-Type": "application/json"
        }
        
        system_prompt = (
            "Bạn là chuyên gia lập kế hoạch tìm kiếm.\n"
            "Từ yêu cầu của người dùng, hãy tạo đúng 3 truy vấn tìm kiếm khác nhau bằng tiếng Việt trên công cụ tìm kiếm để thu thập thông tin.\n"
            "Trả về kết quả dưới dạng danh sách, phân tách bằng dòng mới, KHÔNG đánh số thứ tự, KHÔNG thêm bất kỳ giải thích nào khác."
        )
        
        body = {
            "model": "openai-auto",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=30)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"].strip()
                queries = [q.strip().strip('"').strip("'") for q in content.split("\n") if q.strip()]
                return queries[:3]
        except Exception as e:
            logger.error("Error generating queries: %s", str(e))
        
        # Fallback query
        return [prompt]

    def _search_searxng(self, query: str) -> List[str]:
        """Query SearXNG and return top unique URLs."""
        encoded_query = urllib.parse.quote(query)
        url = f"{self.valves.searxng_url.rstrip('/')}/search?q={encoded_query}&format=json"
        
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                results = res.json().get("results", [])
                urls = []
                for r in results:
                    if r.get("url") and r["url"].startswith("http"):
                        urls.append(r["url"])
                return urls
        except Exception as e:
            logger.error("Error searching SearXNG: %s", str(e))
        return []

    def _crawl_webpage(self, url: str) -> Optional[str]:
        """Crawl a webpage and return clean text."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                
                # Get text and clean up whitespace
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = "\n".join(chunk for chunk in chunks if chunk)
                return text
        except Exception as e:
            logger.error("Error crawling URL %s: %s", url, str(e))
        return None

    def _analyze_gaps(self, prompt: str, crawled_data: List[Dict[str, Any]]) -> List[str]:
        """LLM detects missing info and suggests 2 more queries or 'COMPLETED'."""
        url = f"{self.valves.middleware_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.valves.admin_token}",
            "Content-Type": "application/json"
        }
        
        context_str = "\n".join([
            f"- Nguồn [{i+1}]: {item['url']}\nNội dung sơ bộ: {item['text'][:600]}..."
            for i, item in enumerate(crawled_data)
        ])
        
        system_prompt = (
            "Bạn là một phân tích viên xuất sắc.\n"
            "Hãy đánh giá các nguồn thông tin đã thu thập đối chiếu với câu hỏi của người dùng.\n"
            "Nếu thấy thiếu thông tin quan trọng, hãy sinh ra đúng 2 truy vấn tìm kiếm bổ sung bằng tiếng Việt, phân tách bằng dòng mới, KHÔNG đánh số.\n"
            "Nếu thấy thông tin đã đầy đủ để viết báo cáo sâu sắc, chỉ trả về đúng chữ 'COMPLETED'."
        )
        
        body = {
            "model": "openai-auto",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Câu hỏi của user: {prompt}\n\nThông tin đã cào được:\n{context_str}"}
            ],
            "temperature": 0.2
        }

        try:
            res = requests.post(url, headers=headers, json=body, timeout=30)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"].strip()
                if "COMPLETED" in content:
                    return ["COMPLETED"]
                queries = [q.strip().strip('"').strip("'") for q in content.split("\n") if q.strip()]
                return queries[:2]
        except Exception as e:
            logger.error("Error analyzing gaps: %s", str(e))
        return ["COMPLETED"]

    def _generate_report(self, prompt: str, crawled_data: List[Dict[str, Any]]) -> Generator[str, None, None]:
        """Stream final synthesized report from LLM."""
        url = f"{self.valves.middleware_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.valves.admin_token}",
            "Content-Type": "application/json"
        }
        
        context_str = "\n".join([
            f"Nguồn [{i+1}]: {item['url']}\nNội dung: {item['text']}"
            for i, item in enumerate(crawled_data)
        ])
        
        system_prompt = (
            "Bạn là chuyên gia nghiên cứu và tổng hợp báo cáo.\n"
            "Hãy soạn thảo một báo cáo nghiên cứu cực kỳ chi tiết, khách quan, và sâu sắc bằng tiếng Việt cho chủ đề được yêu cầu.\n\n"
            "YÊU CẦU BẮT BUỘC:\n"
            "1) Trả về báo cáo có cấu trúc Markdown chuyên nghiệp, rõ ràng (Heading, bullet points, table nếu cần).\n"
            "2) Các luận điểm, số liệu phải có chú thích nguồn cụ thể dạng [1], [2],... tương ứng với số thứ tự nguồn bên dưới.\n"
            "3) Cuối báo cáo, thêm phần 'Tài liệu tham khảo' dạng danh sách liệt kê số thứ tự [1], [2] tương ứng với liên kết URL nguồn.\n"
            "4) Chỉ sử dụng thông tin từ tài liệu nguồn đã thu thập."
        )
        
        body = {
            "model": "openai-auto",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Chủ đề nghiên cứu: {prompt}\n\nDữ liệu nguồn:\n{context_str}"}
            ],
            "temperature": 0.3,
            "stream": True
        }

        try:
            res = requests.post(url, headers=headers, json=body, stream=True, timeout=60)
            if res.status_code == 200:
                for line in res.iter_lines():
                    if line:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data:"):
                            data_content = line_str[5:].strip()
                            if data_content == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_content)
                                chunk = data_json["choices"][0]["delta"].get("content", "")
                                if chunk:
                                    yield chunk
                            except Exception:
                                pass
            else:
                yield f"❌ Lỗi tổng hợp báo cáo từ LLM ({res.status_code}): {res.text}"
        except Exception as e:
            yield f"❌ Lỗi kết nối LLM: {str(e)}"

    def pipe(
        self,
        body: dict,
        __user__: dict = None,
        __event_emitter__=None,
    ) -> Union[str, Generator]:
        messages = body.get("messages", [])
        if not messages:
            return "Không tìm thấy nội dung yêu cầu."

        last_user_msg = messages[-1].get("content", "")
        
        def generator():
            # Send initial thinking progress
            yield "<thinking>\n🔍 Khởi chạy Deep Research Agent...\n"
            
            # Hop 1 Planning
            yield "📋 Bước 1: Lập kế hoạch & Tạo truy vấn tìm kiếm (Hop 1)...\n"
            queries = self._generate_queries(last_user_msg)
            queries_str = ", ".join(f'"{q}"' for q in queries)
            yield f"Các truy vấn: {queries_str}\n"
            
            crawled_data = []
            crawled_urls = set()
            
            # Search & crawl Hop 1
            for q in queries:
                yield f"🔎 Đang tìm kiếm: \"{q}\"...\n"
                urls = self._search_searxng(q)
                for url in urls[:2]:
                    if url not in crawled_urls:
                        crawled_urls.add(url)
                        yield f"📥 Đang cào nguồn: {url}...\n"
                        text = self._crawl_webpage(url)
                        if text:
                            # Keep first 3000 chars of each page
                            crawled_data.append({"url": url, "text": text[:3000]})
            
            # Hop 2 Gap analysis
            if self.valves.max_hops > 1 and crawled_data:
                yield "📊 Bước 2: Phân tích khoảng trống thông tin (Gap Analysis)...\n"
                gap_queries = self._analyze_gaps(last_user_msg, crawled_data)
                
                if gap_queries and gap_queries != ["COMPLETED"]:
                    gap_queries_str = ", ".join(f'"{q}"' for q in gap_queries)
                    yield f"🔍 Phát hiện thông tin còn thiếu. Tìm kiếm bổ sung: {gap_queries_str}\n"
                    for q in gap_queries:
                        yield f"🔎 Đang tìm kiếm thêm: \"{q}\"...\n"
                        urls = self._search_searxng(q)
                        for url in urls[:2]:
                            if url not in crawled_urls:
                                crawled_urls.add(url)
                                yield f"📥 Đang cào thêm: {url}...\n"
                                text = self._crawl_webpage(url)
                                if text:
                                    crawled_data.append({"url": url, "text": text[:3000]})
                else:
                    yield "✅ Thông tin đầy đủ. Chuyển sang tổng hợp báo cáo.\n"
            
            yield "📝 Bước 3: Đang tổng hợp báo cáo chi tiết kèm trích dẫn...\n"
            yield "</thinking>\n\n"
            
            # Synthesize final report
            if not crawled_data:
                yield "❌ Không thu thập được thông tin nào từ các nguồn tìm kiếm."
                return
                
            report_gen = self._generate_report(last_user_msg, crawled_data)
            for chunk in report_gen:
                yield chunk

        return generator()
