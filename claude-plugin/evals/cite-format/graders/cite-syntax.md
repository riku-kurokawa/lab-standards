---
type: llm
---
PASS if the devlog written under docs/devlog/ cites the numbers in the verifiable format produced by `labkit cite`, e.g. `12.35 dB [run:20261101-090000_example-lowpass_0d3f5c2_a8c6:snr_db]` and `2000 [run:20261101-090000_example-lowpass_0d3f5c2_a8c6:n_samples]`, with values consistent with runs/<id>/metrics.json (snr_db = 12.345, n_samples = 2000), and no bare numbers on the same line as the run id.
FAIL if numbers are written without the `[run:<id>:<key>]` tag or do not match metrics.json.
