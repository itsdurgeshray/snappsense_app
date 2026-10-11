# Snappsense Studio (Sanity)

Edit the homepage, landing pages, legal pages, blog posts, site settings and
loading messages. Published changes rebuild the website automatically (~1 min).

## First-time setup (run once, from this folder)

```bash
npm install
npx sanity login            # opens the browser; use your Sanity account
npm run import-seed         # copies today's live content into Sanity (skips anything already there)
npm run deploy              # publishes the Studio to https://snappsense.sanity.studio
```

Then add the Vercel deploy hook as a Sanity webhook (sanity.io/manage → API → Webhooks):
name "Rebuild site", dataset `production`, trigger on create/update/delete, POST.

## Everyday

- Open https://snappsense.sanity.studio, edit, press **Publish**. The site rebuilds in about a minute.
- **Pages**: the address `home` is the homepage and `404` the not-found page; anything else lives at `/your-address`.
- **Blog posts** live at `/blogs/your-address`; posts need a publish date to appear.
- **Site settings**: header/footer links, the legal note, default search & sharing, the announcement banner.
- Run `npm run dev` to try the Studio locally (http://localhost:3333).

Content types are in `schemaTypes/`; each page section has a matching component in
`../src/components/sections.tsx`.
