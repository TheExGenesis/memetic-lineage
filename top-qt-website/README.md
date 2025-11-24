# Community Archive Top QT Website

This is a website that displays the top QT tweets from the Community Archive. They are most likely to be in the "canon".

We start with the **dataframe** dump of all tweets from the Community Archive.

We simply count how many times a tweet is quoted by users other than the original poster.

We then display the top tweets with the ability to agreggate by time period, with one column for each of the last few years, the last month and week.

## Architecture
- Next.js React website (Tailwind CSS)
- Supabase for database
- Modal for cron task to calculate the top QT tweets from the df dump and store in the database

## Tasks
- [ ] Create supabase db
- [ ] Create static data for first website
- [ ] Store data in supabase db
- [ ] Create website
- [ ] Host website on Vercel
- [ ] (Extra) Create cron task to calculate the top QT tweets from the df dump and store in the database