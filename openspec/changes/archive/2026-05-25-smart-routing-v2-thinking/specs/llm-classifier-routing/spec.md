# llm-classifier-routing

## Requirements

1. When heuristic complexity score falls in ambiguous range (3-7), middleware MUST call an LLM classifier to determine the correct tier.
2. Classifier MUST use the cheapest available model (`chat-gemini-2.5-flash`).
3. Classifier prompt MUST be ≤150 tokens and return exactly one word: SIMPLE, MEDIUM, COMPLEX, or REASONING.
4. Classifier call MUST have a timeout of 2 seconds.
5. If classifier call fails (timeout, error, invalid response), middleware MUST fall back to heuristic result.
6. Requests with clear heuristic scores (≤2 or ≥8) MUST skip the classifier (0 latency, 0 cost).
7. Classifier decision MUST be logged in audit trail for monitoring and tuning.
8. Classifier MUST NOT be called for non-auto-model requests.
