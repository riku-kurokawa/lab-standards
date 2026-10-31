#!/usr/bin/env bash
# eval 用の最小プロジェクトを現在のディレクトリに作る（lab.toml + 標準ディレクトリ + git + run 1 件）
set -euo pipefail
printf '[lab]\nproject = "evalproj"\n[check]\nmode = "strict"\n' > lab.toml
mkdir -p src/evalproj scripts configs/experiments figspecs tests docs/devlog docs/decisions docs/reviews data/raw runs scratch .lab
printf '__all__ = []\n' > src/evalproj/__init__.py
printf 'def lowpass(x, cutoff):\n    return x\n' > src/evalproj/filters.py
printf 'extends = "../base.toml"\n[filter]\ncutoff_hz = 50\n' > configs/experiments/example.toml
printf 'seed = 0\n' > configs/base.toml
printf 'away\n' > .lab/presence
RUN="20261101-090000_example-lowpass_0d3f5c2_a8c6"
mkdir -p "runs/$RUN/figures"
cat > "runs/$RUN/meta.json" <<JSON
{"schema_version": "1", "run_id": "$RUN", "name": "example-lowpass", "status": "finished", "language": "python",
 "labkit_version": "0.3.0", "labkit_source": {"mode": "release", "version": "0.3.0"}, "created": "2026-11-01T09:00:00+09:00",
 "finished": "2026-11-01T09:00:01+09:00", "duration_s": 0.4,
 "git": {"commit": "0d3f5c2000000000000000000000000000000000", "branch": "main", "dirty": false},
 "inputs": [], "outputs": [], "tags": {}, "error": null}
JSON
printf '{"snr_db": 12.345, "n_samples": 2000}\n' > "runs/$RUN/metrics.json"
git init -q -b main
git -c user.email=eval@example.com -c user.name=eval add -A
git -c user.email=eval@example.com -c user.name=eval commit -qm "init"
