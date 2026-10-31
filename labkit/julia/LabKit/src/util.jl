# 内部ユーティリティ（Python 版 _util.py と同じ挙動）

sha256_file(path::AbstractString) = open(io -> bytes2hex(sha256(io)), path, "r")

function sha256_tree(path::AbstractString)
    files = String[]
    for (d, _, fs) in walkdir(path), f in fs
        push!(files, joinpath(d, f))
    end
    ctx = SHA.SHA256_CTX()
    for f in sort(files)
        SHA.update!(ctx, Vector{UInt8}(relpath(f, path)))
        SHA.update!(ctx, hex2bytes(sha256_file(f)))
    end
    return bytes2hex(SHA.digest!(ctx))
end

function now_iso()
    t = now()
    offset_min = round(Int, Dates.value(t - now(UTC)) / 60_000)
    sign = offset_min >= 0 ? "+" : "-"
    h, m = divrem(abs(offset_min), 60)
    return Dates.format(t, "yyyy-mm-ddTHH:MM:SS") * sign * lpad(h, 2, '0') * ":" * lpad(m, 2, '0')
end

tmp_sibling(path::AbstractString) =
    joinpath(dirname(path), ".$(basename(path)).tmp-$(getpid())-$(randstring(6))")

"""JSON3.write の出力を再パースせずに字下げする。
JSON3.pretty は数値を読み直して 2.0 を 2 にしてしまい、Python（json.dumps）が書く meta.json / サイドカーと型が食い違う。
出力は Python の `json.dumps(indent=2, ensure_ascii=False)` と同じ形。"""
function write_json_pretty(io::IO, obj; indent::Int=2)
    s = codeunits(JSON3.write(obj))
    level, instr, esc, i = 0, false, false, 1
    nl() = print(io, '\n', ' '^(indent * level))
    while i <= length(s)
        c = Char(s[i])
        if instr
            write(io, s[i])
            esc ? (esc = false) : c == '\\' ? (esc = true) : c == '"' && (instr = false)
        elseif c == '"'
            instr = true
            write(io, s[i])
        elseif c == '{' || c == '['
            write(io, s[i])
            if s[i + 1] == UInt8(c == '{' ? '}' : ']')   # 空の {} / [] は 1 行（Python と同じ）
                write(io, s[i + 1])
                i += 1
            else
                level += 1
                nl()
            end
        elseif c == '}' || c == ']'
            level -= 1
            nl()
            write(io, s[i])
        elseif c == ','
            write(io, s[i])
            nl()
        elseif c == ':'
            print(io, ": ")
        else
            write(io, s[i])
        end
        i += 1
    end
end

function write_json_atomic(path::AbstractString, obj)
    mkpath(dirname(path))
    tmp = tmp_sibling(path)
    open(tmp, "w") do io
        write_json_pretty(io, obj)
        println(io)
    end
    mv(tmp, path; force=true)
    return path
end

read_json(path::AbstractString) = JSON3.read(read(path, String), Dict{String,Any})

function _git(root, args...)
    readchomp(pipeline(Cmd(`git $args`; dir=root); stderr=devnull))
end

function git_info(root::AbstractString)
    commit = try
        _git(root, "rev-parse", "HEAD")
    catch
        return nothing
    end
    branch = try
        _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    catch
        ""
    end
    dirty = !isempty(_git(root, "status", "--porcelain", "--untracked-files=no"))
    return Dict{String,Any}("commit" => commit, "branch" => branch, "dirty" => dirty)
end

"""LabKit がリリース版か、手元の本体チェックアウト（link）かを記録する。"""
function labkit_source()
    d = dirname(@__DIR__)  # .../LabKit
    while true
        if isfile(joinpath(d, "copier.yml")) && isdir(joinpath(d, "labkit", "python"))
            return Dict{String,Any}("mode" => "link", "version" => LABKIT_VERSION, "path" => d, "git" => git_info(d))
        end
        parent = dirname(d)
        parent == d && break
        d = parent
    end
    return Dict{String,Any}("mode" => "release", "version" => LABKIT_VERSION)
end

function slurm_info()
    haskey(ENV, "SLURM_JOB_ID") || return nothing
    keys = ("job_id" => "SLURM_JOB_ID", "array_job_id" => "SLURM_ARRAY_JOB_ID",
            "array_task_id" => "SLURM_ARRAY_TASK_ID", "partition" => "SLURM_JOB_PARTITION",
            "nodelist" => "SLURM_JOB_NODELIST")
    return Dict{String,Any}(k => get(ENV, v, nothing) for (k, v) in keys)
end

function slugify(s::AbstractString)
    out = lowercase(strip(replace(s, r"[^0-9A-Za-z]+" => "-"), '-'))
    return isempty(out) ? "run" : out
end

function deep_merge(a::AbstractDict, b::AbstractDict)
    out = Dict{String,Any}(string(k) => v for (k, v) in a)
    for (k, v) in b
        k = string(k)
        if v isa AbstractDict && get(out, k, nothing) isa AbstractDict
            out[k] = deep_merge(out[k], v)
        else
            out[k] = v
        end
    end
    return out
end

function rel_or_abs(path::AbstractString, root::AbstractString)
    p, r = abspath(path), abspath(root)
    return startswith(p, rstrip(r, '/') * "/") ? relpath(p, r) : p
end

function _expandvars(s::AbstractString)
    replace(s, r"\$\{?(\w+)\}?" => m -> get(ENV, strip(m, ['$', '{', '}']), m))
end

function tree_size(path::AbstractString)
    isfile(path) && return filesize(path)
    total = 0
    for (d, _, fs) in walkdir(path), f in fs
        total += filesize(joinpath(d, f))
    end
    return total
end
