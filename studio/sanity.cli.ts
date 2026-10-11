import { defineCliConfig } from "sanity/cli";

export default defineCliConfig({
  api: { projectId: "1lvtpppu", dataset: "production" },
  studioHost: "snappsense", // → https://snappsense.sanity.studio
  deployment: { autoUpdates: true },
});
