# Deploy Warden — 3 steps, ~15 minutes total

Everything below assumes you have a Mac and a browser open. No prior GitHub / Render / Loom accounts required — you'll create them as you go, all free.

At the end you'll have:

- ✅ A public GitHub repo URL
- ✅ A public Warden URL a judge can click
- ✅ A public Loom video URL

Copy them into `README.md` (there are three placeholder lines at the top).

---

## STEP 1 — Push to GitHub (5 min)

### 1a. Install the GitHub CLI (skip if you already have it)

```bash
brew install gh
```

### 1b. Log in

```bash
gh auth login
```

Follow the prompts:

- `GitHub.com`
- `HTTPS`
- `Y` (authenticate git with GitHub credentials)
- `Login with a web browser` — press Enter, copy the one-time code, paste it in the browser that opens, authorize.

### 1c. Create the repo and push

```bash
cd /Users/tanayhuddar/Downloads/warden
gh repo create warden-ai-commerce --public --source=. --remote=origin --push
```

That last command:

1. creates the public repo,
2. sets it as `origin`,
3. pushes all your commits.

When it's done it prints the URL. **Copy it.** That's your repo link.

Paste it into `README.md` where it says `REPO_URL`:

```bash
# open the file and replace REPO_URL_HERE with the URL gh printed
open README.md
```

Save. Then:

```bash
git commit -am "docs: repo URL" && git push
```

---

## STEP 2 — Deploy to Render (5 min)

Render deploys the backend + frontend from `render.yaml`. Free tier is enough for a demo.

### 2a. Create a Render account

Open <https://render.com/register> — click **Sign in with GitHub**, authorize Render to see your repos.

### 2b. Create a Blueprint

1. In Render's dashboard, click the purple **+ New** button → **Blueprint**.
2. Choose **`warden-ai-commerce`** from your GitHub repo list.
3. Give the blueprint a name (anything, e.g. `warden`).
4. Click **Apply**.

Render reads `render.yaml` and starts building **two** services: `warden-backend` and `warden-frontend`. First build takes ~4–5 minutes.

### 2c. Grab your URL

When both services show a green ● **Live** badge:

1. Click on `warden-frontend`.
2. At the top you'll see the URL — something like `https://warden-frontend.onrender.com`.
3. Open it in a new tab.

You should see the Warden dashboard. Header shows **● LIVE DEMO · Razorpay Test Mode · ✓ Backend connected · ✓ Audit verified**.

**Copy that URL. That's your live product link.** Paste it into `README.md` where it says `LIVE_URL_HERE`.

### 2d. Verify

Click all six scenario buttons on the live URL. Every one should work. If **Successful Purchase** returns green ALLOW, everything's wired.

Cold-start note: Render's free tier spins services down after 15 min of inactivity. First hit after a nap takes ~30 sec while the container wakes. Right before your demo, click the URL once to warm it up.

---

## STEP 3 — Record the video with Loom (5 min)

Loom is a free browser recorder. No install needed for the basic version.

### 3a. Sign up

Open <https://www.loom.com/signup>. Free tier, 5-min video limit — perfect.

### 3b. Prepare

Open two browser tabs side by side:

- Tab 1: your live Warden URL (from Step 2)
- Tab 2: this file, scrolled to the script below

Rehearse once through with the script. It's tight but comfortable.

### 3c. Record

In Loom, click **New Video** → **Screen + cam** (or Screen only if you prefer). Select the Warden tab.

Follow the script below. Speak clearly. Don't over-narrate — the UI does a lot of the work.

When done, Loom instantly gives you a shareable URL. **Copy it** and paste into `README.md` where it says `VIDEO_URL_HERE`.

Commit and push:

```bash
git commit -am "docs: video URL" && git push
```

---

## The 5-minute script

**Total: 5:00. Time codes are targets — a few seconds off in either direction is fine.**

### [0:00 — 0:20] Hook

*(on-screen: Warden dashboard, empty state, hero text visible)*

> "When an AI can decide what to buy — who decides whether it's allowed to spend?
>
> This is Warden. Trust infrastructure for AI commerce."

