import os
import sys
import time
import cProfile
import pstats
import io
import psutil
try:
    import flameprof
except ImportError:
    flameprof = None

# Ensure the app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from suspensionlab.physics.quarter_car import (
    QuarterCarParams,
    RoadProfile,
    run_quarter_car_analysis
)
from suspensionlab.physics.optimizer import optimize_setup

def benchmark_physics():
    print("--- Profiling Single Physics Engine Run ---")
    p = QuarterCarParams(m_s=1000)
    r = RoadProfile(duration=10.0)
    
    pr = cProfile.Profile()
    pr.enable()
    run_quarter_car_analysis(p, r)
    pr.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    
    print(s.getvalue())
    
    if flameprof:
        with open("physics_flamegraph.svg", "w") as f:
            flameprof.render(ps.stats, f)
        print("Generated physics_flamegraph.svg")
        
    process = psutil.Process(os.getpid())
    print(f"Memory Usage (Single Physics run): {process.memory_info().rss / 1024 / 1024:.2f} MB")


def benchmark_optimization():
    print("\n--- Profiling Optimization Workflow ---")
    p = QuarterCarParams(m_s=1000)
    r = RoadProfile(duration=5.0) # Shorter duration for opt test
    
    pr = cProfile.Profile()
    pr.enable()
    res = optimize_setup(p, r, objective_type="Ride Comfort", max_travel=0.08)
    pr.disable()
    
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    
    print(s.getvalue())
    print(f"Optimization result: {res}")
    
    if flameprof:
        with open("optimization_flamegraph.svg", "w") as f:
            flameprof.render(ps.stats, f)
        print("Generated optimization_flamegraph.svg")

    process = psutil.Process(os.getpid())
    print(f"Memory Usage (Post-Optimization): {process.memory_info().rss / 1024 / 1024:.2f} MB")


def main():
    print("Beginning Complete Application Profiling...")
    benchmark_physics()
    benchmark_optimization()
    
if __name__ == "__main__":
    main()
