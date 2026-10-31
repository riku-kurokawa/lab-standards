# データの保存・読込（Python 版 io.py と同じ形式・同じサイドカー）

const ARRAY_EXT = (".h5", ".hdf5")
const TABLE_EXT = (".parquet",)

function _check_writable(path::AbstractString, root::AbstractString)
    p = normpath(abspath(path))
    for ro in readonly_roots(root)
        ro = normpath(ro)
        (p == ro || startswith(p, joinpath(ro, ""))) &&
            error("$p は読み取り専用領域（$ro）です。派生データは interim/processed か run へ。")
    end
end

_ext(path) = lowercase(splitext(path)[2])

function _write_sidecar(path, fmt, root, attrs, inputs, description)
    run = current_run()
    meta = Dict{String,Any}(
        "schema_version" => SCHEMA_VERSION,
        "file" => basename(path),
        "format" => fmt,
        "sha256" => isfile(path) ? sha256_file(path) : sha256_tree(path),
        "size" => tree_size(path),
        "created" => now_iso(),
        "created_by" => "labkit-julia $(LABKIT_VERSION)",
        "run_id" => run === nothing ? nothing : run.run_id,
        "git" => run === nothing ? git_info(root) : run.git,
        "inputs" => [describe_input(string(p), root, 2 * 1024^3, Dict{String,String}()) for p in inputs],
        "attrs" => Dict{String,Any}(string(k) => v for (k, v) in attrs),
        "description" => description,
    )
    write_json_atomic(path * ".meta.json", meta)
end

# Julia（列優先）と Python（行優先）で同じ shape に見えるよう、2 次元以上は軸を反転して保存
_to_c(a::AbstractArray) = ndims(a) > 1 ? permutedims(a, ndims(a):-1:1) : a
_from_c(a) = a isa AbstractArray && ndims(a) > 1 ? permutedims(a, ndims(a):-1:1) : a

function _put!(g, d::AbstractDict)
    for (k, v) in d
        k = string(k)
        if v isa AbstractDict
            _put!(create_group(g, k), v)
        elseif v isa AbstractArray && length(v) > 1024 && isbitstype(eltype(v))
            arr = _to_c(v)
            chunk = map(s -> min(s, 4096), size(arr))
            ds = create_dataset(g, k, eltype(arr), size(arr); chunk=chunk, deflate=4)
            write(ds, arr)
        elseif v isa AbstractArray
            g[k] = _to_c(collect(v))
        else
            g[k] = v
        end
    end
end

_attr(v) = v isa AbstractDict ? JSON3.write(v) : v

"""
    save(path, data; attrs=Dict(), inputs=[], description="", overwrite=false)

拡張子で形式を決める: `.h5`（Dict{String,配列}）/ `.parquet`（DataFrame など Tables 互換）。
一時ファイル → rename、サイドカー `<file>.meta.json` を書く。
"""
function save(path::AbstractString, data; attrs::AbstractDict=Dict{String,Any}(),
              inputs::AbstractVector=String[], description::AbstractString="", overwrite::Bool=false)
    root = find_root(isdir(dirname(abspath(path))) ? dirname(abspath(path)) : pwd())
    _check_writable(path, root)
    ispath(path) && !overwrite && error("$path は既に存在します。再生成なら overwrite=true を明示してください。")
    mkpath(dirname(abspath(path)))
    ext = _ext(path)
    tmp = tmp_sibling(abspath(path))
    local fmt
    try
        if ext in ARRAY_EXT
            data isa AbstractDict || error("HDF5 には Dict(名前 => 配列) を渡してください")
            h5open(tmp, "w") do f
                a = HDF5.attributes(f)
                a["labkit_array_order"] = "C"
                a["labkit_version"] = LABKIT_VERSION
                for (k, v) in attrs
                    a[string(k)] = _attr(v)
                end
                _put!(f, data)
            end
            fmt = "hdf5"
        elseif ext in TABLE_EXT
            Parquet2.writefile(tmp, data)
            fmt = "parquet"
        else
            error("save() が扱わない拡張子です: $ext（.h5 / .parquet）。それ以外は writer() を使う。")
        end
        mv(tmp, path; force=true)
    finally
        ispath(tmp) && rm(tmp; force=true, recursive=true)
    end
    _write_sidecar(path, fmt, root, attrs, inputs, description)
    return path
end

"""
    writer(f, path; fmt=nothing, attrs=Dict(), inputs=[], description="", overwrite=false)

任意のライブラリで書く大規模ファイル用。`f(tmp)` に一時パスを渡し、成功したら rename + サイドカー。

```julia
writer(datapath("interim", "big.h5")) do tmp
    h5open(tmp, "w") do f
        ds = create_dataset(f, "x", Float64, (m, n); chunk=(m, 1))
        for j in 1:n; ds[:, j] = compute(j); end
    end
end
```
注意: writer 内で HDF5.jl を直接使う場合、Python からは軸が逆順に見える。揃えたい場合は書く前に転置する。
"""
function writer(f::Function, path::AbstractString; fmt=nothing, attrs::AbstractDict=Dict{String,Any}(),
                inputs::AbstractVector=String[], description::AbstractString="", overwrite::Bool=false)
    root = find_root(isdir(dirname(abspath(path))) ? dirname(abspath(path)) : pwd())
    _check_writable(path, root)
    ispath(path) && !overwrite && error("$path は既に存在します（overwrite=true で再生成）")
    mkpath(dirname(abspath(path)))
    tmp = tmp_sibling(abspath(path))
    try
        f(tmp)
        ispath(tmp) || error("writer の一時パス $tmp に何も書かれていません")
        mv(tmp, path; force=true)
    catch
        ispath(tmp) && rm(tmp; force=true, recursive=true)
        rethrow()
    end
    _write_sidecar(path, something(fmt, lstrip(_ext(path), '.')), root, attrs, inputs, description)
    return path
end

function _get(g)
    out = Dict{String,Any}()
    for k in keys(g)
        obj = g[k]
        out[k] = obj isa HDF5.Group ? _get(obj) : _from_c(read(obj))
    end
    return out
end

"""
    load(path; verify=false)

HDF5 → Dict{String,Any}、Parquet → DataFrame。`verify=true` でサイドカーの sha256 と照合。
"""
function load(path::AbstractString; verify::Bool=false)
    # 先に確かめる: verify ではサイドカーの不在が先に見つかり、原因を取り違えさせる
    ispath(path) || error("$path がありません")
    if verify
        meta = load_meta(path)
        actual = isfile(path) ? sha256_file(path) : sha256_tree(path)
        actual == meta["sha256"] || error("$path の sha256 がサイドカーと一致しません（改変または破損）")
    end
    ext = _ext(path)
    ext in ARRAY_EXT && return h5open(_get, path, "r")
    if ext in TABLE_EXT
        # mmap を使わない: mmap は GC までファイルを掴み続け、Windows では削除・上書きできなくなる
        ds = Parquet2.Dataset(path; use_mmap=false)
        try
            return DataFrame(ds; copycols=true)
        finally
            close(ds)
        end
    end
    error("load() が扱わない拡張子です: $ext")
end

function load_meta(path::AbstractString)
    sc = path * ".meta.json"
    isfile(sc) || error("サイドカー $sc がありません（labkit の save 以外で作られたファイル？）")
    return read_json(sc)
end
