import { render, screen, fireEvent } from "@testing-library/react";
import { ApprovalPrompt, ClarifyForm } from "../components/Prompts";
import LivePanel from "../components/LivePanel";

test("approval prompt states the cost and waits for a decision", () => {
  const onDecide = vi.fn();
  render(<ApprovalPrompt request={{ pages: 20, estimated_cost_usd: 0.04, spent: 0.01, budget: 0.05 }} onDecide={onDecide} />);
  expect(screen.getByRole("dialog")).toHaveTextContent("$0.040");
  fireEvent.click(screen.getByText("Decline"));
  expect(onDecide).toHaveBeenCalledWith(false);
});

test("clarify form submits answers", () => {
  const onSubmit = vi.fn();
  render(<ClarifyForm questions={[{ id: "target_user", question: "Who is the user?" }]} onSubmit={onSubmit} />);
  fireEvent.change(screen.getByLabelText(/Who is the user/), { target: { value: "students" } });
  fireEvent.click(screen.getByText("Continue"));
  expect(onSubmit).toHaveBeenCalledWith({ target_user: "students" });
});

test("live panel shows current agent and spend", () => {
  render(<LivePanel events={[{ type: "transition", from: "EVIDENCE", to: "SCORING", spend: 0.0012 },
    { type: "score", dimension: "risk", score: 4 }]} />);
  expect(screen.getByTestId("spend")).toHaveTextContent("0.0012");
  expect(screen.getByText(/risk = 4/)).toBeInTheDocument();
});
