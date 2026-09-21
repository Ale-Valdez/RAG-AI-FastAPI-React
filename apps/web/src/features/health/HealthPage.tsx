import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "../../shared/states";
import { fetchHealth, fetchReady, type HealthResponse, type ReadyResponse } from "./api";

export default function HealthPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const healthResult = await fetchHealth();
        const readyResult = await fetchReady();
        if (cancelled) return;
        setHealth(healthResult);
        setReady(readyResult);
      } catch (reason: unknown) {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Unable to reach the API.");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return <ErrorState message={error} />;
  }
  if (!health) {
    return <LoadingState label="Checking API health…" />;
  }

  const probes = ready?.probes ?? {};
  return (
    <section className="panel">
      <h2>API status</h2>
      <p>
        {health.service}: <strong>{health.status}</strong>
      </p>
      {ready && ready.status !== "ok" ? (
        <p className="error">Readiness checks failed.</p>
      ) : null}
      {Object.keys(probes).length === 0 ? (
        <p className="muted">No readiness probes reported.</p>
      ) : (
        <div>
          {Object.entries(probes).map(([name, ok]) => (
            <div className="probe" key={name}>
              <span>{name}</span>
              <strong>{ok ? "ok" : "down"}</strong>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
