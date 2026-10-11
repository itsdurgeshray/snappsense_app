import { defineConfig } from "sanity";
import { structureTool } from "sanity/structure";
import { visionTool } from "@sanity/vision";
import { SINGLETONS, schemaTypes } from "./schemaTypes";

export default defineConfig({
  name: "snappsense",
  title: "Snappsense",
  projectId: "1lvtpppu",
  dataset: "production",
  plugins: [
    structureTool({
      structure: (S) =>
        S.list()
          .title("Content")
          .items([
            S.listItem().title("Site settings").id("siteSettings").child(S.document().schemaType("siteSettings").documentId("siteSettings")),
            S.listItem().title("Loading messages").id("loaderMessages").child(S.document().schemaType("loaderMessages").documentId("loaderMessages")),
            S.divider(),
            S.documentTypeListItem("page").title("Pages"),
            S.documentTypeListItem("post").title("Blog posts"),
          ]),
    }),
    visionTool(),
  ],
  schema: {
    types: schemaTypes,
    // Settings are singletons: no "create new" for them.
    templates: (templates) => templates.filter(({ schemaType }) => !SINGLETONS.includes(schemaType)),
  },
  document: {
    actions: (actions, { schemaType }) =>
      SINGLETONS.includes(schemaType) ? actions.filter(({ action }) => action && ["publish", "discardChanges", "restore"].includes(action)) : actions,
  },
});
