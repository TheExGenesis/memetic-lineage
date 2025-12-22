export default function AboutPage() {
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        <header className="mb-12 border-b-4 border-black pb-6">
          <div className="flex items-center gap-4 mb-4">
            <a
              href="/"
              className="p-2 hover:bg-gray-100 transition-colors border border-transparent hover:border-black"
              title="Back to home"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 12H5" />
                <path d="M12 19l-7-7 7-7" />
              </svg>
            </a>
            <h1 className="text-5xl font-bold tracking-tighter">About</h1>
          </div>
        </header>

        <main className="space-y-10 text-lg leading-relaxed">
          <section>
            <h2 className="text-3xl font-bold mb-4">
              What is the Community Archive?
            </h2>
            <p>
              An open database and API of Twitter data anyone can build on. Currently contains millions of tweets from hundreds of contributors.
            </p>
            <p className="mt-4">
              Learn more at{' '}
              <a
                href="https://www.community-archive.org/"
                target="_blank"
                rel="noopener noreferrer"
                className="underline font-bold hover:opacity-70"
              >
                community-archive.org
              </a>
            </p>
          </section>

          <section>
            <h2 className="text-3xl font-bold mb-4">
              What are Bangers?
            </h2>
            <p>
              Tweets ranked by quote count from third parties (excluding self-quotes). Shows the most quoted tweets by year, month, and week.
            </p>
          </section>

          <section>
            <h2 className="text-3xl font-bold mb-4">
              Why This Matters
            </h2>
            <p>
              We&apos;re building community-owned infrastructure to increase agency over cultural production. 
            </p>
            <p className="mt-4">
            Quote counts by the community are a strong signal that a tweet is valuable—these tweets get referenced many times. There are more elaborate metrics we could use, but this one is simple and effective. 
            </p>
            <p className="mt-4">These highly-quoted tweets serve as starting points for research on how ideas spread, helping us trace influences and impacts across the network.</p>
          </section>

          <section className="bg-black text-white p-8 -mx-4 sm:-mx-6 lg:-mx-8">
            <h2 className="text-3xl font-bold mb-6">
              Contribute
            </h2>
            <div className="space-y-6">
              <div>
                <h3 className="text-xl font-bold mb-3">Upload Your Archive</h3>
                <p className="mb-3">
                  Export your data from X: <a href="https://x.com/settings/download_your_data" target="_blank" rel="noopener noreferrer" className="underline">x.com/settings/download_your_data</a>
                </p>
                <a
                  href="https://www.community-archive.org/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block bg-white text-black font-bold py-3 px-6 hover:bg-gray-200 transition-colors"
                >
                  Upload at community-archive.org →
                </a>
              </div>

              <div className="pt-4">
                <h3 className="text-xl font-bold mb-3">Stream Extension</h3>
                <p className="mb-3">
                  Install the browser extension to stream tweets to the archive as you browse X/Twitter.
                </p>
                <a
                  href="https://chromewebstore.google.com/detail/community-archive-stream/igclpobjpjlphgllncjcgaookmncegbk"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block bg-white text-black font-bold py-3 px-6 hover:bg-gray-200 transition-colors"
                >
                  Chrome Extension →
                </a>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  )
}

