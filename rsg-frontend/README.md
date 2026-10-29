# RSG frontend

React + TypeScript + Vite. Requires Node.js 20.19+ or 22.12+ and npm.

```powershell
npm ci
npm run dev
```

Open http://localhost:5173 with the backend running at http://127.0.0.1:8000. Vite proxies `/api`, `/docs`, and `/openapi.json` to the backend. Never add the Groq key to this project.

Run `npm run build` for a type-checked production build. The backend optionally serves `dist/` when it exists at startup. Local dependencies, build output, cache, and environment files are ignored here.

Assistant messages use `react-markdown` with GitHub-flavored Markdown and line-break support, adapted from the message renderer in my existing agent application. Tables scroll within the message; raw HTML is escaped and links allow only web/mail protocols. User messages remain plain text. Run `npm test` for Markdown rendering regressions, including the revenue contribution table, code fences, malformed tables, and unsafe HTML/links.
