# lab.toml とプロジェクトルート、実験設定（Python 版 config.py / runconfig.py と同じ挙動）

const DEFAULT_LAB = Dict{String,Any}(
    "layout" => Dict{String,Any}("readonly" => ["data/raw", "legacy"]),
    "runs" => Dict{String,Any}("hash_inputs_max_gb" => 2.0),
)

"""
    find_root(start=pwd())

`lab.toml` を含むディレクトリを上方向に探す。環境変数 `LAB_PROJECT_ROOT` が優先。
"""
function find_root(start::AbstractString=pwd())
    haskey(ENV, "LAB_PROJECT_ROOT") && return abspath(expanduser(ENV["LAB_PROJECT_ROOT"]))
    d = abspath(start)
    isfile(d) && (d = dirname(d))
    while true
        isfile(joinpath(d, "lab.toml")) && return d
        parent = dirname(d)
        parent == d && error("lab.toml が $start から上位に見つかりません。lab-standards で生成したプロジェクト内で実行してください。")
        d = parent
    end
end

load_lab(root::AbstractString=find_root()) = deep_merge(DEFAULT_LAB, TOML.parsefile(joinpath(root, "lab.toml")))

function _load_with_extends(path::AbstractString, seen::Set{String})
    path = abspath(path)
    path in seen && error("extends が循環しています: $path")
    push!(seen, path)
    cfg = Dict{String,Any}(TOML.parsefile(path))
    files = [path]
    parent = pop!(cfg, "extends", nothing)
    if parent !== nothing
        base, base_files = _load_with_extends(joinpath(dirname(path), parent), seen)
        cfg = deep_merge(base, cfg)
        files = vcat(base_files, files)
    end
    return cfg, files
end

function _parse_value(s::AbstractString)
    try
        return TOML.parse("v = $s")["v"]
    catch
        return String(s)
    end
end

"""
    load_config(path; overrides=String[])

TOML 設定を読む。`extends = "../base.toml"` で継承、`overrides=["filter.cutoff_hz=80"]` で上書き。
"""
function load_config(path::AbstractString; overrides::AbstractVector{<:AbstractString}=String[])
    cfg, files = _load_with_extends(path, Set{String}())
    for item in overrides
        occursin('=', item) || error("上書きは key=value 形式: $item")
        key, val = split(item, '='; limit=2)
        parts = split(strip(key), '.')
        node = cfg
        for h in parts[1:end-1]
            node = get!(node, String(h), Dict{String,Any}())
        end
        node[String(parts[end])] = _parse_value(strip(val))
    end
    cfg["_files"] = files
    cfg["_overrides"] = collect(String, overrides)
    return cfg
end
