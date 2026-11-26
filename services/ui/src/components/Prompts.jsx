import { useState } from "react";

// U4: the system states the cost and waits before going over budget.
export function ApprovalPrompt({ request, onDecide }) {
  if (!request) return null;
  return (
    <section className="card approval" role="dialog" aria-label="approval needed">
      <p>
        Not enough evidence yet. A deep search of about <b>{request.pages}</b> pages would cost about{" "}
        <b>${Number(request.estimated_cost_usd).toFixed(3)}</b>. You have spent ${Number(request.spent).toFixed(3)} of
        your ${Number(request.budget).toFixed(2)} budget.
      </p>
      <button onClick={() => onDecide(true)}>Approve deep search</button>{" "}
      <button className="secondary" onClick={() => onDecide(false)}>Decline</button>
    </section>
  );
}

// U5: only questions that change the result are asked.
export function ClarifyForm({ questions, onSubmit }) {
  const [answers, setAnswers] = useState({});
  if (!questions || !questions.length) return null;
  return (
    <form className="card" aria-label="clarifying questions"
      onSubmit={(e) => { e.preventDefault(); onSubmit(answers); }}>
      {questions.map((q) => (
        <label key={q.id}>{q.question}
          <input required value={answers[q.id] || ""} onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })} />
        </label>
      ))}
      <button type="submit">Continue</button>
    </form>
  );
}