*(gesture at the top bar)*

> "AI proposes. Warden authorizes. Razorpay executes. Audit proves."

### [0:20 — 0:45] The architecture

*(hover the Transaction Flow strip: AI Buyer → Warden → Razorpay → Audit)*

> "Every AI purchase goes through four stages. The AI buyer builds a cart. Warden — a deterministic engine, no LLM — checks it against a customer mandate. Only if Warden allows does Razorpay ever get called. And every step is recorded in a hash-chained audit trail."

### [0:45 — 1:45] Scenario 1 — Successful Purchase

*(click **Run Successful Purchase**)*

> "Customer's mandate says: coffee purchases, up to ₹2000 a month. The AI restocks — ₹1499. Watch Warden's 8 checks fire."

*(pause 2 sec while the checks render)*

> "Mandate valid. Customer verified. Category coffee — allowed. Spend within limit. No duplicate. Price hasn't drifted."

*(point at the big green ALLOWED badge)*

> "ALLOWED. That decision authorized Razorpay to create a test order — you can see the order and payment link recorded on the right. The audit chain updates. Every event hash-linked to the previous one."

### [1:45 — 2:50] Scenario 2 — Cap Exceeded

*(click **Run Cap Exceeded**)*

> "Same customer, same mandate. But now the AI proposes ₹3,499 — over the ₹1000 cap."

*(pause while the panels update)*

> "Warden blocks it. Reason code: CAP_EXCEEDED. And look at the transaction flow —"

*(point at the flow strip)*

> "— Razorpay is marked 'Not called — Warden blocked'. The AI made the proposal. It never had the authority to execute it. Not a single API call went out."

### [2:50 — 3:50] Scenario 3 — Duplicate

*(click **Run Duplicate**)*

> "Now the interesting one. What if the same purchase is submitted twice? Maybe a retry, maybe a bug, maybe an adversarial replay."

*(pause)*

> "Warden's coordinator uses idempotency keys. Same key comes back — same action_id. No new Razorpay call, no double charge. The KPI card shows exactly one order authorized, no duplicates. This isn't a check the frontend enforces. It's cryptographically impossible to bypass because the payment layer refuses to create a second Razorpay order for the same action."

### [3:50 — 4:25] Audit

*(hover the Audit Trail column, then click **Verify chain**)*

> "Every decision Warden makes is written to an append-only, SHA-256 hash-chained log. Click Verify chain and the backend re-hashes every entry. If a single row is tampered with, the chain breaks and Warden tells you exactly which entry is invalid."

*(pause on the ✓ Chain verified badge)*

> "This is what makes AI commerce auditable. Not just fast — provable."

### [4:25 — 5:00] Close

*(scroll to top, hero visible)*

> "AI commerce doesn't only need intelligence. It needs trust.
>
> Warden creates that trust boundary.
>
> AI proposes.
>
> Warden authorizes.
>
> Razorpay executes.
>
> Audit proves.
>
> Warden. Trust infrastructure for AI commerce."

*(end)*

---

## If Render's free tier is too slow

If cold-start is annoying, either:

- Upgrade the frontend to Render's Starter plan ($7/mo) — no cold starts.
- Or deploy the frontend to Vercel instead: `npx vercel@latest` from `/frontend`, set `NEXT_PUBLIC_API_BASE_URL` to your Render backend URL.

Either fallback preserves everything else in this guide.

---

## If something breaks

- **Frontend shows "Backend unreachable"** — CORS or the backend URL is wrong. Check the frontend service's `NEXT_PUBLIC_API_BASE_URL` env var in Render's dashboard. It should be `https://warden-backend.onrender.com` (or whatever Render assigned).
- **Backend build fails** — usually a stale requirements cache. In Render → backend service → Settings → Clear build cache & Deploy.
- **Everything green but scenarios return errors** — the seed didn't run. In Render → backend service → Shell tab, run `python -m app.seed --url $DATABASE_URL --create-tables`.

Ping me here with the error and I'll diagnose.
