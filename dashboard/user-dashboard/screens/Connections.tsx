import React from "react";
import { LiveReadinessRuntime } from "../../shared/components/LiveReadinessRuntime";
import { UserConnectionsRuntime } from "../../shared/components/UserConnectionsRuntime";
import { UserDeploymentsRuntime } from "../../shared/components/UserDeploymentsRuntime";

export const ConnectionsScreen: React.FC<{ previewMode?: boolean }> = () => {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <UserConnectionsRuntime />
      <UserDeploymentsRuntime />
      <LiveReadinessRuntime view="connections" />
    </div>
  );
};
