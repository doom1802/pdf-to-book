# Repository guidance for coding agents

- This project converts digital PDFs to EPUB 3. The package is in `pdf_to_book/`; the CLI is `pdf_to_book/__main__.py`.
- Use `docs/architecture.md` when changing the intermediate book format or EPUB boundaries. Use `docs/performance.md` for performance work.
- Run `python -m unittest discover -s tests -v` for package changes and `python -m unittest discover -s benchmark/golden -p 'test_*.py' -v` for benchmark code. These commands use disposable outputs and may run without additional approval.
- Local integration tests use PDFs and derived annotations supplied by the developer. They skip when those files are absent.
- Never commit third-party PDFs, their extracted text or images, golden annotations derived from them, model caches, generated EPUBs, or local profiling output. Use synthetic or properly licensed fixtures for public tests.
- Keep changes focused. Preserve deterministic EPUB output when `SOURCE_DATE_EPOCH` is set and report any known validation gaps.
