# Internal References

Written here and committed: architecture diagrams and pages that say how the system fits together, with enough prose to read them.

**A file here describes `main`.**
When the design changes, rewrite it in place, with no dated changelog and no correction paragraphs.

Nothing here cites the private parts of `docs/`.
Decision records may point at these pages; these pages state the facts themselves rather than pointing back.

Other material written here about how the system works (guides, explainers, walkthroughs) is not reference and is not committed; it stays in private notes.

| File | Shows |
|---|---|
| [`pipeline-overview.md`](pipeline-overview.md) | What the pipeline produces and what each stage does |
| [`reproduction.md`](reproduction.md) | Rebuild steps, the reproducibility contract, the reference artifact hash |
| [`data-sources.md`](data-sources.md) | The four pinned inputs: URLs, checksums, license, processing counts |
| [`known-caveats.md`](known-caveats.md) | Limits of the artifact a user needs before analyzing it |
| [`artifact-schema.md`](artifact-schema.md) | Every column of `fires_enriched.parquet` |