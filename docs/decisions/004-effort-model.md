# DDR-004 (optional): Rule-based effort estimate for the feasibility gate

- **Status:** Proposed. Tune it against the labelled set.
- **Context:** The feasibility gate compares the estimated build hours with the student's available hours. A model's guess at hours is unstable.
- **Decision:** A base of 40 h, plus fixed hours per detected component (auth +15, payments +30, real-time +35, mobile +50, ML +45, marketplace +60, hardware +70 …), in `services/validators/src/features.py`.
- **Why:** It is deterministic and explainable on the card ("payments +30 h"), and it is unit-tested.
- **Cost:** It is coarse. Clarifying question `must_have` refines it. We re-checked the hours on __ labelled ideas.
