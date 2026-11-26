// U3: shows the running agent, its tool calls and spend as they happen.
export default function LivePanel({ events }) {
  if (!events.length) return null;
  const last = events[events.length - 1];
  const spend = [...events].reverse().find((e) => e.spend !== undefined);
  return (
    <section className="card live" aria-label="live progress">
      <div className="live-head">
        <b>Now:</b> <span data-testid="current">{last.agent || last.to || last.type}</span>
        {spend && <span className="spend" data-testid="spend">spent ${spend.spend.toFixed(4)}</span>}
      </div>
      <ol className="events">
        {events.map((e, i) => (
          <li key={i}>
            <code>{e.type}</code>{" "}
            {e.type === "transition" && `${e.from || ""} → ${e.to}`}
            {e.agent && ` ${e.agent}`}
            {e.tool && ` · tool ${e.tool}`}
            {e.dimension && ` · ${e.dimension} = ${e.abstained ? "abstained" : e.score}`}
            {e.verdict && ` · ${e.verdict}`}
            {e.what && ` · ${e.what}`}
          </li>
        ))}
      </ol>
    </section>
  );
}
