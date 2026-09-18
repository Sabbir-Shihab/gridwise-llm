# Preliminary submission package

Form: https://forms.gle/fDdAWMnipWXsfgc67

Fill these fields after the live URL, repository, Docker tag, and video are ready.

## 1. Working public endpoint

Base URL (no trailing path):

```
https://<your-service-host>
```

Judge checks:

- `GET /health` → `{"status":"ok"}`
- `POST /optimize-energy` with the Problem Statement schema

Keep this host up through the evaluation window. Set `GROQ_API_KEY` (or `GEMINI_API_KEY`) on the host. Do not put the key in the form or README.

## 2. GitHub repository

Create a **new private** repository after question reveal, push this project, keep it private during the event, then make it **public after 11:00 PM**.

```bash
git init
git add .
git commit -m "Submit GridWise LLM preliminary service."
# create a private GitHub repo in the browser, then:
git remote add origin https://github.com/<user>/<repo>.git
git branch -M main
git push -u origin main
```

No commits after 11:00 PM.

## 3. README and configuration

This repository README is the local quickstart: env var names, Groq/Gemini model, OR-Tools GLOP, curl examples, public-sample test command, Docker run, limitations, and secret handling.

## 4. Docker fallback image

Build locally if Docker Desktop is installed:

```bash
docker build -t gridwise-llm:preli .
docker tag gridwise-llm:preli ghcr.io/<user>/<repo>:preli
docker push ghcr.io/<user>/<repo>:preli
```

After GitHub Actions runs on `main`, the image is:

```
ghcr.io/<user>/<repo>:preli
```

Verified run:

```bash
docker pull ghcr.io/<user>/<repo>:preli
docker run --rm -p 8000:8000 -e GROQ_API_KEY=YOUR_KEY ghcr.io/<user>/<repo>:preli
curl http://127.0.0.1:8000/health
```

Image has no baked-in secrets. Port 8000, bind `0.0.0.0`.

## 5. 3-minute video

Record `scripts/VIDEO_SCRIPT.md` as a screen capture (max 3:00). Upload MP4 or an organizer-accessible link (Drive/YouTube unlisted).

The video is tie-break only. It still must be submitted.

## Pre-submit checklist

- [ ] `GET /health` works from outside the laptop
- [ ] `POST /optimize-energy` accepts 1–3 operator notes
- [ ] LLM key is set on the host, not in git
- [ ] Repository is private until the deadline, then public
- [ ] README local quickstart works
- [ ] Docker tag is pullable
- [ ] Video ≤ 3 minutes
- [ ] No commit after 11:00 PM
