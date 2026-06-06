# Deploying Roqet

Two pieces: the **API** (FastAPI + Qdrant + local embedder) on **Railway**, and the
**UI** (Next.js) on **Vercel**.

The API container is intentionally small: `Dockerfile.api` installs only
fastembed (ONNX) for query embedding — no torch, and **no in-process vector DB**.
The vectors live in a **managed Qdrant** cluster (e.g. Qdrant Cloud's free tier),
which keeps the container's RAM low and stable (the earlier all-in-one image OOM'd
on small tiers because it held the model *and* all 33k vectors in one process).

### 0. Managed Qdrant (one-time)
1. Create a free cluster at [cloud.qdrant.io](https://cloud.qdrant.io) and copy its
   URL and API key.
2. Load the index into it from your machine:
   ```bash
   export QDRANT_URL="https://xxxx.cloud.qdrant.io:6333"
   export QDRANT_API_KEY="..."
   ./scripts/index_cloud.sh
   ```
3. In the Railway service → Variables, set the same `QDRANT_URL` and
   `QDRANT_API_KEY`. The API reads them at runtime.

---

## 1. Backend → Railway

### Option A — deploy from GitHub (recommended)
1. Push this repo to GitHub.
2. On [railway.app](https://railway.app): **New Project → Deploy from GitHub repo** → pick this repo.
3. Railway reads `railway.toml` and builds `Dockerfile.api` automatically.
4. Wait for the build (it installs torch + builds the index; first build ~5–8 min).
5. **Settings → Networking → Generate Domain** to get a public URL, e.g.
   `https://roqet-api-production.up.railway.app`.
6. Verify: open `https://<your-domain>/health` → `{"status":"ok",...}`.

### Option B — deploy from the CLI
```bash
npm i -g @railway/cli
railway login
railway init
railway up            # uploads the repo, builds Dockerfile.api
railway domain        # create a public URL
```

### Resources
The image runs torch + MiniLM + an on-disk Qdrant of ~21k points. Give the service
**≥ 1 GB RAM** (Railway: Settings → Resources). The index is read-only and baked into
the image, so no persistent volume is required.

### Optional hardening
- Set `CORS_ORIGINS` to your Vercel URL (Variables tab) to stop allowing `*`.

---

## 2. Frontend → Vercel

1. On [vercel.com](https://vercel.com): **Add New → Project** → import this repo.
2. Framework preset: **Next.js** (auto-detected). Root directory: repo root.
3. **Environment Variables** → add:
   ```
   NEXT_PUBLIC_API_URL = https://<your-railway-domain>
   ```
   (no trailing slash)
4. **Deploy.** Vercel builds and serves the UI.
5. Open the Vercel URL — search hits your Railway API.

> `NEXT_PUBLIC_API_URL` is baked at **build** time. If you change it later, redeploy
> the Vercel project.

---

## 3. Refreshing the index

The deployed index is the snapshot in `deploy/declarations.enriched.jsonl`. To update
it (new libraries, more declarations, different model):

```bash
python3 -m roqet.fetch --lib stdlib --lib mathcomp
SOURCES="--source repos/stdlib/theories=stdlib --source repos/mathcomp=mathcomp" \
  MODEL=local ./scripts/build_index.sh
cp data/declarations.enriched.jsonl deploy/declarations.enriched.jsonl
git commit -am "Refresh deploy index snapshot" && git push
```

Railway rebuilds on push; Vercel needs no change.

---

## Notes
- **Embedder must match at build and serve time.** The image bakes `local` +
  `all-MiniLM-L6-v2` for both; don't override `EMBED_MODEL` at runtime without
  rebuilding the index.
- For very large corpora, move from the on-disk Qdrant to a managed Qdrant: run a
  Qdrant service, set `QDRANT_URL`/`QDRANT_API_KEY`, and index into it instead of
  baking the store.
