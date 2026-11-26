# DDR-003: All internet traffic, including hosted-model calls, goes through M5

- **Status:** Accepted
- **Context:** The brief says only M5 may reach the internet (NetworkPolicy). Agents also need a hosted LLM for drafting labels, the Skeptic and the fallback scorer.
- **Options:** (1) Let every agent pod call the LLM API directly and add egress exceptions. (2) Route LLM calls through M5's `/llm/v1/chat/completions` proxy.
- **Decision:** Option 2. The LLM API key is only in the tools pod's Secret. Agents use `LLM_BASE_URL=http://tools:8000/llm/v1`.
- **Why:** One egress point keeps the NetworkPolicy simple (default deny, plus internet only for `egress=internet` pods). Rate limits, the allow-list and metrics apply to model calls as well. A leaked agent pod has no API key.
- **Cost:** One extra network hop (~__ ms). If M5 is down, both scouting and the hosted fallback stop. It runs with probes and can be scaled.
- **AI use:** Drafted with AI help. We reviewed it and tested it with `scripts/netpol_test.sh`.
