import { useState } from "react";
import { api, getToken, streamRun } from "./api";
import VerdictCard from "./components/VerdictCard";
import LivePanel from "./components/LivePanel";
import { ApprovalPrompt, ClarifyForm } from "./components/Prompts";
import { Login, ProfileForm } from "./components/Forms";
import History from "./components/History";

export default function App() {
  const [uid, setUid] = useState(getToken() ? "me" : "");
  const [tab, setTab] = useState("validate");
  const [idea, setIdea] = useState("");
  const [niche, setNiche] = useState("");
  const [run, setRun] = useState(null);           // {run_id, idea_id}
  const [events, setEvents] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [approval, setApproval] = useState(null);
  const [card, setCard] = useState(null);
  const [ideas, setIdeas] = useState(null);       // Discover results
  const [proposals, setProposals] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (!uid) return <Login onLogin={setUid} />;

  const follow = (runId) => {
    setEvents([]); setQuestions([]); setApproval(null);
    streamRun(runId, (e) => {
      setEvents((x) => [...x, e]);
      if (e.type === "approval_needed") setApproval(e);
    }, async () => {
      const r = await api(`/runs/${runId}`);
      setBusy(false);
      if (r.state === "CLARIFY") setQuestions(r.questions);
      if (r.state === "FAILED") setErr(r.error || "Run failed");
      if (r.state === "DONE") { if (r.kind === "discover") setIdeas(r.result); else setCard(r.result); }
    });
  };

  const start = async (path, body) => {
    setErr(""); setCard(null); setIdeas(null); setProposals([]); setBusy(true);
    try {
      const r = await api(path, { method: "POST", body });
      if (r.cached) { setCard(r.result); setBusy(false); return; }
      setRun(r); follow(r.run_id);
    } catch (e) { setErr(e.message); setBusy(false); }
  };

  const challenge = async (dimension) => {
    setBusy(true);
    try {
      const r = await api(`/ideas/${card.idea_id}/challenge`, { method: "POST", body: { run_id: card.run_id, card, dimension } });
      setCard({ ...r.card, challenge_note: `${dimension}: ${r.outcome} — ${r.reason}` });
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const proposeWhatIf = async () => {
    setBusy(true);
    try {
      const r = await api(`/ideas/${card.idea_id}/whatif`, { method: "POST", body: { run_id: card.run_id, idea: card.idea_text, card } });
      setProposals(r.proposals || []);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  const applyWhatIf = async (p) => {
    setBusy(true); setProposals([]);
    const r = await api(`/ideas/${card.idea_id}/whatif`, { method: "POST",
      body: { run_id: card.run_id, idea: card.idea_text, card, apply_text: p.new_idea_text } });
    setCard(null); setRun(r); follow(r.run_id);
  };

  const respond = async (path, body) => {
    setBusy(true); setQuestions([]); setApproval(null);
    await api(`/runs/${run.run_id}/${path}`, { method: "POST", body });
    follow(run.run_id);
  };

  return (
    <main>
      <nav>
        {["validate", "discover", "profile", "history"].map((t) => (
          <button key={t} className={tab === t ? "active" : "secondary"} onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      {err && <p className="error" role="alert">{err}</p>}

      {tab === "profile" && <ProfileForm />}
      {tab === "history" && <History onOpen={(c) => { setCard(c); setTab("validate"); }} />}

      {tab === "validate" && (
        <section className="card">
          <h3>Validate your idea</h3>
          <textarea rows="4" placeholder="Describe the idea: what it does and who it is for"
            value={idea} onChange={(e) => setIdea(e.target.value)} />
          <button disabled={busy || idea.length < 10} onClick={() => start("/validate", { idea })}>Get verdict</button>
        </section>
      )}
      {tab === "discover" && (
        <section className="card">
          <h3>Discover ideas</h3>
          <input placeholder="Niche (optional), e.g. education" value={niche} onChange={(e) => setNiche(e.target.value)} />
          <button disabled={busy} onClick={() => start("/discover", { niche, n_ideas: 5 })}>Find ideas for me</button>
        </section>
      )}

      <LivePanel events={events} />
      <ClarifyForm questions={questions} onSubmit={(answers) => respond("answer", { answers })} />
      <ApprovalPrompt request={approval} onDecide={(ok) => respond("approve", { approve: ok })} />

      {ideas && (
        <section className="card">
          <h3>Ranked ideas</h3>
          <ol>{ideas.ideas.map((i) => (
            <li key={i.idea_id}><b>{i.verdict}</b> {i.score != null && `(${i.score})`} — {i.idea}
              <div><small>{i.reason}</small> <button className="link" onClick={() => setCard(i.card)}>open card</button></div></li>
          ))}</ol>
          {ideas.dropped.length > 0 && <small>{ideas.dropped.length} ideas dropped by the Skeptic.</small>}
        </section>
      )}

      {card && card.challenge_note && <p className="note">{card.challenge_note}</p>}
      <VerdictCard card={card} busy={busy} onChallenge={card && card.scores ? challenge : null} onWhatIf={proposeWhatIf} />
      {proposals.length > 0 && (
        <section className="card">
          <h4>Concrete changes</h4>
          <ul>{proposals.map((p, i) => (
            <li key={i}>{p.change} <button onClick={() => applyWhatIf(p)}>Apply → version 2</button></li>
          ))}</ul>
        </section>
      )}
    </main>
  );
}
