# run 管理（Python 版 runs.py と同じディレクトリ構成・同じ meta.json）

mutable struct Run
    root::String
    lab::Dict{String,Any}
    name::String
    config::Dict{String,Any}
    tags::Dict{String,Any}
    run_id::String
    dir::String
    git::Union{Nothing,Dict{String,Any}}
    t0::Float64
    last::Dict{String,Float64}
    meta::Dict{String,Any}
end

const _CURRENT = Ref{Any}(nothing)
current_run() = _CURRENT[]

function make_run_id(name::AbstractString, commit)
    ts = Dates.format(now(), "yyyymmdd-HHMMSS")
    short = commit === nothing ? "nogit" : commit[1:7]
    return "$(ts)_$(slugify(name))_$(short)_$(bytes2hex(rand(UInt8, 2)))"
end

function _manifest_lookup(root::AbstractString)
    raw = datapath("raw"; root=root)
    mf = joinpath(raw, "MANIFEST.sha256")
    out = Dict{String,String}()
    isfile(mf) || return out
    for line in eachline(mf)
        startswith(line, "#") && continue
        parts = split(line, limit=3)
        length(parts) == 3 && (out[abspath(joinpath(raw, parts[3]))] = parts[1])
    end
    return out
end

function describe_input(path::AbstractString, root::AbstractString, max_bytes::Real, manifest::AbstractDict)
    p = abspath(path)
    rec = Dict{String,Any}("path" => rel_or_abs(p, root), "exists" => ispath(p))
    ispath(p) || return rec
    sz = tree_size(p)
    rec["size"] = sz
    rec["mtime"] = Dates.format(unix2datetime(mtime(p)), "yyyy-mm-ddTHH:MM:SS")
    sidecar = p * ".meta.json"
    if haskey(manifest, p)
        rec["sha256"] = manifest[p]; rec["sha256_source"] = "manifest"
    elseif isfile(sidecar)
        rec["sha256"] = read_json(sidecar)["sha256"]; rec["sha256_source"] = "sidecar"
    elseif sz <= max_bytes
        rec["sha256"] = isfile(p) ? sha256_file(p) : sha256_tree(p); rec["sha256_source"] = "computed"
    else
        rec["sha256"] = nothing; rec["sha256_source"] = "skipped_too_large"
    end
    return rec
end

_max_bytes(lab) = Float64(lab["runs"]["hash_inputs_max_gb"]) * 1024^3

function start_run(name::AbstractString, config::AbstractDict=Dict{String,Any}();
                   inputs::AbstractVector=String[], tags::AbstractDict=Dict{String,Any}(),
                   root::AbstractString=find_root())
    lab = load_lab(root)
    cfg = Dict{String,Any}(string(k) => v for (k, v) in config)
    files = pop!(cfg, "_files", String[])
    overrides = pop!(cfg, "_overrides", String[])
    git = git_info(root)
    run_id = make_run_id(name, git === nothing ? nothing : git["commit"])
    dir = joinpath(runs_root(root), run_id)
    ispath(dir) && error("run ディレクトリが既に存在します: $dir")
    mkpath(joinpath(dir, "figures"))
    if !isempty(files)
        mkpath(joinpath(dir, "config"))
        for f in files
            cp(f, joinpath(dir, "config", basename(f)))
        end
    end
    write_json_atomic(joinpath(dir, "config.json"), cfg)
    manifest = _manifest_lookup(root)
    meta = Dict{String,Any}(
        "schema_version" => SCHEMA_VERSION,
        "run_id" => run_id,
        "name" => String(name),
        "status" => "running",
        "language" => "julia",
        "language_version" => string(VERSION),
        "labkit_version" => LABKIT_VERSION,
        "labkit_source" => labkit_source(),
        "created" => now_iso(),
        "finished" => nothing,
        "duration_s" => nothing,
        "host" => gethostname(),
        "lab_env" => env_name(),
        "git" => git,
        "slurm" => slurm_info(),
        "command" => vcat([Base.julia_cmd().exec[1], something(Base.PROGRAM_FILE, "")], ARGS),
        "cwd" => pwd(),
        "config_files" => [rel_or_abs(f, root) for f in files],
        "config_overrides" => overrides,
        "inputs" => [describe_input(string(p), root, _max_bytes(lab), manifest) for p in inputs],
        "outputs" => Any[],
        "tags" => Dict{String,Any}(string(k) => v for (k, v) in tags),
        "error" => nothing,
    )
    write_json_atomic(joinpath(dir, "meta.json"), meta)
    run = Run(root, lab, String(name), cfg, meta["tags"], run_id, dir, git, time(), Dict{String,Float64}(), meta)
    _CURRENT[] = run
    if git !== nothing && git["dirty"]
        log_message(run, "警告: 未コミットの変更がある状態で実行しています（meta.json の git.dirty=true）")
    end
    if meta["labkit_source"]["mode"] == "link"
        log_message(run, "注意: LabKit は手元の lab-standards を参照中（link）。この run は正式版の結果ではありません")
    end
    return run
