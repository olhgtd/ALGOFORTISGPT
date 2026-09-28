import React, { useEffect, useState } from "react";
import type { UserShellStatus } from "../shellState";
import { HomeCommandCenter } from "../home/HomeCommandCenter";
import { buildHomeCommandCenterModel, type HomeCommandCenterModel } from "../home/homeModel";
import { loadHomeCommandCenterModel } from "../home/homeData";

interface Props {
  go: (screen: string) => void;
  onShellStatus?: (status: UserShellStatus) => void;
}

export const UserHome: React.FC<Props> = ({ go, onShellStatus }) => {
  const [model, setModel] = useState<HomeCommandCenterModel | null>(null);

  useEffect(() => {
    let active = true;

    void loadHomeCommandCenterModel()
      .then((next) => {
        if (!active) return;
        setModel(next);
        onShellStatus?.(next.shell);
      })
      .catch(() => {
        if (!active) return;
        const unavailable = buildHomeCommandCenterModel({});
        setModel(unavailable);
        onShellStatus?.(unavailable.shell);
      });

    return () => {
      active = false;
    };
  }, [onShellStatus]);

  if (!model) {
    return (
      <section className="af-home-loading" role="status" aria-live="polite">
        <span className="af-eyebrow">Home / Command Center</span>
        <h1>Loading authoritative Command Center…</h1>
        <p>AlgoFortis is checking runtime, portfolio, and canonical market authorities. Missing data will stay unavailable rather than being estimated.</p>
      </section>
    );
  }

  return <HomeCommandCenter model={model} onNavigate={go} />;
};
