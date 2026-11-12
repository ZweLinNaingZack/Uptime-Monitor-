// Vitest runs the frontend's unit tests: `npm test`. See the Next.js guide in
// node_modules/next/dist/docs/01-app/02-guides/testing/vitest.md.
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  // Reads "paths" from tsconfig.json, so "@/lib/api" imports work in tests as in the app.
  resolve: { tsconfigPaths: true },
  test: {
    // Plain Node by default. A test file that renders components asks for a fake browser
    // ("jsdom") with a comment at its top.
    environment: "node",
    include: ["__tests__/**/*.test.{ts,tsx}"],
  },
});
