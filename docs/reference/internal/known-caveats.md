# Known Caveats of the Artifact

Limits a user of `artifacts/fires_enriched.parquet` needs to know before analyzing it.
Figures are from the reference build.

- 5,384 fires (23.2%) have no alarm date and 1 fire has no division; they carry null climate covariates and are never dropped, since every climate join is a left join.
  Among joinable fires, nClimDiv coverage is 100%.
  AWND coverage is 64.2% because the GSOM pull starts at 1980, so every pre-1980 fire has null `awnd_ms`.
- `coarse_geometry` flags 197 fires (0.85%) below 3.0 vertices/km, about the 1st percentile of the density distribution in `data/processed/s04_vertex_density.csv`.
- Deduplication is heuristic: rows sharing year, normalized name and alarm date collapse to one.
  FRAP itself warns duplicates may remain, and complex fires reported both per-fire and as a complex may survive as separate rows.
- FRAP's own use limitation applies: the record is incomplete (missing and over-generalized perimeters, especially pre-1950); use care in statistical analysis.
- `gis_acres` is FRAP's published value and is not recomputed.
  It matches the geometry almost everywhere (median gis_acres / geometry-acres = 1.0000, p01 = p99 = 1.0), but 9 fires over 10 acres disagree with their geometry by more than 25%.
  The worst is DOOLITTLE 2023, published at 16.6 ac against about 2.4 ac of polygon.
  These are upstream inconsistencies, kept as published.
  Use `area_km2` for geometry-derived size.
- Climate values are division-scale monthly context, not at-fire weather.
- `alarm_year` can differ from `year`: the 1958 DAM fire has alarm_date 1957-07-02.
  Climate joins on the alarm month, not on `year`.
- `fire_id` is stable only within one FRAP release, because it hashes the source row position.
- Geometry-derived floats are byte-identical only per platform; a Linux rebuild differs from the macOS reference in trailing digits.
