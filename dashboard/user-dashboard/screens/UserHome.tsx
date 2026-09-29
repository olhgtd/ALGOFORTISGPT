import React, { useEffect, useMemo, useState } from "react";
import type { UserRiskAuthority } from "../data/userShellData";
import type { UserShellStatus } from "../shellState";
import { HomeCommandCenter } from "../home/HomeCommandCenter";
import { buildHomeCommandCenterModel, type HomeCommandCenterModel } from "../home/homeModel";
import { loadHomeCommandCenterModel } from "../home/homeData";

interface Props {
  go: (screen: string) => void;
  shellStatus?: UserShellStatus;
  riskAuthority?: UserRiskAuthority;
}

export const UserHome: React.FC<Props> = ({ go, shellStatus, riskAuthority }) => {
  const [model, setModel] = useState<HomeCommandCenterModel | null>(null);

  useEffect(() => {
    let active = true;
    void loadHomeCommandCenterModel()
      .then((next) => { if (active) setModel(next); })
      .catch(() => { if (active) setModel(buildHomeCommandCenterModel({})); });
    return () => { active = false; };
  }, []);

  const displayModel = useMemo(() => {
    if (!model) return null;
    return {
      ...model,
      ...(shellStatus ? { shell: shellStatus } : {}),
      ...(riskAuthority ? { risk: riskAuthority } : {}),
    };
  }, [model, riskAuthority, shellStatus]);

  if (!displayModel) {
    return (
      <section className="af-home-loading" role="status" aria-live="polite">
        <span className="af-eyebrow">Home / Command Center</span>
        <h1>Loading authoritative Command Center…</h1>
        <p>AlgoFortis is checking runtime, portfolio, and canonical market authorities. Missing data will stay unavailable rather than being estimated.</p>
      </section>
    );
  }

  return <HomeCommandCenter model={displayModel} onNavigate={go} />;
};
