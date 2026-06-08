"""Compact masked action space for RL.

The model chooses the operation. A deterministic legal placer chooses the
nearest valid site for that operation. This keeps the policy learned while
removing the unproductive 11k-way spatial exploration burden.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from world import placement
from world.catalog import TILE_CATALOG
from world.grid import has_road_adjacency, road_connected_set
from world.sim import World
from world.subsurface import Q_MAX_WELL_BBL_DAY, drill_capex, survey_cost

WORLD_W = 32
WORLD_H = 32

ACTIONS: tuple[str, ...] = (
    "noop",
    "build_road",
    "build_house",
    "build_commercial",
    "build_industrial",
    "build_park",
    "build_solar_farm",
    "build_wind_turbine",
    "build_battery",
    "build_coal_plant",
    "survey_next",
    "drill_best_oil",
    "demolish_coal_plant",
    "demolish_lowest_commercial",
)

ACTION_DIM = len(ACTIONS)

BUILD_ACTIONS: dict[str, str] = {
    "build_road": "road",
    "build_house": "house",
    "build_commercial": "commercial",
    "build_industrial": "industrial",
    "build_park": "park",
    "build_solar_farm": "solar_farm",
    "build_wind_turbine": "wind_turbine",
    "build_battery": "battery",
    "build_coal_plant": "coal_plant",
}


def describe_action(action: int) -> str:
    if 0 <= int(action) < ACTION_DIM:
        return ACTIONS[int(action)]
    return f"invalid:{action}"


def apply_action(world: World, action: int) -> dict[str, Any]:
    name = describe_action(action)
    if name == "noop":
        return {"ok": True, "treasury_after": world.state.treasury, "result": None}
    if name in BUILD_ACTIONS:
        tile_type = BUILD_ACTIONS[name]
        site = _best_build_site(world, tile_type)
        if site is None:
            return {"ok": False, "error": "no_legal_site", "treasury_after": world.state.treasury}
        return world.build(tile_type, site[0], site[1])
    if name == "survey_next":
        site = _best_survey_site(world)
        if site is None:
            return {"ok": False, "error": "no_survey_site", "treasury_after": world.state.treasury}
        return world.survey(site[0], site[1], 4)
    if name == "drill_best_oil":
        target = _best_oil_target(world)
        if target is None:
            return {"ok": False, "error": "no_oil_target", "treasury_after": world.state.treasury}
        result = world.drill(target[0], target[1], target[2], "production")
        if result.get("ok") and isinstance(result.get("result"), dict):
            well_id = str(result["result"]["id"])
            world.control_well(well_id, min(160.0, Q_MAX_WELL_BBL_DAY))
        return result
    if name == "demolish_lowest_commercial":
        tile = _lowest_value_commercial(world)
        if tile is None:
            return {"ok": False, "error": "no_demolishable", "treasury_after": world.state.treasury}
        return world.demolish(int(tile["x"]), int(tile["y"]))
    if name == "demolish_coal_plant":
        tile = _coal_plant_to_retire(world)
        if tile is None:
            return {"ok": False, "error": "no_demolishable", "treasury_after": world.state.treasury}
        return world.demolish(int(tile["x"]), int(tile["y"]))
    return {"ok": False, "error": "invalid_action", "treasury_after": world.state.treasury}


def legal_action_mask(world: World, *, min_cash_after: float = 0.0) -> np.ndarray:
    mask = np.zeros(ACTION_DIM, dtype=np.bool_)
    mask[0] = True
    for idx, action_name in enumerate(ACTIONS):
        if action_name in BUILD_ACTIONS:
            tile_type = BUILD_ACTIONS[action_name]
            spec = TILE_CATALOG[tile_type]
            if world.state.treasury >= spec.capex + min_cash_after and _growth_gate(
                world, tile_type
            ):
                mask[idx] = _best_build_site(world, tile_type) is not None
        elif action_name == "demolish_lowest_commercial":
            mask[idx] = _lowest_value_commercial(world) is not None
        elif action_name == "demolish_coal_plant":
            mask[idx] = _coal_plant_to_retire(world) is not None
        elif action_name == "survey_next":
            mask[idx] = (
                world.state.treasury >= survey_cost(4) + min_cash_after
                and _best_survey_site(world) is not None
            )
        elif action_name == "drill_best_oil":
            target = _best_oil_target(world)
            if target is not None:
                capex = drill_capex(TILE_CATALOG["oil_well"].capex, target[2], world.config.world_d)
                mask[idx] = world.state.treasury >= capex + min_cash_after
    return mask


def _growth_gate(world: World, tile_type: str) -> bool:
    state = world.state
    pop = float(state.population)
    housing = float(sum(tile.housing_capacity for tile in state.tiles))
    jobs = float(sum(tile.jobs for tile in state.tiles))
    counts: dict[str, int] = {}
    for tile in state.tiles:
        counts[tile.type] = counts.get(tile.type, 0) + 1
    if tile_type == "house":
        return housing <= pop + 80.0
    if tile_type == "commercial":
        return jobs <= pop + 80.0
    if tile_type == "industrial":
        return jobs <= pop + 120.0 and counts.get("industrial", 0) < 8
    if tile_type == "park":
        houses = counts.get("house", 0)
        parks = counts.get("park", 0)
        return parks < max(3, 1 + houses // 2)
    if tile_type == "battery":
        renewables = counts.get("solar_farm", 0) + counts.get("wind_turbine", 0)
        return counts.get("battery", 0) < min(8, max(1, renewables // 2 + 1))
    if tile_type == "solar_farm":
        return counts.get("solar_farm", 0) < 24
    if tile_type == "wind_turbine":
        return counts.get("wind_turbine", 0) < 16
    if tile_type == "coal_plant":
        return counts.get("coal_plant", 0) < 2
    if tile_type == "road":
        return counts.get("road", 0) < 160
    return True


def _best_build_site(world: World, tile_type: str) -> tuple[int, int] | None:
    occupied = {(tile.x, tile.y): tile for tile in world.state.tiles}
    candidates: list[tuple[float, int, int]] = []
    for x, y in _candidate_cells(world, tile_type):
        if (x, y) in occupied:
            continue
        spec = TILE_CATALOG[tile_type]
        if spec.requires_road and not has_road_adjacency(
            x, y, world.state.tiles, world.config.world_w, world.config.world_h
        ):
            continue
        if placement.validate(tile_type, (x, y), world.state.tiles) is not None:
            continue
        candidates.append((_site_score(world, tile_type, x, y), x, y))
    if not candidates:
        return None
    _score, x, y = max(candidates, key=lambda item: (item[0], -item[2], -item[1]))
    return x, y


def _site_score(world: World, tile_type: str, x: int, y: int) -> float:
    center = (WORLD_W // 2, WORLD_H // 2)
    distance_penalty = 0.01 * (abs(x - center[0]) + abs(y - center[1]))
    tiles = world.state.tiles
    if tile_type == "park":
        covered_housing = sum(
            tile.housing_capacity
            for tile in tiles
            if tile.type in {"town_hall", "house"} and max(abs(tile.x - x), abs(tile.y - y)) <= 2
        )
        return 10.0 * covered_housing - distance_penalty
    if tile_type == "commercial":
        nearby_housing = sum(
            tile.housing_capacity
            for tile in tiles
            if tile.housing_capacity > 0 and max(abs(tile.x - x), abs(tile.y - y)) <= 2
        )
        return 8.0 * nearby_housing - distance_penalty
    if tile_type == "house":
        nearby_parks = sum(
            1 for tile in tiles if tile.type == "park" and max(abs(tile.x - x), abs(tile.y - y)) <= 2
        )
        nearby_commercial = sum(
            1
            for tile in tiles
            if tile.type == "commercial" and max(abs(tile.x - x), abs(tile.y - y)) <= 2
        )
        return 12.0 * nearby_parks + 3.0 * nearby_commercial - distance_penalty
    return -distance_penalty


def _candidate_cells(world: World, tile_type: str) -> list[tuple[int, int]]:
    center = (WORLD_W // 2, WORLD_H // 2)
    occupied = {(tile.x, tile.y): tile for tile in world.state.tiles}
    if tile_type == "road":
        cells = _road_frontier(world)
    elif tile_type == "park":
        cells = _near_residences(world, radius=2)
    elif tile_type in {"solar_farm", "wind_turbine", "battery"}:
        cells = [(x, y) for y in range(WORLD_H) for x in range(WORLD_W) if (x, y) not in occupied]
    else:
        cells = [(x, y) for y in range(WORLD_H) for x in range(WORLD_W) if (x, y) not in occupied]
    cells.sort(key=lambda xy: (abs(xy[0] - center[0]) + abs(xy[1] - center[1]), xy[1], xy[0]))
    return cells


def _road_frontier(world: World) -> list[tuple[int, int]]:
    connected = road_connected_set(world.state.tiles, world.config.world_w, world.config.world_h)
    anchors = set(connected) or {(tile.x, tile.y) for tile in world.state.tiles}
    occupied = {(tile.x, tile.y) for tile in world.state.tiles}
    cells: set[tuple[int, int]] = set()
    for x, y in anchors:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < WORLD_W and 0 <= ny < WORLD_H and (nx, ny) not in occupied:
                cells.add((nx, ny))
    return list(cells)


def _near_residences(world: World, *, radius: int) -> list[tuple[int, int]]:
    occupied = {(tile.x, tile.y) for tile in world.state.tiles}
    residences = [tile for tile in world.state.tiles if tile.type in {"town_hall", "house"}]
    cells: set[tuple[int, int]] = set()
    for tile in residences:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = tile.x + dx, tile.y + dy
                if 0 <= x < WORLD_W and 0 <= y < WORLD_H and (x, y) not in occupied:
                    cells.add((x, y))
    return list(cells)


def _lowest_value_commercial(world: World) -> dict[str, Any] | None:
    state = world.state_dict()
    candidates = [
        tile
        for tile in state["tiles"]
        if tile["type"] == "commercial" and int(tile.get("staffed_jobs", 0)) > 0
    ]
    if len(candidates) <= 2:
        return None
    candidates.sort(
        key=lambda tile: (
            float(tile.get("estimated_net_per_day", 0.0)),
            float(tile.get("residents_in_radius", 0.0)),
        )
    )
    return candidates[0]


def _coal_plant_to_retire(world: World) -> dict[str, Any] | None:
    candidates = [tile for tile in world.state_dict()["tiles"] if tile["type"] == "coal_plant"]
    if not candidates:
        return None
    candidates.sort(key=lambda tile: (float(tile.get("kwh_served_yesterday", 0.0)), tile["id"]))
    return candidates[0]


def _best_survey_site(world: World) -> tuple[int, int] | None:
    explored = set(world.subsurface.explored_columns)
    for x, y in _survey_anchors():
        if (x, y) not in explored:
            return x, y
    return None


def _survey_anchors() -> list[tuple[int, int]]:
    anchors = [(x, y) for y in range(0, WORLD_H, 4) for x in range(0, WORLD_W, 4)]
    center = (WORLD_W // 2, WORLD_H // 2)
    anchors.sort(key=lambda xy: (abs(xy[0] - center[0]) + abs(xy[1] - center[1]), xy[1], xy[0]))
    return anchors


def _best_oil_target(world: World) -> tuple[int, int, int] | None:
    occupied = {(tile.x, tile.y) for tile in world.state.tiles}
    occupied |= {(well.x, well.y) for well in world.state.wells}
    revealed = world.state_dict().get("reservoirs_revealed", {}).get("top_k", [])
    best: tuple[float, int, int, int] | None = None
    for voxel in revealed:
        x = int(voxel.get("x", 0))
        y = int(voxel.get("y", 0))
        z = int(voxel.get("z", 0))
        if (x, y) in occupied:
            continue
        oil = float(voxel.get("oil_estimate_bbl", 0.0) or 0.0)
        perm = float(voxel.get("perm_estimate_md", 0.0) or 0.0)
        if oil < 2_500.0:
            continue
        score = oil * (max(perm, 1.0) ** 0.3)
        if best is None or score > best[0]:
            best = (score, x, y, z)
    if best is None:
        return None
    return best[1], best[2], best[3]
