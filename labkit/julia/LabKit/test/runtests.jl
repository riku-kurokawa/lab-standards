using Test, LabKit, DataFrames, JSON3

@testset "LabKit" begin
    mktempdir() do dir
        write(joinpath(dir, "lab.toml"), "[lab]\nproject = \"t\"\n")
        for d in ("configs", "data/raw", "data/processed", "runs")
            mkpath(joinpath(dir, d))
        end
        write(joinpath(dir, "configs", "base.toml"), "seed = 0\n[filter]\ncutoff = 10\n")
        write(joinpath(dir, "configs", "exp.toml"), "extends = \"base.toml\"\n[filter]\ncutoff = 50\n")
        cd(dir) do
            cfg = load_config("configs/exp.toml"; overrides=["filter.order=8"])
            @test cfg["filter"]["cutoff"] == 50 && cfg["filter"]["order"] == 8 && cfg["seed"] == 0

            x = reshape(collect(1.0:12.0), 3, 4)
            run = Run("jl test", cfg) do run
                save(runpath(run, "a.h5"), Dict("x" => x, "v" => collect(1:2000)); attrs=Dict("fs" => 100.0))
                log_metric(run, "loss", 0.5; step=1)
                write(datapath("raw", "in.bin"), "abc")
                add_input(run, datapath("raw", "in.bin"))
                log_message(run, "hello")
            end
            meta = JSON3.read(read(joinpath(run.dir, "meta.json"), String))
            @test occursin("hello", read(joinpath(run.dir, "log.txt"), String))
            @test length(meta["inputs"]) == 1 && meta["inputs"][1]["sha256_source"] == "computed"
            p2 = writer(datapath("interim", "big.bin"); fmt="raw") do tmp; write(tmp, "xyz"); end
            @test read(p2, String) == "xyz" && load_meta(p2)["format"] == "raw"
            @test meta["status"] == "finished" && meta["language"] == "julia"
            # JSON の数値は Python と同じ型で書く（2.0 を 2 にしない）
            @test occursin(r"\"duration_s\": \d+\.\d+", read(joinpath(run.dir, "meta.json"), String))
            pj = LabKit.write_json_atomic(joinpath(dir, "j.json"), Dict("f" => 2.0, "i" => 2, "e" => Dict(), "s" => "a\"{b"))
            txt = read(pj, String)
            @test occursin("\"f\": 2.0", txt) && occursin("\"i\": 2,", txt) && occursin("\"e\": {}", txt)
            @test JSON3.read(txt, Dict{String,Any})["s"] == "a\"{b"
            d = load(joinpath(run.dir, "a.h5"); verify=true)
            @test d["x"] == x && length(d["v"]) == 2000
            @test load_meta(joinpath(run.dir, "a.h5"))["attrs"]["fs"] == 100.0
            # 完了した run はコピーを通常の手段で削除できる（Windows の ACL 問題の回帰テスト）
            tmp = joinpath(dir, "copy"); cp(run.dir, tmp); rm(tmp; recursive=true, force=true)
            @test !ispath(tmp)

            df = DataFrame(m=["a", "b"], v=[1.0, 2.0])
            p = save(datapath("processed", "t.parquet"), df)
            @test load(p; verify=true) == df
            @test_throws ErrorException save(datapath("raw", "x.h5"), Dict("x" => [1.0]))
        end
    end
end
