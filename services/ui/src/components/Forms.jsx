import { useEffect, useState } from "react";
import { api, setToken } from "../api";

export function Login({ onLogin }) {
  const [f, setF] = useState({ email: "", password: "" });
  const [err, setErr] = useState("");
  const go = async (path) => {
    setErr("");
    try { const r = await api(path, { method: "POST", body: f }); setToken(r.token); onLogin(r.user_id); }
    catch (e) { setErr(e.message); }
  };
  return (
    <section className="card narrow">
      <h2>Idea Validator</h2>
      <label>Email<input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
      <label>Password<input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
      {err && <p className="error">{err}</p>}
      <button onClick={() => go("/auth/login")}>Log in</button>{" "}
      <button className="secondary" onClick={() => go("/auth/register")}>Sign up</button>
    </section>
  );
}

const list = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function ProfileForm({ onSaved }) {
  const [p, setP] = useState(null);
  const [msg, setMsg] = useState("");
  useEffect(() => { api("/profile").then(setP).catch((e) => setMsg(e.message)); }, []);
  if (!p) return <p>{msg || "Loading profile…"}</p>;
  const save = async () => {
    const body = { skills: p.skills, hours_per_week: Number(p.hours_per_week), weeks_available: Number(p.weeks_available),
      team_size: Number(p.team_size), compute: p.compute, goal: p.goal, interests: p.interests };
    try { const r = await api("/profile", { method: "PUT", body }); setP(r); setMsg(`Saved (version ${r.version}).`); onSaved && onSaved(r); }
    catch (e) { setMsg(e.message); }
  };
  return (
    <section className="card">
      <h3>Your profile</h3>
      <div className="grid2">
        <label>Skills (comma separated)<input value={p.skills.join(", ")} onChange={(e) => setP({ ...p, skills: list(e.target.value) })} /></label>
        <label>Interests<input value={p.interests.join(", ")} onChange={(e) => setP({ ...p, interests: list(e.target.value) })} /></label>
        <label>Hours per week<input type="number" min="1" value={p.hours_per_week} onChange={(e) => setP({ ...p, hours_per_week: e.target.value })} /></label>
        <label>Weeks available<input type="number" min="1" value={p.weeks_available} onChange={(e) => setP({ ...p, weeks_available: e.target.value })} /></label>
        <label>Team size<input type="number" min="1" value={p.team_size} onChange={(e) => setP({ ...p, team_size: e.target.value })} /></label>
        <label>Compute<select value={p.compute} onChange={(e) => setP({ ...p, compute: e.target.value })}>
          <option value="laptop">Laptop</option><option value="free_gpu">Free GPU</option><option value="paid">Paid</option></select></label>
        <label>Goal<select value={p.goal} onChange={(e) => setP({ ...p, goal: e.target.value })}>
          <option value="startup">Startup</option><option value="portfolio">Portfolio</option><option value="course_project">Course project</option></select></label>
      </div>
      <button onClick={save}>Save profile</button> <span>{msg}</span>
    </section>
  );
}
