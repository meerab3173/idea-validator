# DDR-001: The verdict comes from deterministic code, not from a model

- **Status:** Accepted
- **Context:** The language model's scores drift and are hard to explain. The brief says the model must never output the verdict, and the verdict must be repeatable and testable.
- **Options:** (1) Ask the LLM for GO/NO-GO directly. (2) LLM gives scores, then a weighted sum in code. (3) LLM gives evidence-backed scores, then code applies hard gates, weights, thresholds, a confidence rule and a sensitivity check.
- **Decision:** Option 3, implemented in `services/verdict/src/engine.py` (M11), with the rules in a ConfigMap (`config/verdict.yaml`).
- **Why:** Same input gives the same output (tested in `test_same_input_same_output`). Every gate, threshold edge and what-if has a unit test (38 tests). The worked example from the brief (70.5, GO, BORDERLINE; Competition 3.0 → 73.5, stable GO) reproduces exactly.
- **Cost:** We have to define and defend the weights and thresholds ourselves, and tune them on a labelled set (see DDR-003).
- **AI use:** Drafted with AI help. We checked the formulas against Section 5 of the brief and the test numbers by hand.
