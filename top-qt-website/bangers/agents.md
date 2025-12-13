# Bangers Agent Guidelines

## Project Overview
Next.js app for visualizing "bangers" (highly-quoted tweets) from the Community Archive.

## Architecture

### Data Flow
```
Supabase (CA) → lib/api.ts → Server Actions → React Components
                    ↓
            Supabase (TopQt) - local strand ratings DB
```

### Key Abstractions
- `Tweet` type in `lib/types.ts` - canonical tweet shape
- `fetchTweetDetails` - enriches tweet IDs with user info, media, quotes
- `loadThreadColumns` - groups tweets by conversation for visualization

## Antipatterns to Fix

### lib/api.ts
- **Issue:** Duplicated batch loop pattern (lines 74-124)
- **Fix:** Extract `batchFetch<T>(ids, fetchFn, batchSize)` utility

### app/HomePageClient.tsx
- **Issue:** 357 lines, handles layout + state + navigation + URL sync
- **Fix:** Extract hooks: `useUrlSync`, `useTweetSelection`, `usePaneNavigation`

### app/actions/search.ts
- **Issue:** Sequential promise resolution in `findStrandSeeds` (lines 60-65)
- **Fix:** Use `Promise.all` for fetching quotes of semantic matches

### Duplicate Data
- `app/data/top_quoted_strands.json` duplicates `data/top_quoted_strands.json`
- Keep only one, import from there

## Testing

No tests currently. Priority test targets:

1. **lib/api.ts** - Mock Supabase, test `fetchTweetDetails` batching
2. **loadThreadColumns.ts** - Test conversation grouping logic
3. **search.ts** - Integration test `findStrandSeeds` with mocked fetch

Recommended setup: Vitest + MSW for mocking

## Conventions

- TypeScript strict mode
- Server actions in `app/actions/`
- Shared types in `lib/types.ts`
- Tailwind for styling, no CSS modules

## TODOs

- [x] Extract `batchFetch` utility in lib/api.ts
- [x] Parallelize quote fetching in findStrandSeeds
- [x] Remove duplicate JSON data files
- [x] Read rated strands from scratchpads/data/rated_strands
- [ ] Add Vitest + basic test setup
- [ ] Decompose HomePageClient into smaller hooks

