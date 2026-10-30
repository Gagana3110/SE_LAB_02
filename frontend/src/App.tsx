import { useEffect, useState } from "react";

type Status = "checking" | "connected" | "database down" | "unreachable";

export default function App() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((body) => setStatus(body.database === "up" ? "connected" : "database down"))
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main>
      <h1>Demand Forecasting System</h1>
      <p>Backend status: {status}</p>
    </main>
  );
}
