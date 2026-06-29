"""
Unit tests for the Deep Research Pipe class.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from deep_research_pipe import Pipe


class DeepResearchTests(unittest.TestCase):
    def setUp(self):
        self.pipe = Pipe()
        self.pipe.valves.middleware_url = "http://mock-middleware:5000/v1"
        self.pipe.valves.admin_token = "mock-token"
        self.pipe.valves.searxng_url = "http://mock-searxng:8080"

    @patch("requests.post")
    def test_generate_queries(self, mock_post):
        # Mock successful LLM query generation response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "query 1\nquery 2\nquery 3"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        queries = self.pipe._generate_queries("test prompt")
        self.assertEqual(len(queries), 3)
        self.assertEqual(queries, ["query 1", "query 2", "query 3"])

    @patch("requests.get")
    def test_search_searxng(self, mock_get):
        # Mock successful SearXNG search results
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {"url": "https://example.com/site1"},
                {"url": "https://example.com/site2"}
            ]
        }
        mock_get.return_value = mock_response

        urls = self.pipe._search_searxng("test query")
        self.assertEqual(len(urls), 2)
        self.assertEqual(urls, ["https://example.com/site1", "https://example.com/site2"])

    @patch("requests.get")
    def test_crawl_webpage(self, mock_get):
        # Mock successful HTML crawling
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = (
            "<html><head><title>Test Page</title></head><body>"
            "<nav>Menu items</nav>"
            "<h1>Article Title</h1>"
            "<p>This is the main body text of the article.</p>"
            "<footer>Footer content</footer></body></html>"
        )
        mock_get.return_value = mock_response

        text = self.pipe._crawl_webpage("https://example.com/article")
        self.assertIsNotNone(text)
        self.assertIn("Article Title", text)
        self.assertIn("This is the main body text of the article.", text)
        # Verify navigation and footer elements are stripped
        self.assertNotIn("Menu items", text)
        self.assertNotIn("Footer content", text)

    @patch("requests.post")
    def test_analyze_gaps_completed(self, mock_post):
        # Mock gap analysis returning 'COMPLETED'
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "COMPLETED"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        gaps = self.pipe._analyze_gaps("prompt", [{"url": "url", "text": "text"}])
        self.assertEqual(gaps, ["COMPLETED"])


if __name__ == "__main__":
    unittest.main()
