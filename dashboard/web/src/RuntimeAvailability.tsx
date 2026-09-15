import React, { useEffect, useState } from "react";
import { clearSessionToken } from "./api";
import { productRuntimeMode } from "../../shared/services/runtimeConfig";

type RuntimeState = "STARTING" | "READY" | "UNAVAILABLE" | "RECOVERING";

/** The product server supplies the marker; API URLs remain same-origin. */
export function RuntimeAvailability({ children }: { children: React.ReactNode }) {
  const productMode = productRuntimeMode();
  const [state, setState] = useState<RuntimeState>(productMode ? "STARTING" : "READY");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!productMode) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    let previousInstance: string | undefined;
    const check = async () => {
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      try {
        const response = await fetch("/api/v1/runtime/status", { signal: controller.signal, cache: "no-store" });
        const status = await response.json();
        if (!response.ok || status.state !== "READY" || status.mode !== productMode ||
            typeof status.instance_id !== "string" || !status.instance_id || status.api_base !== "/api/v1") {
          throw new Error("Runtime authority unavailable");
        }
        if (active) {
          if (previousInstance && previousInstance !== status.instance_id) {
            clearSessionToken();
            setState("RECOVERING");
          } else setState("READY");
          previousInstance = status.instance_id;
        }
      } catch {
        if (active) {
          clearSessionToken();
          setState("UNAVAILABLE");
        }
      } finally {
        clearTimeout(timeout);
        if (active) timer = setTimeout(check, 3000);
      }
    };
    void check();
    return () => { active = false; clearTimeout(timer); controller?.abort(); };
  }, [productMode, retry]);

  if (state === "READY") return <>{children}</>;
  return (
    <div className="secure-entry-root" data-testid="runtime-availability" data-state={state}>
      <div className="secure-access-card" role={state === "UNAVAILABLE" ? "alert" : "status"}>
        <h2 className="card-title">{state === "STARTING" ? "AlgoFortis is starting" : state === "RECOVERING" ? "Reconnecting to AlgoFortis" : "AlgoFortis is unavailable"}</h2>
        <p className="card-subtitle">{state === "UNAVAILABLE" ? "The local runtime is unavailable. Reopen AlgoFortis to restart it, or retry the connection." : "Waiting for the local runtime to become ready."}</p>
        {state === "UNAVAILABLE" && <button className="btn-primary-continue" onClick={() => { setState("RECOVERING"); setRetry(value => value + 1); }}>Retry connection</button>}
      </div>
    </div>
  );
}
