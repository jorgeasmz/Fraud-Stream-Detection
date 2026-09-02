import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node", include: ["lib/**/*.test.ts"] },
  // fileURLToPath decodes the URL; `pathname` leaves a path whose accents are
  // percent-encoded, which resolves to nothing on disk.
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
});
