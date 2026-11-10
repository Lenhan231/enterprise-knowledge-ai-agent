# QuocAn adoption

Adopted Huy's eight evaluation commits from `8fe0dbf` through
`9c06a2b583348ec78617bffb3587c6ce3e87c4e5`, with source hashes recorded
in the cherry-pick commit messages. Checked against `origin/main` at `5357579`.

The scorer includes the original Vietnamese policy Markdown for offline judging.
Run and score JSON files use UTF-8, including on Windows.

QuocAn currently lacks Huy's claim-verification runtime. Retrieval arm A,
closed-book B0, unverified B1/B4 and HTTP E2E can use their existing backends.
B2/B3/B5/B6/B7 stop explicitly when the backend lacks `verify_claims`;
they must run against a verifier-enabled backend to preserve their meaning.
E2E evaluates whichever backend is listening at `--base-url`.

The deterministic scorer and paired comparison work without the verifier module.
Live retrieval, generation, HTTP and LLM judging require their configured services.
