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
- `app/hooks/` - `useUrlSync`, `useTweetSelection`, `usePaneNavigation`

## Testing

Uses Vitest (`pnpm test`). Current coverage:

- `lib/api.test.ts` - `batchFetch` utility tests

Priority additions:
- `loadThreadColumns.ts` - conversation grouping logic
- `search.ts` - `findStrandSeeds` with mocked fetch

## Conventions

- TypeScript strict mode
- Server actions in `app/actions/`
- Shared types in `lib/types.ts`
- Tailwind for styling, no CSS modules

## TODOs

- [ ] Add tests for `loadThreadColumns`
- [ ] Add tests for `findStrandSeeds`

