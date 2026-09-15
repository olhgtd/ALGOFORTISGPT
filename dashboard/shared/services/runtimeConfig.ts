/** The product server owns this marker; it never grants authentication. */
export function productRuntimeMode(): "DEVELOPMENT" | "TEST" | "PRODUCTION" | null {
  const mode = typeof document === "undefined"
    ? null
    : (document.querySelector('meta[name="algofortis-runtime"]')?.getAttribute("content") ||
       document.querySelector('meta[name="sentinelx-runtime"]')?.getAttribute("content"));
  return mode === "DEVELOPMENT" || mode === "TEST" || mode === "PRODUCTION" ? mode : null;
}
