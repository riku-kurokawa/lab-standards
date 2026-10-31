"""
    LabKit

labkit（Python）と同じ関数名・同じファイル形式を Julia で提供する。

```julia
using LabKit
cfg = load_config("configs/experiments/example.toml")
Run("example", cfg; inputs=[datapath("raw", "rec01.h5")]) do run
    save(runpath(run, "signal.h5"), Dict("t" => t, "x" => x); attrs=Dict("fs" => 1000.0))
    log_metric(run, "snr_db", 12.3; step=0)
end
fig("figspecs/example_timeseries.toml"; run=run)   # 図は labkit CLI（Python）に委譲
```

配列の軸順: Julia の size (n_ch, n_t) の配列は、Python でも shape (n_ch, n_t) で読める
（保存・読込時に軸を反転して HDF5 上は C 順に揃える）。
"""
module LabKit

using Dates, SHA, TOML, Random
using JSON3, HDF5, DataFrames, Parquet2

export find_root, load_lab, load_config,
       Run, runpath, log_metric, log_message, add_input,
       save, load, load_meta, writer,
       datapath, runs_root, fig, check, cite, labkit_cli

const LABKIT_VERSION = "0.3.0"
const SCHEMA_VERSION = "1"

include("util.jl")
include("config.jl")
include("paths.jl")
include("runs.jl")
include("io.jl")
include("cli.jl")

end # module
