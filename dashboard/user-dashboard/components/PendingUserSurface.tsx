import React from "react";

export const PendingUserSurface: React.FC<{ title: string }> = ({ title }) => (
  <section className="af-pending-surface" data-testid="pending-user-surface">
    <span className="af-eyebrow">User Surface</span>
    <h1>{title}</h1>
    <p>This page is being migrated onto the locked AlgoFortis user shell. Legacy preview content is not shown as finished product data.</p>
    <div className="af-empty-state">
      <strong>Authoritative surface not available in this slice</strong>
      <span>Home / Command Center is the active implementation slice. No trading authority is granted here.</span>
    </div>
  </section>
);
