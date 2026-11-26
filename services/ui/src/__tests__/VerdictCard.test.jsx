import { render, screen, fireEvent } from "@testing-library/react";
import VerdictCard from "../components/VerdictCard";

const dims = ["demand_pain", "competition", "differentiation", "feasibility", "risk", "learning"];
const base = {
  idea_id: "i1", run_id: "r1", version: 1, verdict: "GO", stability: "BORDERLINE", score: 70.5, confidence: 0.74,
  gates: { evidence: "pass", feasibility: "pass", risk: "pass", duplicate: "pass" },
  weights: { demand_pain: 15, competition: 15, differentiation: 15, feasibility: 25, risk: 10, learning: 20 },
  scores: dims.map((d) => ({ dimension: d, score: 3, confidence: 0.7, evidence_ids: ["card_ab12#c0"], reason: "r" })),
  evidence: [{ evidence_id: "card_ab12#c0", url: "https://news.ycombinator.com/item?id=1", quote: "slow export" }],
  sensitivity: { runs: 14, flipped: 1, flips: [{ change: "weight feasibility x0.80", new_verdict: "PIVOT" }] },
  what_would_make_go: [{ change: "Raise competition from 2.0 to 3.0", new_score: 73.5, stable: true }],
  versions: { engine: "m11@v1", rubrics: "r1", profile_weights: "w1" },
};

test("shows verdict, borderline, six scores with evidence links and weights", () => {
  render(<VerdictCard card={base} />);
  expect(screen.getByTestId("verdict")).toHaveTextContent("GO");
  expect(screen.getByText("BORDERLINE")).toBeInTheDocument();
  dims.forEach((d) => expect(screen.getByTestId(`row-${d}`)).toBeInTheDocument());
  expect(screen.getAllByRole("link")[0]).toHaveAttribute("href", "https://news.ycombinator.com/item?id=1");
  expect(screen.getByText(/Confidence 74%/)).toBeInTheDocument();
  expect(screen.getByText(/Raise competition/)).toBeInTheDocument();
});

test("challenge button sends the dimension", () => {
  const onChallenge = vi.fn();
  render(<VerdictCard card={base} onChallenge={onChallenge} />);
  fireEvent.click(screen.getAllByText("Challenge")[1]);
  expect(onChallenge).toHaveBeenCalledWith("competition");
});

test("INSUFFICIENT EVIDENCE says what was missing and shows no scores", () => {
  const card = { ...base, verdict: "INSUFFICIENT_EVIDENCE", score: null, stability: "STABLE",
    missing: ["Found 1 independent sources on 1 platforms; need 3+ sources on 2+ platforms."],
    gates: { evidence: "fail" }, what_would_make_go: [], sensitivity: {} };
  render(<VerdictCard card={card} />);
  expect(screen.getByRole("alert")).toHaveTextContent("need 3+ sources");
  expect(screen.queryByTestId("row-demand_pain")).toBeNull();
});
