import React from "react";
import { OwnerAccessRegistryScreen } from "./screens";
import { OwnerUsersInspectionScreen } from "./UserInspection";

export const UsersAccessScreen: React.FC = () => (
  <>
    <div className="v3-screen-head">
      <div>
        <h2 className="v3-screen-title">Users & Access</h2>
        <p className="v3-screen-sub">One canonical Owner surface for user inspection, lifecycle, entitlement, activation, session and access governance.</p>
      </div>
    </div>
    <OwnerUsersInspectionScreen />
    <OwnerAccessRegistryScreen />
  </>
);
