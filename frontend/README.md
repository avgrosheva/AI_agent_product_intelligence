# Frontend

React + TypeScript + Vite application for AI Agent Product Intelligence. See the [repository README](../README.md) for what the product does and how to run the full stack (backend + database + frontend).

## Development

```bash
npm install
npm run dev            # http://localhost:5173
```

## Testing

```bash
npm run test                                      # unit tests (Vitest + React Testing Library)
npx playwright install chromium                    # one-time browser install
npm run test:e2e                                   # end-to-end (needs the backend running against demo data)
```

## Build

```bash
npm run build
```
