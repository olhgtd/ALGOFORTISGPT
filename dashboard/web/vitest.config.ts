import { defineConfig } from "vitest/config";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dashboardRoot = path.resolve(__dirname, "..");

export default defineConfig({
  root: __dirname,
  resolve: {
    alias: [
      { find: /^\/user-dashboard(?=\/|$)/, replacement: path.resolve(dashboardRoot, "user-dashboard") },
      { find: /^\/owner-dashboard(?=\/|$)/, replacement: path.resolve(dashboardRoot, "owner-dashboard") },
      { find: /^\/shared(?=\/|$)/, replacement: path.resolve(dashboardRoot, "shared") },
      { find: "react", replacement: path.resolve(__dirname, "node_modules/react") },
      { find: "react-dom", replacement: path.resolve(__dirname, "node_modules/react-dom") },
      { find: "react/jsx-runtime", replacement: path.resolve(__dirname, "node_modules/react/jsx-runtime") },
    ],
  },
  server: {
    fs: {
      allow: [dashboardRoot],
    },
  },
  test: {
    environment: "jsdom",
    include: [
      "src/__tests__/**/*.test.{ts,tsx}",
      "src/visual-lab/secure-entry/__tests__/**/*.test.{ts,tsx}",
      "../user-dashboard/**/*.test.{ts,tsx}",
      "../owner-dashboard/**/*.test.{ts,tsx}",
      "../shared/components/professionalChartTruth.test.ts",
    ],
    clearMocks: true,
    restoreMocks: true,
  },
});
