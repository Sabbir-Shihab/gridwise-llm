# Preliminary submission package

Form: https://forms.gle/fDdAWMnipWXsfgc67

## Live values (fill the Google Form with these)

| Field | Value |
|---|---|
| Public API base URL | `http://campuslenzbd.online/gridwise.campuslenzbd.online` |
| Health | `GET http://campuslenzbd.online/gridwise.campuslenzbd.online/health` → `{"status":"ok"}` |
| Optimize | `POST http://campuslenzbd.online/gridwise.campuslenzbd.online/optimize-energy` |
| Alternate (after Namecheap A record) | `http://gridwise.campuslenzbd.online` |
| GitHub repository | https://github.com/Sabbir-Shihab/gridwise-llm |
| Docker image | `gridwise-llm:preli` locally; after GitHub Actions: `ghcr.io/<user>/gridwise-llm-preli:preli` |
| Video | Record `scripts/VIDEO_SCRIPT.md` (max 3:00) |

Live API is on the cPanel host, isolated from the Laravel site. Old sites were not modified. Add a Namecheap A record `gridwise` → `198.38.93.23` if you want the subdomain URL.

Set `GROQ_API_KEY` (or `GEMINI_API_KEY`) in `.env` and restart uvicorn before judges send hidden cases. Without a key, `/health` works but `/optimize-energy` cannot interpret notes.

## 1. Working public endpoint

Base URL (no trailing path):

```
http://campuslenzbd.online/gridwise.campuslenzbd.online
```

Judge checks:

- `GET /health` → `{"status":"ok"}`
- `POST /optimize-energy` with the Problem Statement schema

## 2. GitHub repository

https://github.com/Sabbir-Shihab/gridwise-llm

The live code is on branch `preli`, pushed to `main`. No commits after 11:00 PM.

## 3. README and configuration

Repository README is the local quickstart: env var names, Groq/Gemini model, OR-Tools GLOP, curl examples, public-sample test command, Docker run, limitations, and secret handling.

## 4. Docker fallback image

Docker Desktop is not installed on this machine. The `Dockerfile` is tested-layout ready (port 8000, bind `0.0.0.0`, no secrets).

On a machine with Docker:

```bash
docker build -t gridwise-llm:preli .
docker run --rm -p 8000:8000 -e GROQ_API_KEY=YOUR_KEY gridwise-llm:preli
curl http://127.0.0.1:8000/health
```

After the private GitHub repo exists, pushing `preli` runs `.github/workflows/docker-image.yml` and publishes:

```
ghcr.io/<user>/gridwise-llm-preli:preli
```

```bash
docker pull ghcr.io/<user>/gridwise-llm-preli:preli
docker run --rm -p 8000:8000 -e GROQ_API_KEY=YOUR_KEY ghcr.io/<user>/gridwise-llm-preli:preli
```

## 5. 3-minute video

Record `scripts/VIDEO_SCRIPT.md` as a screen capture (max 3:00). Upload MP4 or an organizer-accessible Drive/YouTube unlisted link.

Tie-break only, but still required.

## Pre-submit checklist

- [x] `GET /health` works locally and through the public tunnel
- [ ] `GROQ_API_KEY` or `GEMINI_API_KEY` set so `/optimize-energy` can interpret notes
- [ ] GitHub private repo pushed (`scripts/push_private_github.ps1`)
- [ ] README local quickstart used as-is
- [ ] Docker image built/pushed from a Docker-capable machine or GHCR
- [ ] Video ≤ 3 minutes uploaded
- [ ] Google Form submitted
- [ ] No commit after 11:00 PM
- [ ] Repo made public after the deadline
