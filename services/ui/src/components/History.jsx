import { useEffect, useState } from "react";
import { api } from "../api";

// U9: past ideas and versions, and a six-dimension comparison of two ideas.
export default function History({ onOpen }) {
  const [ideas, setIdeas] = useState([]);
  const [sel, setSel] = useState([]);
  const [versions, setVersions] = useState(null);
  const [cmp, setCmp] = useState(null);
  useEffect(() => { api("/ideas").then(setIdeas).catch(() => {}); }, []);
  const toggle = (id) => setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id].slice(-2)));
  return (
    <section className="card">
      <h3>History</h3>
      <table>
        <thead><tr><th /><th>Idea</th><th>Latest verdict</th><th>Versions</th><th /></tr></thead>
        <tbody>
          {ideas.map((i) => (
            <tr key={i.id}>
              <td><input type="checkbox" aria-label={`select ${i.title}`} checked={sel.includes(i.id)} onChange={() => toggle(i.id)} /></td>
              <td>{i.title}</td><td>{i.latest_verdict}</td><td>{i.latest_version}</td>
              <td><button onClick={async () => setVersions({ id: i.id, list: await api(`/ideas/${i.id}/versions`) })}>Versions</button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <button disabled={sel.length !== 2} onClick={async () => setCmp(await api(`/compare?a=${sel[0]}&b=${sel[1]}`))}>
        Compare selected
      </button>
      {versions && (
        <ul>{versions.list.map((v) => (
          <li key={v.version}>v{v.version}: {v.verdict} ({v.score}) — {v.text.slice(0, 80)}
            {v.card && <button className="link" onClick={() => onOpen(v.card)}>open card</button>}</li>
        ))}</ul>
      )}
      {cmp && (
        <table aria-label="comparison">
          <thead><tr><th>Dimension</th><th>A ({cmp.a.verdict})</th><th>B ({cmp.b.verdict})</th></tr></thead>
          <tbody>{cmp.dimensions.map((d) => (
            <tr key={d.dimension}><td>{d.dimension}</td>
              <td className={d.better === "a" ? "win" : ""}>{d.a}</td><td className={d.better === "b" ? "win" : ""}>{d.b}</td></tr>
          ))}</tbody>
        </table>
      )}
    </section>
  );
}