end

function finish_run!(run::Run, status::AbstractString, err)
    _CURRENT[] = nothing
    run.meta["finished"] = now_iso()
    run.meta["duration_s"] = round(time() - run.t0; digits=3)
    run.meta["status"] = status
    run.meta["error"] = err === nothing ? nothing : last(err, 4000)
    write_json_atomic(joinpath(run.dir, "metrics.json"), run.last)
    outputs = Any[]
    for (d, _, fs) in walkdir(run.dir), f in fs
        rel = relpath(joinpath(d, f), run.dir)
        (rel == "meta.json" || startswith(rel, "figures")) && continue
        push!(outputs, Dict("path" => rel, "size" => filesize(joinpath(d, f))))
    end
    run.meta["outputs"] = sort(outputs; by=o -> o["path"])
    write_json_atomic(joinpath(run.dir, "meta.json"), run.meta)
    freeze_run(run.dir)
    return run
end

function freeze_run(dir::AbstractString)
    for (d, subdirs, fs) in walkdir(dir; topdown=false)
        rel = relpath(d, dir)
        (rel == "figures" || startswith(rel, "figures/")) && continue
        for f in fs
            chmod(joinpath(d, f), 0o444)
        end
        d == dir || chmod(d, 0o555)
    end
end

"""
    Run(f, name, config=Dict(); inputs=[], tags=Dict())

do ブロックで使う。正常終了で status=finished、例外で failed（例外は再送出）。
"""
function Run(f::Function, name::AbstractString, config::AbstractDict=Dict{String,Any}(); kwargs...)
    run = start_run(name, config; kwargs...)
    try
        f(run)
    catch e
        status = e isa InterruptException ? "interrupted" : "failed"
        finish_run!(run, status, sprint(showerror, e, catch_backtrace()))
        rethrow()
    end
    finish_run!(run, "finished", nothing)
    return run
end

function runpath(run::Run, parts::AbstractString...)
    p = joinpath(run.dir, parts...)
    mkpath(dirname(p))
    return p
end

function log_metric(run::Run, key::AbstractString, value::Real; step=nothing)
    rec = Dict("key" => key, "value" => Float64(value), "step" => step, "time" => time())
    open(joinpath(run.dir, "metrics.jsonl"), "a") do io
        println(io, JSON3.write(rec))
    end
    run.last[String(key)] = Float64(value)
    return nothing
end

function log_message(run::Run, msg::AbstractString)
    line = "[$(now_iso())] $msg"
    println(line)
    open(io -> println(io, line), joinpath(run.dir, "log.txt"), "a")
    return nothing
end

function add_input(run::Run, path::AbstractString)
    push!(run.meta["inputs"], describe_input(path, run.root, _max_bytes(run.lab), _manifest_lookup(run.root)))
    write_json_atomic(joinpath(run.dir, "meta.json"), run.meta)
end
