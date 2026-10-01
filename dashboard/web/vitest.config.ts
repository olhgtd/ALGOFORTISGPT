import { defineConfig } from "vitest/config";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");

export default defineConfig({
  root: dashboardRoot,
  resolve: {
    alias: {
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
      "react/jsx-runtime": path.resolve(__dirname, "node_modules/react/jsx-runtime"),
    },
  },
  test: {
    environment: "jsdom",
    include: [
      "web/src/__tests__/**/*.test.{ts,tsx}",
      "web/src/visual-lab/secure-entry/__tests__/**/*.test.{ts,tsx}",
      "user-dashboard/**/*.test.{ts,tsx}",
      "owner-dashboard/**/*.test.{ts,tsx}",
      "shared/components/professionalChartTruth.test.ts",
    ],
    clearMocks: true,
    restoreMocks: true,
  },
});
