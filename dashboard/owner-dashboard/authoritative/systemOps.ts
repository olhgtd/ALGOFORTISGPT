import { ownerFetch } from "./api";

export async function querySystemOperations(): Promise<any> {
  const [authority, productOps, incidents, audit] = await Promise.all([
    ownerFetch<any>("/api/v1/owner/admin/authority"),
    ownerFetch<any>("/api/v1/product-ops/owner/health"),
    ownerFetch<any>("/api/v1/owner/admin/incidents?limit=100"),
    ownerFetch<any>("/api/v1/integration/audit/events?limit=100&offset=0"),
  ]);
  return { authority, productOps, incidents, audit };
}
