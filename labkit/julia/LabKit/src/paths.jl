# 環境ごとのパス解決（Python 版 paths.py と同じ挙動）

const STAGES = ("raw", "external", "interim", "processed")

env_name() = get(ENV, "LAB_ENV", "local")

function load_paths(root::AbstractString=find_root())
    cfg = Dict{String,Any}("data_root" => "data", "runs_root" => "runs")
    f = joinpath(root, "configs", "paths", "$(env_name()).toml")
    if isfile(f)
        merge!(cfg, TOML.parsefile(f))
    elseif env_name() != "local"
        error("LAB_ENV=$(env_name()) ですが $f がありません")
    end
    out = Dict{String,String}()
    for (k, v) in cfg
        p = expanduser(_expandvars(string(v)))
        out[k] = isabspath(p) ? p : joinpath(root, p)
    end
    return out
end

"""
    datapath(stage, parts...; root=find_root())

`datapath("processed", "features.parquet")` → `<data_root>/processed/features.parquet`
"""
function datapath(stage::AbstractString, parts::AbstractString...; root::AbstractString=find_root())
    stage in STAGES || error("stage は $(STAGES) のいずれか: $stage")
    return joinpath(load_paths(root)["data_root"], stage, parts...)
end

runs_root(root::AbstractString=find_root()) = load_paths(root)["runs_root"]

function readonly_roots(root::AbstractString)
    lab = load_lab(root)
    ro = [abspath(joinpath(root, p)) for p in lab["layout"]["readonly"]]
    push!(ro, abspath(datapath("raw"; root=root)))
    return ro
end
