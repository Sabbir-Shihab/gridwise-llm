# Preliminary submission package

Form: https://forms.gle/fDdAWMnipWXsfgc67

## Live values (fill the Google Form with these)

| Field | Value |
|---|---|
| Public API base URL | `https://3803aa1655d060.lhr.life` |
| Health | `GET https://3803aa1655d060.lhr.life/health` → `{"status":"ok"}` |
| Optimize | `POST https://3803aa1655d060.lhr.life/optimize-energy` |
| GitHub repository | Create with `scripts/push_private_github.ps1` after `gh auth login` |
| Docker image | `gridwise-llm:preli` locally; after GitHub Actions: `ghcr.io/<user>/gridwise-llm-preli:preli` |
| Video | Record `scripts/VIDEO_SCRIPT.md` (max 3:00) |

The public URL is a tunnel to this machine. Keep the laptop awake with the API process running until a Render/Railway host replaces it.

Set `GROQ_API_KEY` (or `GEMINI_API_KEY`) in `.env` and restart uvicorn before judges send hidden cases. Without a key, `/health` works but `/optimize-energy` cannot interpret notes.

## 1. Working public endpoint

Base URL (no trailing path):

```
https://3803aa1655d060.lhr.life
```

Judge checks:

- `GET /health` → `{"status":"ok"}`
- `POST /optimize-energy` with the Problem Statement schema

## 2. GitHub repository

GitHub CLI is installed. Complete device login, then run the push script.

```powershell
# Browser: https://github.com/login/device
gh auth login --hostname github.com --git-protocol https --web
.\scripts\push_private_github.ps1
```

Keep the repo **private until 11:00 PM**, then:

```powershell
gh repo edit gridwise-llm-preli --visibility public --accept-visibility-change-consequences
```

No commits after 11:00 PM.

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
