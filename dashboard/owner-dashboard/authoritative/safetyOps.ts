import { ownerFetch, ownerMutationWithStepUp } from "./api";

export async function queryOwnerSafety(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/safety");
}

export async function engageSafeMode(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/safety/safe-mode/engage", { method: "POST" });
}

export async function engageGlobalHold(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/safety/global-hold/engage", { method: "POST" });
}

export async function releaseGlobalHold(): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "SAFETY_RELEASE",
    path: "/api/v1/owner/safety/global-hold/release",
    body: {},
  });
}
