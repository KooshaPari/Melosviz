# Deploy MelosViz Web to Vercel

## Prerequisites
- Vercel account + `npx vercel` CLI

## Deploy
```bash
cd web && bun install
npx vercel deploy --prod
```

Set `VITE_API_URL` in Vercel project environment variables to your backend URL.

## Backend
Deploy Python backend separately (Railway/Fly.io/VPS):
```bash
cd backend && pip install -r requirements.txt
uvicorn src.melosviz.bridge.server:app --host 0.0.0.0 --port 5000
```
