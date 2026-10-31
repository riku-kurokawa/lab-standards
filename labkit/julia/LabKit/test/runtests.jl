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
            end
            meta = JSON3.read(read(joinpath(run.dir, "meta.json"), String))
            @test meta["status"] == "finished" && meta["language"] == "julia"
            d = load(joinpath(run.dir, "a.h5"); verify=true)
            @test d["x"] == x && length(d["v"]) == 2000
            @test load_meta(joinpath(run.dir, "a.h5"))["attrs"]["fs"] == 100.0

            df = DataFrame(m=["a", "b"], v=[1.0, 2.0])
            p = save(datapath("processed", "t.parquet"), df)
            @test load(p; verify=true) == df
            @test_throws ErrorException save(datapath("raw", "x.h5"), Dict("x" => [1.0]))
        end
    end
end
