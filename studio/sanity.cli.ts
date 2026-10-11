import { defineCliConfig } from "sanity/cli";

export default defineCliConfig({
  api: { projectId: "1lvtpppu", dataset: "production" },
  studioHost: "snappsense", // → https://snappsense.sanity.studio
  deployment: { autoUpdates: true, appId: "vhmw5eje54exvhz0r66q0wvw" },
});
