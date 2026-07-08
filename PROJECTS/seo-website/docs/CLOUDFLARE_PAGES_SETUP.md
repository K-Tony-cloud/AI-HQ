# Cloudflare Pages Setup

Deploy the SEO affiliate site to Cloudflare Pages connected to the monorepo.

---

## 1. Connect the Git Repository

1. Go to **Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git**
2. Authorize GitHub and select the `AI-HQ` repository
3. Cloudflare Pages will build on every push to the production branch

---

## 2. Build Configuration

| Setting | Value |
|---|---|
| **Production branch** | `main` |
| **Root directory** | `PROJECTS/seo-website` |
| **Build command** | `npm run build` |
| **Build output directory** | `dist` |
| **Node.js version** | `22` (set via Environment Variable `NODE_VERSION=22`) |

> Cloudflare Pages auto-detects Astro. If it doesn't, select **Astro** as the framework preset.

---

## 3. Environment Variables

Set in **Settings → Environment Variables** (Production):

| Variable | Value | Notes |
|---|---|---|
| `SITE_URL` | `https://your-site.pages.dev` | Replace with your custom domain once set |
| `NODE_VERSION` | `22` | Required for Astro v5+ |

---

## 4. Custom Domain (optional)

1. **Settings → Custom Domains → Add**
2. Enter your domain (e.g., `deals.yourdomain.com`)
3. Cloudflare automatically manages the SSL certificate and DNS if the domain is on Cloudflare

After adding a custom domain, update `SITE_URL` in both:
- Cloudflare Pages environment variables
- `.env` in `PROJECTS/shopee-agent-os/`

---

## 5. First Deployment

After connecting the repo, Cloudflare triggers a build automatically.

Watch the build log at:  
**Cloudflare → Pages → your-project → Deployments**

Expected output (13+ pages):
```
✓ Completed in Xms.
[build] 13 page(s) built in Xms
[build] Complete!
```

---

## 6. Enable Real Publishing from Discord

Once the site is live and you have verified the URL:

1. Update `.env` in `PROJECTS/shopee-agent-os/`:
   ```
   SITE_URL=https://your-site.pages.dev
   SEO_PUBLISH_ENABLED=true
   SEO_GIT_REMOTE=origin
   SEO_GIT_BRANCH=main
   ```

2. Test with a dry-run first (keep `SEO_PUBLISH_ENABLED=false`, run `/seo-publish`)
3. Switch to `true` and publish a real article

---

## 7. Rollback

If a bad article breaks the build or causes issues:

- **Instant rollback**: Cloudflare → Deployments → pick a previous deployment → **Rollback**
- **Via Discord**: `/seo-unpublish <article_id>` deletes the `.md` file, commits and pushes deletion, Cloudflare rebuilds automatically

---

## 8. Build Log Verification Checklist

After first deployment confirm:
- [ ] Build succeeded (exit 0)
- [ ] `sitemap-index.xml` generated in `dist/`
- [ ] At least one article URL appears in the sitemap
- [ ] Custom domain SSL is active (green padlock)
- [ ] `SITE_URL` matches the live URL exactly (no trailing slash)
