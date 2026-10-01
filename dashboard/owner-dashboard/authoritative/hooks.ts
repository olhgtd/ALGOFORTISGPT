import { useCallback, useEffect, useState } from "react";
import { queryOwnerAuthority, type OwnerAuthoritySnapshot } from "./api";

export function useOwnerAuthority() {
  const [snapshot, setSnapshot] = useState<OwnerAuthoritySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await queryOwnerAuthority();
      setSnapshot(next);
      setError(null);
    } catch (err: any) {
      setSnapshot(null);
      setError(err?.message || "OWNER_AUTHORITY_UNAVAILABLE");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  return { snapshot, loading, error, refresh };
}

export function useAsyncResource<T>(loader: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await loader());
      setError(null);
    } catch (err: any) {
      setData(null);
      setError(err?.message || "AUTHORITY_UNAVAILABLE");
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => { void refresh(); }, [refresh]);
  return { data, loading, error, refresh };
}
