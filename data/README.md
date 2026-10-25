# Data

- `samples/`: anonymized sample bills for tests and demos. No real patient names, IP numbers, or hospital bills.
- `private/`: gitignored. Keep any real bills here, and only on your own machine.

## Reference prices

`samples/reference-prices.json` is **illustrative**: made-up figures so the audit has something
to run against. Every entry is marked `"source": "sample"`, and the API leaves sample prices out
unless `ALLOW_SAMPLE_PRICES=true`, which only the tests set. Outside them, no price flag is raised
until a real, sourced list is loaded.

A real price names where it came from in `source` (for example `"nppa"`). An entry with no
`source` is treated as a sample: nothing is a real price by default.
