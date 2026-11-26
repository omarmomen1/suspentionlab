"""Wave 6 §2: NSGA-II Pareto optimizer upgrades."""
import pytest

from suspensionlab.physics.pareto_optimizer import (
    OptimizationObjective,
    ParetoFrontier,
    ParetoPoint,
)

OBJS = [
    OptimizationObjective("comfort", minimize=True),
    OptimizationObjective("grip", minimize=True),
]


def _pt(x, y, feasible=True):
    return ParetoPoint(params={}, objectives={"comfort": x, "grip": y}, constraints={}, feasible=feasible)


def test_multi_level_fronts_not_binary():
    """Deb fast non-dominated sort: a chain of 3 nested points yields ranks 0,1,2."""
    f = ParetoFrontier(OBJS)
    f.add_points([_pt(1.0, 1.0), _pt(2.0, 2.0), _pt(3.0, 3.0)])
    ranks = sorted(p.pareto_rank for p in f._points)
    assert ranks == [0, 1, 2], f"expected true multi-level fronts, got {ranks}"


def test_non_dominated_front_correct():
    f = ParetoFrontier(OBJS)
    # Classic trade-off front plus one dominated point
    f.add_points([_pt(1.0, 3.0), _pt(2.0, 2.0), _pt(3.0, 1.0), _pt(2.5, 2.5)])
    frontier = f.get_frontier()
    assert len(frontier) == 3
    assert all(p.pareto_rank == 0 for p in frontier)


def test_crowding_distance_boundary_points_infinite():
    f = ParetoFrontier(OBJS)
    f.add_points([_pt(1.0, 3.0), _pt(2.0, 2.0), _pt(3.0, 1.0)])
    front = f.get_frontier()
    dists = sorted(p.crowding_distance for p in front)
    assert dists[0] > 0  # middle point finite
    assert dists[1] == float("inf")
    assert dists[2] == float("inf")


def test_normalized_tolerance_not_scale_blind():
    """Two points differing by 1e-6 on a 0-1 objective must NOT tie as 'equal'
    when the other objective decides dominance — relative tolerance scales
    with the observed objective range, not an absolute 1e-10."""
    f = ParetoFrontier(OBJS)
    a = _pt(0.5, 0.5)
    b = _pt(0.5 + 1e-6, 0.5 - 1e-6)  # trades tiny comfort for tiny grip: neither dominates
    c = _pt(0.9, 0.9)                # dominated by both
    f.add_points([a, b, c])
    assert a.pareto_rank == 0 and b.pareto_rank == 0
    assert c.pareto_rank == 1


def test_corner_solution_warning():
    f = ParetoFrontier(OBJS, param_bounds={"k_s": (10000.0, 80000.0)})
    f.add_points([
        ParetoPoint(params={"k_s": 10000.0}, objectives={"comfort": 1.0, "grip": 2.0}, constraints={}, feasible=True),
        ParetoPoint(params={"k_s": 40000.0}, objectives={"comfort": 2.0, "grip": 1.0}, constraints={}, feasible=True),
    ])
    warns = f.corner_warnings()
    assert any("k_s=LOWER" in w for w in warns), f"expected corner warning, got {warns}"
    d = f.to_dict()
    assert "corner_warnings" in d
