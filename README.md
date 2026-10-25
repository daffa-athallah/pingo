# Recall

Recall is a responsive React web app. The frontend foundation lives in [`frontend/`](frontend/). Backend and AI integrations are outside this setup.

## Run locally

Use Node.js 22.12+ (or another version supported by the installed Vite release).

```sh
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite. For checks and a production preview:

```sh
npm run typecheck
npm run build
npm run preview
```

## Structure

```text
frontend/
├── public/
├── src/
│   ├── assets/
│   │   ├── images/
│   │   └── icons/
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.tsx
│   │   │   └── BottomNav.tsx
│   │   └── common/
│   │       ├── PageHeader.tsx
│   │       └── EmptyState.tsx
│   ├── pages/
│   │   ├── home/HomePage.tsx
│   │   ├── checkin/CheckInPage.tsx
│   │   ├── category/CategoryPage.tsx
│   │   └── entity/EntityDetailPage.tsx
│   ├── data/mockData.ts
│   ├── types/recall.ts
│   ├── services/api.ts
│   ├── styles/global.css
│   ├── router/AppRouter.tsx
│   ├── App.tsx
│   └── main.tsx
├── .gitignore
├── index.html
├── package.json
├── package-lock.json
├── tsconfig.json
└── vite.config.ts
```

The empty asset and public directories contain `.gitkeep` files so they survive checkout.

## Routes and fixtures

| Route | Behavior |
| --- | --- |
| `/` | Homepage skeleton with Food, Shopping, and Travel category cards |
| `/check-in` | Ica's Check-in placeholder |
| `/category/:category` | Reusable category page for `food`, `shopping`, or `travel` |
| `/entity/:entityId` | Entity placeholder using fixture data when available |

Unknown routes and unsupported categories redirect to `/`. Unknown entity IDs, including `/entity/test`, render a safe detail placeholder.

`src/data/mockData.ts` holds three development entities: Ramen A (Carlton, 5 screenshots), Zara Brown Jacket (3 screenshots), and TeamLab Tokyo (2 screenshots). Homepage counts reflect fixture entities, not screenshots. Category entries link to their entity detail pages. No backend calls are made. `src/services/api.ts` reserves the future API location; an optional `VITE_API_BASE_URL` can be set in an ignored `.env.local` file later.

Production hosting will need an SPA fallback to `index.html` for direct links and refreshes on nested routes. Vite's development and preview servers already handle this.

## Parallel development

Once this shared foundation has been committed and pushed, both developers should branch from that same commit:

```sh
# Daffa, in his checkout
git switch -c feature/home

# Ica, in her checkout
git switch -c feature/checkin
```

| Owner | Page directories | Owned sections of `src/styles/global.css` |
| --- | --- | --- |
| Daffa | `src/pages/home/`, `src/pages/category/`, `src/pages/entity/` | 6. Homepage, 7. Categories, 8. Entity Detail |
| Ica | `src/pages/checkin/` | 9. Check-in |

All styling belongs in the **single** `src/styles/global.css`, imported once by `src/main.tsx`. Add page media queries within the relevant owner's section. Do not add page stylesheets, CSS modules, inline styles, or UI frameworks.

Coordinate changes to shared files: CSS tokens/base/layout/components/navigation/responsive sections, `router/`, `components/`, `types/`, `data/`, and `services/`. Keep page classes scoped with `home-`, `category-`, `entity-`, and `checkin-` prefixes. The two developers can evolve their page files and CSS sections independently without changing the router or shell.

When screenshot references arrive, update the relevant owner's pages and CSS sections while retaining the routes, folder structure, and shared types where possible. Homepage and Check-in are intentionally placeholders; no authentication, uploads, notifications, calendar, location, backend, or agents are implemented.

## Manual navigation check

1. From `/`, select Food; verify `/category/food`, then return Home.
2. Select Shopping; verify `/category/shopping`, then return Home.
3. Select Travel; verify `/category/travel`, then return Home.
4. Use bottom navigation to go Home → Check-in → Home.
5. Open `/entity/test` directly and confirm the safe detail placeholder.
6. Open a known fixture (for example `/entity/food-ramen-a`) and an unknown route; verify detail content and the redirect respectively.
