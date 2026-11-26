// U6, U7, U8, U10: verdict, gates, six scores with evidence links, weights,
// confidence, stability, challenge buttons and "what would make this GO?".
const LABELS = {
  demand_pain: "Demand and pain", competition: "Competition", differentiation: "Differentiation",
  feasibility: "Feasibility for you", risk: "Risk", learning: "Learning and portfolio value",
};
const COLORS = { GO: "#1a7f37", PIVOT: "#9a6700", "NO-GO": "#cf222e", INSUFFICIENT_EVIDENCE: "#57606a" };

export default function VerdictCard({ card, onChallenge, onWhatIf, busy }) {
  if (!card) return null;
  const ev = Object.fromEntries((card.evidence || []).map((e) => [e.evidence_id, e]));
  const insufficient = card.verdict === "INSUFFICIENT_EVIDENCE";
  return (
    <section className="card" aria-label="verdict card">
      <header className="verdict-head">
        <span className="badge" style={{ background: COLORS[card.verdict] }} data-testid="verdict">
          {card.verdict.replace("_", " ")}
        </span>
        {card.stability === "BORDERLINE" && <span className="badge warn">BORDERLINE</span>}
        {card.cache_hit && <span className="badge muted" title="served from cache">cached</span>}
        {card.score != null && <span className="score">Score {card.score} / 100</span>}
        <span className="conf">Confidence {Math.round((card.confidence || 0) * 100)}%</span>
        {card.version > 1 && <span className="badge muted">version {card.version}</span>}
      </header>
      <p className="reason">{card.reason}</p>

      {insufficient && (
        <div className="missing" role="alert">
          <strong>Why we did not decide:</strong>
          <ul>{(card.missing || []).map((m) => <li key={m}>{m}</li>)}</ul>
          <small>The system abstains instead of guessing.</small>
        </div>
      )}

      <h4>Gates</h4>
      <ul className="gates">
        {Object.entries(card.gates || {}).map(([g, v]) => (
          <li key={g} className={v}>
            {g}: <b>{v}</b>{card.gate_messages && card.gate_messages[g] ? ` — ${card.gate_messages[g]}` : ""}
          </li>
        ))}
      </ul>

      {!insufficient && (
        <>
          <h4>Six dimensions</h4>
          <table className="scores">
            <thead><tr><th>Dimension</th><th>Score</th><th>Weight</th><th>Conf.</th><th>Evidence</th><th /></tr></thead>
            <tbody>
              {(card.scores || []).map((s) => (
                <tr key={s.dimension} data-testid={`row-${s.dimension}`}>
                  <td title={s.reason}>{LABELS[s.dimension] || s.dimension}</td>
                  <td>{s.score.toFixed(1)}</td>
                  <td>{card.weights ? card.weights[s.dimension] : ""}</td>
                  <td>{Math.round(s.confidence * 100)}%</td>
                  <td>
                    {(s.evidence_ids || []).map((id) => (
                      <a key={id} href={ev[id] ? ev[id].url : "#"} target="_blank" rel="noreferrer" title={ev[id] ? ev[id].quote : id}>
                        [{id.split("#")[0].slice(-4)}]
                      </a>
                    ))}
                  </td>
                  <td>
                    {onChallenge && (
                      <button disabled={busy} onClick={() => onChallenge(s.dimension)}>Challenge</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {card.sensitivity && card.sensitivity.flips && card.sensitivity.flips.length > 0 && (
        <details>
          <summary>What flips it ({card.sensitivity.flipped} of {card.sensitivity.runs} checks)</summary>
          <ul>{card.sensitivity.flips.map((f) => <li key={f.change}>{f.change} → {f.new_verdict}</li>)}</ul>
        </details>
      )}

      {(card.what_would_make_go || []).length > 0 && (
        <div className="whatif">
          <h4>What would make this GO?</h4>
          <ul>
            {card.what_would_make_go.slice(0, 3).map((w) => (
              <li key={w.change}>{w.change}{w.new_score ? ` → ${w.new_score} (${w.stable ? "stable" : "borderline"} GO)` : ""}</li>
            ))}
          </ul>
          {onWhatIf && <button disabled={busy} onClick={onWhatIf}>Suggest concrete changes</button>}
        </div>
      )}

      {(card.objections || []).length > 0 && (
        <details>
          <summary>Skeptic objections ({card.objections.filter((o) => o.supported).length} accepted)</summary>
          <ul>{card.objections.map((o, i) => <li key={i} className={o.supported ? "" : "struck"}>{o.text}</li>)}</ul>
        </details>
      )}
      <small className="versions">
        engine {card.versions && card.versions.engine} · rubrics {card.versions && card.versions.rubrics} · weights {card.versions && card.versions.profile_weights}
      </small>
    </section>
  );
}
