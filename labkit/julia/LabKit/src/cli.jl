# 図・チェックなどは Python の labkit CLI に委譲する（実装を一本化し、挙動の差をなくすため）

function _labkit_exe(root::AbstractString)
    for cand in (joinpath(root, ".venv", "bin", "labkit"), joinpath(root, ".venv", "Scripts", "labkit.exe"))
        isfile(cand) && return `$cand`
    end
    Sys.which("labkit") !== nothing && return `labkit`
    Sys.which("uv") !== nothing && return Cmd(`uv run labkit`; dir=root)
    error("labkit CLI が見つかりません。プロジェクトで `uv sync` を実行してください。")
end

"""
    labkit_cli(args...)

`labkit` コマンドを実行する。例: `labkit_cli("check")`, `labkit_cli("runs", "list")`
"""
function labkit_cli(args::AbstractString...; root::AbstractString=find_root())
    cmd = _labkit_exe(root)
    run(Cmd(`$cmd $args`; dir=root))
end

"""
    fig(spec; run=nothing)

図テンプレートで図を作る（`labkit fig <spec> --run <run_id>` と同じ）。`run` は Run か run ID。
"""
function fig(spec::AbstractString; run=nothing)
    args = String["fig", spec]
    if run !== nothing
        push!(args, "--run", run isa Run ? run.run_id : string(run))
    end
    labkit_cli(args...)
end

check(; full::Bool=false) = full ? labkit_cli("check", "--full") : labkit_cli("check")
