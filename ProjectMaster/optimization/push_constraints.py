"""Fixture-aware, grid-exact slicing MILP used ONLY by the push optimizer.

Cut coordinates are shared by all descendant rooms. Each cut selects a grid
line. Continuous cell variables are exact ANDs of binary column/row membership
expressions; cell intersection areas are precomputed against the fixed polygon.
Thus no width*height nonlinear approximation is passed to HiGHS.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
import json
from math import ceil, isfinite
from pathlib import Path
import time
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import linemerge, unary_union

from .ampl_room_optimizer import polygon_only


@dataclass
class Expr:
    terms: dict[int, float] = field(default_factory=dict)
    constant: float = 0.0

    def __add__(self, other):
        other = expr(other)
        terms = self.terms.copy()
        for key, value in other.terms.items():
            terms[key] = terms.get(key, 0.0) + value
        return Expr({k: v for k, v in terms.items() if abs(v) > 1e-12}, self.constant + other.constant)

    __radd__ = __add__

    def __mul__(self, value):
        return Expr({k: v * value for k, v in self.terms.items()}, self.constant * value)

    __rmul__ = __mul__

    def __truediv__(self, value):
        return self * (1.0 / value)

    def __sub__(self, other):
        return self + expr(other) * -1

    def __rsub__(self, other):
        return expr(other) - self

    def value(self, solution):
        return self.constant + sum(value * solution[key] for key, value in self.terms.items())


def expr(value):
    return value if isinstance(value, Expr) else Expr(constant=float(value))


class LinearModel:
    def __init__(self):
        self.names = []
        self.lb = []
        self.ub = []
        self.integer = []
        self.rows = []
        self.row_lb = []
        self.row_ub = []
        self.labels = []

    def var(self, name, lower=0.0, upper=1.0, integer=False):
        index = len(self.names)
        self.names.append(name)
        self.lb.append(float(lower))
        self.ub.append(float(upper))
        self.integer.append(int(integer))
        return Expr({index: 1.0})

    def constraint(self, value, lower=-np.inf, upper=np.inf, label=""):
        value = expr(value)
        if not value.terms:
            if not lower - 1e-7 <= value.constant <= upper + 1e-7:
                raise ValueError(f"Inconsistent constraints: {label} ({value.constant:g} not in [{lower:g}, {upper:g}]).")
            return
        self.rows.append(value.terms)
        self.row_lb.append(float(lower - value.constant))
        self.row_ub.append(float(upper - value.constant))
        self.labels.append(label)

    def absolute(self, value, name):
        variable = self.var(name, upper=np.inf)
        self.constraint(variable - value, lower=0)
        self.constraint(variable + value, lower=0)
        return variable

    def solve(self, objective, backend, seconds, mip_gap):
        cost = np.zeros(len(self.names))
        for key, value in objective.terms.items():
            cost[key] = value
        try_ampl = backend == "ampl" or (backend == "auto" and max(len(self.names),len(self.rows)) <= 1800)
        if try_ampl:
            try:
                solution,details = self._solve_ampl(cost, seconds, mip_gap)
                details["objectiveValue"] += objective.constant
                return solution,details
            except Exception as error:
                if backend == "ampl":
                    raise RuntimeError("AMPL/HiGHS could not run this model. Check your AMPL license/modules, or use --push-backend scipy. " + str(error)) from error
                fallback = f"AMPL unavailable: {type(error).__name__}: {str(error)[:200]}"
        else:
            fallback = ("Model exceeds conservative AMPL demo-size threshold; use backend=ampl with a suitable license."
                        if backend == "auto" else None)
        ri, ci, values = [], [], []
        for row, coefficients in enumerate(self.rows):
            for col, value in coefficients.items():
                ri.append(row)
                ci.append(col)
                values.append(value)
        matrix = coo_matrix((values, (ri, ci)), shape=(len(self.rows), len(self.names))).tocsc()
        result = milp(cost, integrality=np.array(self.integer), bounds=Bounds(self.lb, self.ub),
                      constraints=LinearConstraint(matrix, self.row_lb, self.row_ub),
                      options={"time_limit": max(0.01, seconds), "mip_rel_gap": mip_gap})
        if result.x is None:
            raise RuntimeError("No feasible push layout found. " + result.message +
                               " Check the constraints overlay, image scale, fixture widths/margins, room minima, or try a finer --push-step.")
        gap = getattr(result,"mip_gap",None)
        gap = float(gap) if gap is not None else None
        details = {"backend": "scipy-highs", "status": ("optimal" if gap is None or gap < 1e-8 else "optimal-within-gap") if result.status == 0 else "feasible-limit",
                   "message": result.message, "mipRelativeGap": gap,
                   "objectiveValue": float(result.fun + objective.constant), "fallbackReason": fallback}
        return np.asarray(result.x), details

    def verify_solution(self, solution, tolerance=2e-5):
        if not np.isfinite(solution).all():
            raise RuntimeError("Solver returned non-finite values")
        for i,value in enumerate(solution):
            if value < self.lb[i]-tolerance or value > self.ub[i]+tolerance:
                raise RuntimeError(f"Solver bound violation for {self.names[i]}")
            if self.integer[i] and abs(value-round(value))>tolerance:
                raise RuntimeError(f"Solver did not return an integral cut/size for {self.names[i]}")
        for coefficients,lower,upper,label in zip(self.rows,self.row_lb,self.row_ub,self.labels):
            value = sum(coefficient*solution[index] for index,coefficient in coefficients.items())
            if value < lower-tolerance or value > upper+tolerance:
                raise RuntimeError(f"Solver constraint violation: {label}")

    def _solve_ampl(self, cost, seconds, mip_gap):
        from amplpy import AMPL, modules
        try:
            ampl = AMPL(modules.load())
        except Exception:
            ampl = AMPL()
        try:
            ampl.eval("""
                set V; set C; set NZ within C cross V; set I within V;
                param lo {V}; param hi {V}; param a {NZ}; param rhslo {C}; param rhshi {C}; param cost {V};
                var x {v in V} >= lo[v], <= hi[v];
                var bit {I} binary;
                subject to Integrality {v in I}: x[v] = bit[v];
                subject to Rows {c in C}: rhslo[c] <= sum {(r,v) in NZ: r=c} a[r,v]*x[v] <= rhshi[c];
                minimize Objective: sum {v in V} cost[v]*x[v];
            """)
            ampl.set["V"] = range(len(self.names))
            ampl.set["C"] = range(len(self.rows))
            ampl.set["I"] = [i for i, flag in enumerate(self.integer) if flag]
            coefficients = {(row, col): value for row, items in enumerate(self.rows) for col, value in items.items()}
            ampl.set["NZ"] = list(coefficients)
            for key, values in [("lo", self.lb), ("hi", self.ub), ("rhslo", self.row_lb), ("rhshi", self.row_ub), ("cost", cost)]:
                ampl.param[key] = dict(enumerate(values))
            ampl.param["a"] = coefficients
            ampl.option["solver"] = "highs"
            ampl.option["highs_options"] = f"time_limit={max(0.01, seconds)} mip_rel_gap={mip_gap}"
            ampl.solve()
            code = int(ampl.get_value("solve_result_num"))
            status = str(ampl.get_value("solve_result"))
            if code >= 200:
                raise RuntimeError(f"AMPL did not prove a feasible solution: {status} ({code}).")
            solution = np.array([float(ampl.get_value(f"x[{i}]")) for i in range(len(self.names))])
            return solution, {"backend": "ampl-highs", "status": "optimal" if code < 100 else "feasible-limit",
                              "message": status, "mipRelativeGap": None, "objectiveValue": float(cost @ solution)}
        finally:
            ampl.close()


@dataclass
class Fixture:
    key: str
    kind: str
    room_ids: tuple[int, ...]
    axis: str  # coordinate along the wall: x for horizontal, y for vertical
    normal: float
    start: float
    width: float
    side: str | None
    other_side: str | None
    host_min: float
    host_max: float
    margin: float
    widths: list[tuple[str, float, dict]]
    inward: int = 0
    measurement: str = "detected-bbox-projection"
    original_center_fraction: float = 0.5
    host_profile: list[tuple[float,float]] = field(default_factory=list)
    host_normal_min: float | None = None
    host_normal_max: float | None = None

    def to_dict(self):
        return {"id": self.key, "kind": self.kind, "roomIds": list(self.room_ids),
                "axis": self.axis, "wallCoordinate": self.normal,
                "originalStartPixels": self.start, "originalWidthPixels": self.width,
                "marginEachEndPixels": self.margin, "measurement": self.measurement,
                "originalCenterFraction": self.original_center_fraction,
                "hostNormalRangePixels": [self.normal if self.host_normal_min is None else self.host_normal_min,
                                          self.normal if self.host_normal_max is None else self.host_normal_max],
                "hostBoundaryProfile": [{"x":float(x),"y":float(y)} for x,y in self.host_profile],
                "hostIntervalPixels": [self.host_min, self.host_max],
                "allowedSizes": [{"id": key, "requiredWidthPixels": width, **meta} for key, width, meta in self.widths]}


def positive(value, name, allow_zero=False):
    number = float(value)
    if not isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"{name} must be {'non-negative' if allow_zero else 'positive'} and finite")
    return number


def boundary_segments(boundary):
    segments = []
    coords = list(boundary.exterior.coords)
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        if abs(y2 - y1) <= 1e-5 and abs(x2 - x1) > 1:
            segments.append(("x", y1, min(x1, x2), max(x1, x2)))
        elif abs(x2 - x1) <= 1e-5 and abs(y2 - y1) > 1:
            segments.append(("y", x1, min(y1, y2), max(y1, y2)))
    # Merge exactly collinear contiguous segments, including redundant vertices.
    merged = []
    for axis in ("x", "y"):
        for item in sorted([s for s in segments if s[0] == axis], key=lambda s: (s[1], s[2])):
            if merged and merged[-1][0] == axis and abs(merged[-1][1] - item[1]) < 1e-5 and item[2] <= merged[-1][3] + 1e-5:
                previous = merged.pop()
                merged.append((axis, item[1], previous[2], max(previous[3], item[3])))
            else:
                merged.append(item)
    return merged


def line_components(geometry):
    pieces=[]
    def collect(item):
        if item.geom_type=="LineString" and item.length>1e-7:
            pieces.append(item)
        elif hasattr(item,"geoms"):
            for part in item.geoms:
                collect(part)
    collect(geometry)
    if len(pieces)>1:
        united=unary_union(pieces)
        merged=united if united.geom_type=="LineString" else linemerge(united)
        pieces.clear()
        collect(merged)
    return pieces


def facade_chains(boundary,jog_tolerance):
    """Join continuous small raster/frame jogs, never separate distant faces.

    The footprint stays unchanged. Every logical host retains its exact
    boundary profile, so ownership and final validation use the real contour.
    A common axis/normal alone is insufficient: a connected boundary path
    spanning the complete proposed interval must exist inside the jog band.
    """
    groups=[]
    for axis,normal,lo,hi in boundary_segments(boundary):
        middle=(lo+hi)/2
        point=Point(middle,normal+.01) if axis=="x" else Point(normal+.01,middle)
        inward=1 if boundary.covers(point) else -1
        groups.append({"axis":axis,"inward":inward,"segments":[(normal,lo,hi)]})
    def profile(group):
        segments=group["segments"]
        low_n=min(item[0] for item in segments)
        high_n=max(item[0] for item in segments)
        lo=min(item[1] for item in segments)
        hi=max(item[2] for item in segments)
        strip=box(lo,low_n-1e-6,hi,high_n+1e-6) if group["axis"]=="x" else box(low_n-1e-6,lo,high_n+1e-6,hi)
        along=0 if group["axis"]=="x" else 1
        for piece in line_components(boundary.boundary.intersection(strip)):
            if piece.bounds[along]<=lo+1e-5 and piece.bounds[along+2]>=hi-1e-5:
                return piece
        return None
    changed=True
    while changed:
        changed=False
        for i,a in enumerate(groups):
            for j in range(i+1,len(groups)):
                b=groups[j]
                if a["axis"]!=b["axis"] or a["inward"]!=b["inward"]:
                    continue
                combined=a["segments"]+b["segments"]
                if max(item[0] for item in combined)-min(item[0] for item in combined)>jog_tolerance+1e-7:
                    continue
                a_lo,a_hi=min(item[1] for item in a["segments"]),max(item[2] for item in a["segments"])
                b_lo,b_hi=min(item[1] for item in b["segments"]),max(item[2] for item in b["segments"])
                if max(a_lo,b_lo)-min(a_hi,b_hi)>jog_tolerance+1e-7:
                    continue
                candidate={"axis":a["axis"],"inward":a["inward"],"segments":combined}
                if profile(candidate) is None:
                    continue
                groups[i]=candidate
                groups.pop(j)
                changed=True
                break
            if changed:
                break
    result=[]
    for group in groups:
        segments=group["segments"]
        lengths=defaultdict(float)
        for normal,lo,hi in segments:
            lengths[normal]+=hi-lo
        normal=max(lengths,key=lengths.get)
        path=profile(group)
        if path is None:
            continue
        result.append({**group,"normal":normal,"lo":min(item[1] for item in segments),
                       "hi":max(item[2] for item in segments),
                       "normalMin":min(item[0] for item in segments),
                       "normalMax":max(item[0] for item in segments),"profile":path})
    return result


def fixture_path(fixture,start,width,normal,margin=0.0):
    lo,hi=start-margin,start+width+margin
    if not fixture.host_profile:
        return LineString([(lo,normal),(hi,normal)] if fixture.axis=="x" else [(normal,lo),(normal,hi)])
    source=LineString(fixture.host_profile)
    b=source.bounds
    clip=box(lo,b[1]-1,hi,b[3]+1) if fixture.axis=="x" else box(b[0]-1,lo,b[2]+1,hi)
    along=0 if fixture.axis=="x" else 1
    for piece in line_components(source.intersection(clip)):
        if piece.bounds[along]<=lo+1e-5 and piece.bounds[along+2]>=hi-1e-5:
            coords=list(piece.coords)
            if coords[0][along]>coords[-1][along]:
                coords.reverse()
            return LineString(coords)
    raise ValueError(f"{fixture.key}: fixture interval crosses a real break in its facade profile")


def fixture_polygon(item):
    points = item.get("polygon") or []
    if len(points) >= 3:
        polygon = Polygon([(float(p["x"]), float(p["y"])) for p in points])
    elif item.get("bbox"):
        b = item["bbox"]
        polygon = box(b["x1"], b["y1"], b["x2"], b["y2"])
    else:
        raise ValueError("A fixture is missing its polygon/bbox")
    if polygon.is_empty or not polygon.is_valid or polygon.area <= 0:
        raise ValueError("A fixture has invalid polygon/bbox geometry")
    return polygon


def reference_boxes(tree, boundary):
    result = {}
    def visit(node, bounds):
        if node.is_leaf:
            result[node.room_ids[0]] = bounds
            return
        x0, y0, x1, y1 = bounds
        cut = float(node.original_cut)
        if node.axis == "x":
            visit(node.first, (x0, y0, cut, y1))
            visit(node.second, (cut, y0, x1, y1))
        else:
            visit(node.first, (x0, y0, x1, cut))
            visit(node.second, (x0, cut, x1, y1))
    visit(tree, boundary.bounds)
    return result


def collect_fixtures(data, rooms, boundary, tree, options, pixels_per_metre):
    tolerance = positive(options.mapping_tolerance_pixels, "mapping_tolerance_pixels")
    margin = positive(options.fixture_margin_pixels, "fixture_margin_pixels", True)
    refs = reference_boxes(tree,boundary) if tree is not None else {room_id:record["polygon"].bounds for room_id,record in rooms.items()}
    assessment=(data.get("buildingBoundary") or {}).get("automaticAssessment") or {}
    try:
        thickness=float(assessment.get("estimatedWallThicknessPixels",8.0))
    except (TypeError,ValueError):
        thickness=8.0
    if not isfinite(thickness) or thickness<=0:
        thickness=8.0
    jog_tolerance=min(tolerance,max(1.0,thickness*.5))
    exterior = facade_chains(boundary,jog_tolerance)
    catalogue = json.loads(Path(options.window_catalog_path).read_text())
    records = catalogue.get("windows", [])
    catalogue_allowance = positive(catalogue.get("installationAllowanceTotalMm", 30), "installation allowance", True)
    if not records:
        raise ValueError("Window catalogue has no windows")
    for record in records:
        positive(record["frameWidthMm"], "catalogue frame width")
        positive(record["frameHeightMm"], "catalogue frame height")
    keys = [str(record["id"]) for record in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Window catalogue size IDs must be unique")
    overrides = options.fixture_overrides or {}
    fixtures = []
    seen = set()
    for collection, kind in [("doors", "door"), ("openings", "opening"), ("windows", "window")]:
        for index, item in enumerate(data.get(collection) or [], 1):
            key = f"{kind}:{item.get('id', index)}"
            if key in seen:
                raise ValueError(f"Duplicate fixture id {key}")
            seen.add(key)
            override = overrides.get(key, {})
            polygon = fixture_polygon(item)
            b = polygon.bounds
            room_ids = []
            for field_name in ("room1", "room2"):
                value = item.get(field_name)
                if value is not None:
                    room_ids.append(int(value["id"] if isinstance(value, dict) else value))
            if "roomIds" in override:
                room_ids = [int(value) for value in override["roomIds"]]
            if any(room_id not in rooms for room_id in room_ids) or len(set(room_ids)) != len(room_ids):
                raise ValueError(f"{key}: invalid/missing room references {room_ids}")
            if kind == "opening" and len(room_ids) != 2:
                raise ValueError(f"{key}: an opening must connect two rooms")
            if kind == "door" and len(room_ids) not in {1, 2}:
                raise ValueError(f"{key}: a door must connect one exterior room or two interior rooms")
            candidates = []
            if len(room_ids) == 2:
                first, second = (refs[value] for value in room_ids)
                for axis, side_a, side_b, pa, pb, lo, hi in [
                    ("x", "y1", "y0", first[3], second[1], max(first[0], second[0]), min(first[2], second[2])),
                    ("x", "y0", "y1", first[1], second[3], max(first[0], second[0]), min(first[2], second[2])),
                    ("y", "x1", "x0", first[2], second[0], max(first[1], second[1]), min(first[3], second[3])),
                    ("y", "x0", "x1", first[0], second[2], max(first[1], second[1]), min(first[3], second[3])),
                ]:
                    if abs(pa - pb) > tolerance or hi <= lo:
                        continue
                    normal = (pa + pb) / 2
                    line = LineString([(lo, normal), (hi, normal)] if axis == "x" else [(normal, lo), (normal, hi)])
                    distance = line.distance(polygon)
                    if distance <= tolerance:
                        score = distance + abs((polygon.centroid.y if axis == "x" else polygon.centroid.x) - normal) * .01
                        candidates.append((score, axis, normal, lo, hi, side_a, side_b, 0, tuple(room_ids),None))
            else:
                possible_ids = room_ids or sorted(rooms)
                for facade in exterior:
                    axis,normal,lo,hi=(facade[key] for key in ("axis","normal","lo","hi"))
                    line = facade["profile"]
                    if line.distance(polygon) > tolerance:
                        continue
                    inward = facade["inward"]
                    for room_id in possible_ids:
                        room_poly = rooms[room_id]["polygon"]
                        gap = room_poly.distance(polygon)
                        if gap > tolerance:
                            continue
                        idx = 0 if axis == "x" else 1
                        r = refs[room_id]
                        overlap = min(b[idx+2], hi, r[idx+2]) - max(b[idx], lo, r[idx])
                        if overlap <= 0:
                            continue
                        normal_center = polygon.centroid.y if axis == "x" else polygon.centroid.x
                        score = gap + line.distance(polygon) + abs(normal_center-normal)*.01
                        candidates.append((score, axis, normal, lo, hi, None, None, inward, (room_id,),facade))
            if not candidates:
                raise ValueError(f"{key}: cannot attach fixture to the same room pair/exterior wall within {tolerance:g}px. Check detections or fixture overrides; it will not be discarded.")
            selected = min(candidates, key=lambda value: value[0])
            _, axis, normal, lo, hi, side_a, side_b, inward, room_ids,facade = selected
            idx = 0 if axis == "x" else 1
            start = float(b[idx])
            width = float(b[idx+2] - b[idx])
            if "widthPixels" in override:
                width = positive(override["widthPixels"], f"{key} widthPixels")
                start = (b[idx] + b[idx+2] - width) / 2
            fixture_margin = positive(override.get("marginPixels", margin), f"{key} marginPixels", True)
            widths = [("original", width, {})]
            if kind == "window" and options.window_policy == "catalog":
                ppm = positive(pixels_per_metre or 0, "pixels_per_metre (required for catalogue windows; use --window-policy preserve without scale)")
                choices = []
                for record in records:
                    required = (float(record["frameWidthMm"]) + catalogue_allowance) * ppm / 1000
                    choices.append((str(record["id"]), required, {**record, "installationAllowanceTotalMm": catalogue_allowance}))
                if "preferredSize" in override:
                    preferred = next((choice for choice in choices if choice[0] == override["preferredSize"]), None)
                    if preferred is None:
                        raise ValueError(f"{key}: unknown preferredSize")
                else:
                    preferred = min(choices, key=lambda value: abs(value[1] - width))
                widths = sorted([choice for choice in choices if choice[1] <= preferred[1]+1e-6], key=lambda value: value[1])
            fixtures.append(Fixture(key, kind, tuple(room_ids), axis, normal, start, width, side_a, side_b,
                                    lo, hi, fixture_margin, widths, inward,
                                    "user-width-override" if "widthPixels" in override else "detected-bbox-projection"))
            if facade is not None:
                fixtures[-1].host_profile=list(facade["profile"].coords)
                fixtures[-1].host_normal_min=facade["normalMin"]
                fixtures[-1].host_normal_max=facade["normalMax"]
            original_lo = max([lo]+[refs[room_id][idx] for room_id in room_ids])
            original_hi = min([hi]+[refs[room_id][idx+2] for room_id in room_ids])
            fraction = (start+width/2-original_lo)/max(original_hi-original_lo,1e-9)
            fixtures[-1].original_center_fraction = max(0,min(1,fraction))
    unknown = set(overrides) - seen
    if unknown:
        raise ValueError(f"Unknown fixture overrides: {sorted(unknown)}")
    return fixtures


def graph_report(fixtures, tree):
    cuts = []
    def visit(node, key):
        if node.is_leaf:
            return
        cuts.append({"id": key, "axis": node.axis, "coordinatePixels": node.original_cut, "roomIds": list(node.room_ids)})
        visit(node.first, key+"L")
        visit(node.second, key+"R")
    visit(tree, "root")
    return {"fixtures": [item.to_dict() for item in fixtures], "sharedCuts": cuts,
            "rules": {"preserveDoorWidth": True, "preserveOpeningWidth": True,
                      "preserveFixtureRoomConnections": True, "sharedWallCoordinates": True,
                      "fixturePositionsMaySlide": True, "doorSwingClearanceModeled": False},
            "measurementNotice": "Projected detector boxes are estimates. Review the overlay or supply measured widthPixels overrides."}


def make_grid(low, high, step, originals):
    count = max(1, int(ceil((high-low)/step)))
    values = list(np.linspace(low, high, count+1))
    values.extend(value for value in originals if low+1e-5 < value < high-1e-5)
    unique = []
    for value in sorted(values):
        if not unique or value - unique[-1] > 1e-4:
            unique.append(float(value))
    return unique


def actual_fixture_intervals(fixture,polygons,boundary,normal,tolerance):
    """Available straight pieces of this fixture's actual host wall."""
    along = 0 if fixture.axis=="x" else 1
    lo,hi = boundary.bounds[along],boundary.bounds[along+2]
    lo = max([lo]+[polygons[r].bounds[along] for r in fixture.room_ids])
    hi = min([hi]+[polygons[r].bounds[along+2] for r in fixture.room_ids])
    if len(fixture.room_ids)==1 or fixture.host_profile:
        lo,hi = max(lo,fixture.host_min),min(hi,fixture.host_max)
    if hi<=lo:
        return []
    if fixture.host_profile:
        common=fixture_path(fixture,lo,hi-lo,normal)
    else:
        points = [(lo,normal),(hi,normal)] if fixture.axis=="x" else [(normal,lo),(normal,hi)]
        common = LineString(points)
    for room_id in fixture.room_ids:
        common = common.intersection(polygons[room_id].boundary.buffer(tolerance,cap_style=2,join_style=2))
    if len(fixture.room_ids)==1:
        common = common.intersection(boundary.boundary.buffer(tolerance,cap_style=2,join_style=2))
    intervals = []
    def collect(geometry):
        if geometry.geom_type=="LineString" and geometry.length>1e-6:
            intervals.append((max(lo,geometry.bounds[along]),min(hi,geometry.bounds[along+2])))
        elif hasattr(geometry,"geoms"):
            for part in geometry.geoms:
                collect(part)
    collect(common)
    merged = []
    for left,right in sorted(intervals):
        if merged and left<=merged[-1][1]+1e-7:
            merged[-1]=(merged[-1][0],max(merged[-1][1],right))
        else:
            merged.append((left,right))
    return merged


def shared_wall_support(boundary,axis,normal):
    """Intervals with building interior on BOTH sides of an internal cut.

    The room bounding box can extend through a facade projection beyond the
    actual shared wall. Probe either side, project the intervals onto the cut,
    and intersect them so a door cannot use that unsupported bounding-box tail.
    """
    along=0 if axis=="x" else 1
    low,high=boundary.bounds[along],boundary.bounds[along+2]
    epsilon=max(1e-7,min(1e-4,(high-low)*1e-7))
    sides=[]
    for offset in (-epsilon,epsilon):
        coordinate=normal+offset
        line=LineString([(low,coordinate),(high,coordinate)] if axis=="x" else [(coordinate,low),(coordinate,high)])
        intervals=[]
        for part in line_components(boundary.intersection(line)):
            intervals.append((part.bounds[along],part.bounds[along+2]))
        sides.append(intervals)
    common=[]
    for left_a,right_a in sides[0]:
        for left_b,right_b in sides[1]:
            left,right=max(left_a,left_b),min(right_a,right_b)
            if right-left>1e-6:
                common.append((left,right))
    return sorted(common)


def constrain_internal_fixture(model,fixture,start,width,source,normal,grids,cut_bits,boundary,cache):
    """Enforce actual host intervals before solving, for every cut coordinate."""
    perpendicular="y" if fixture.axis=="x" else "x"
    if source is None:
        positions=[(normal.constant,expr(1))]
    else:
        bits=cut_bits[source]
        positions=[]
        for index,coordinate in enumerate(grids[perpendicular]):
            before=bits[index-1] if index else expr(0)
            after=bits[index] if index<len(bits) else expr(1)
            positions.append((coordinate,after-before))
    big_m=4*max(boundary.bounds[2]-boundary.bounds[0],boundary.bounds[3]-boundary.bounds[1],1)
    big_m+=max(item[1] for item in fixture.widths)+2*fixture.margin
    count=0
    minimum_width=min(item[1] for item in fixture.widths)
    for index,(coordinate,active) in enumerate(positions):
        key=(fixture.axis,float(coordinate))
        if key not in cache:
            cache[key]=shared_wall_support(boundary,fixture.axis,coordinate)
        intervals=[(lo,hi) for lo,hi in cache[key] if hi-lo>=minimum_width+2*fixture.margin-1e-6]
        if not intervals:
            model.constraint(active,upper=0,label=f"unsupported-cut-{fixture.key}-{index}")
            continue
        if len(intervals)==1:
            lo,hi=intervals[0]
            model.constraint(start+big_m*(1-active),lower=lo+fixture.margin,label=f"actual-wall-start-{fixture.key}-{index}")
            model.constraint(start+width-big_m*(1-active),upper=hi-fixture.margin,label=f"actual-wall-end-{fixture.key}-{index}")
        else:
            choices=[]
            for part,(lo,hi) in enumerate(intervals):
                chosen=model.var(f"host:{fixture.key}:{index}:{part}",integer=True)
                choices.append(chosen)
                model.constraint(start+big_m*(1-chosen),lower=lo+fixture.margin)
                model.constraint(start+width-big_m*(1-chosen),upper=hi-fixture.margin)
            model.constraint(sum(choices,Expr())-active,lower=0,upper=0)
        count+=1
    return count


def refine_fixture_positions(optimizer,fixtures,records,polygons,boundary):
    """Separate small placement solve: cuts, areas and widths remain fixed.

    A real second solve avoids relying on the 1e-8 tie-breaker, which can be
    ignored by MIP tolerances. Multiple fixtures on the same host are spread
    with balanced gaps while retaining their original order.
    """
    if not fixtures:
        return records,{"status":"no-fixtures","policy":optimizer.fixture_position}
    model = LinearModel()
    by_key = {record["id"]:record for record in records}
    groups = defaultdict(list)
    for fixture in fixtures:
        normal = by_key[fixture.key]["wallCoordinate"]
        groups[(fixture.axis,tuple(sorted(fixture.room_ids)),round(normal,5))].append(fixture)
    for group in groups.values():
        group.sort(key=lambda item:item.start)
    positions,segments,preferred = {},{},{}
    objective = Expr()
    x0,y0,x1,y1 = boundary.bounds
    big_m = 8*max(x1-x0,y1-y0,1)
    for fixture in fixtures:
        record = by_key[fixture.key]
        width = record["widthPixels"]
        normal = record["wallCoordinate"]
        intervals = actual_fixture_intervals(fixture,polygons,boundary,normal,optimizer.geometry_tolerance_pixels)
        intervals = [(a,b) for a,b in intervals if b-a>=width+2*fixture.margin-1e-6]
        if not intervals:
            raise RuntimeError(f"{fixture.key}: no actual wall interval remains for position refinement")
        start = model.var(f"position:{fixture.key}",lower=min(a for a,b in intervals),upper=max(b for a,b in intervals))
        deviation = model.var(f"position-deviation:{fixture.key}",upper=np.inf)
        choices = []
        targets = []
        group = groups[(fixture.axis,tuple(sorted(fixture.room_ids)),round(normal,5))]
        group_index = group.index(fixture)
        for index,(lo,hi) in enumerate(intervals):
            chosen = model.var(f"segment:{fixture.key}:{index}",integer=True) if len(intervals)>1 else expr(1)
            choices.append(chosen)
            model.constraint(start+big_m*(1-chosen),lower=lo+fixture.margin)
            model.constraint(start-big_m*(1-chosen),upper=hi-width-fixture.margin)
            if optimizer.fixture_position=="relative":
                fraction = fixture.original_center_fraction
                target = lo+fraction*(hi-lo)-width/2
            else:
                total_width = sum(by_key[item.key]["widthPixels"] for item in group)
                used = total_width+group[0].margin+group[-1].margin+optimizer.fixture_gap_pixels*(len(group)-1)
                extra = (hi-lo-used)/(len(group)+1)
                if extra>=0:
                    previous = sum(by_key[item.key]["widthPixels"]+optimizer.fixture_gap_pixels+extra for item in group[:group_index])
                    target = lo+group[0].margin+extra+previous
                else:
                    # Different actual wall pieces may be needed. Prefer
                    # an even spread, and let spacing/domain rules decide.
                    target = lo+(group_index+1)*(hi-lo)/(len(group)+1)-width/2
            targets.append(target)
            model.constraint(deviation-start+big_m*(1-chosen),lower=-target)
            model.constraint(deviation+start+big_m*(1-chosen),lower=target)
            objective -= .001*(hi-lo)*chosen
        model.constraint(sum(choices,Expr()),lower=1,upper=1)
        objective += deviation
        positions[fixture.key],segments[fixture.key],preferred[fixture.key] = start,choices,targets
    for a,b in combinations(fixtures,2):
        normal_a,normal_b = by_key[a.key]["wallCoordinate"],by_key[b.key]["wallCoordinate"]
        if a.axis!=b.axis or abs(normal_a-normal_b)>optimizer.geometry_tolerance_pixels:
            continue
        first,second = (a,b) if a.start<=b.start else (b,a)
        # Preserve original same-line ordering. Also prevent new collisions
        # if two formerly offset walls become collinear after optimization.
        model.constraint(positions[second.key]-positions[first.key],
                         lower=by_key[first.key]["widthPixels"]+optimizer.fixture_gap_pixels)
    solution,details = model.solve(objective,optimizer.backend,10.0,0.0)
    model.verify_solution(solution)
    updated = []
    for fixture in fixtures:
        record = by_key[fixture.key].copy()
        start = positions[fixture.key].value(solution)
        width,normal = record["widthPixels"],record["wallCoordinate"]
        choice = max(range(len(segments[fixture.key])),key=lambda index:segments[fixture.key][index].value(solution))
        path=fixture_path(fixture,start,width,normal)
        padded=fixture_path(fixture,start,width,normal,fixture.margin)
        for room_id in fixture.room_ids:
            if padded.difference(polygons[room_id].boundary.buffer(optimizer.geometry_tolerance_pixels,cap_style=2,join_style=2)).length>1e-5:
                raise RuntimeError(f"{fixture.key}: refined fixture left its actual host wall")
        record.update(optimizedStartPixels=start,positionPolicy=optimizer.fixture_position,
                      preferredStartPixels=preferred[fixture.key][choice],
                      positionDeviationPixels=abs(start-preferred[fixture.key][choice]),
                      line=[{"x":float(x),"y":float(y)} for x,y in path.coords])
        updated.append(record)
    details["policy"]=optimizer.fixture_position
    details["layoutAndWidthsFixed"]=True
    return updated,details


def attach_original_shared_profiles(fixtures,rooms,optimizer):
    """Use the original partition's real shared paths, including pixel stairs."""
    for fixture in fixtures:
        if len(fixture.room_ids)!=2:
            continue
        a,b=(rooms[room_id]["polygon"] for room_id in fixture.room_ids)
        common=a.boundary.intersection(b.boundary)
        bounds=common.bounds
        if common.is_empty:
            raise ValueError(f"{fixture.key}: original rooms have no shared wall")
        tolerance=optimizer.mapping_tolerance_pixels
        strip=(box(bounds[0]-1,fixture.normal-tolerance,bounds[2]+1,fixture.normal+tolerance)
               if fixture.axis=="x" else box(fixture.normal-tolerance,bounds[1]-1,fixture.normal+tolerance,bounds[3]+1))
        along=0 if fixture.axis=="x" else 1
        minimum=min(item[1] for item in fixture.widths)+2*fixture.margin
        candidates=[piece for piece in line_components(common.intersection(strip))
                    if piece.bounds[along+2]-piece.bounds[along]>=minimum-1e-6]
        if not candidates:
            raise ValueError(f"{fixture.key}: the unchanged shared wall cannot fit the fixture and its end margins")
        expected=Point(fixture.start+fixture.width/2,fixture.normal) if along==0 else Point(fixture.normal,fixture.start+fixture.width/2)
        chosen=min(candidates,key=lambda piece:(piece.distance(expected),-piece.length))
        fixture.host_profile=list(chosen.coords)
        fixture.host_min,fixture.host_max=chosen.bounds[along],chosen.bounds[along+2]
        perpendicular=1-along
        lengths=defaultdict(float)
        for first,second in zip(fixture.host_profile,fixture.host_profile[1:]):
            if abs(first[perpendicular]-second[perpendicular])<=1e-7:
                lengths[first[perpendicular]]+=abs(first[along]-second[along])
        if lengths:
            fixture.normal=max(lengths,key=lengths.get)
        fixture.host_normal_min=chosen.bounds[perpendicular]
        fixture.host_normal_max=chosen.bounds[perpendicular+2]
        fraction=(fixture.start+fixture.width/2-fixture.host_min)/max(fixture.host_max-fixture.host_min,1e-9)
        fixture.original_center_fraction=max(0,min(1,fraction))


def fixed_layout_size_records(optimizer,fixtures,polygons,boundary):
    """Select catalogue sizes jointly on fixed rooms; preserve mode is exact."""
    selected={fixture.key:len(fixture.widths)-1 for fixture in fixtures}
    if any(len(fixture.widths)>1 for fixture in fixtures):
        model=LinearModel()
        objective=Expr()
        expressions={}
        size_choices={}
        big_m=8*max(boundary.bounds[2]-boundary.bounds[0],boundary.bounds[3]-boundary.bounds[1],1)
        for fixture in fixtures:
            start=model.var(f"fixed-start:{fixture.key}",lower=min(boundary.bounds)-1,upper=max(boundary.bounds)+1)
            if len(fixture.widths)>1:
                choices=[model.var(f"fixed-size:{fixture.key}:{key}",integer=True) for key,_,_ in fixture.widths]
                model.constraint(sum(choices,Expr()),lower=1,upper=1)
                width=sum((choice*item[1] for choice,item in zip(choices,fixture.widths)),Expr())
                objective+=(fixture.widths[-1][1]-width)/max(fixture.widths[-1][1]-fixture.widths[0][1],1e-9)
                size_choices[fixture.key]=choices
            else:
                width=expr(fixture.widths[0][1])
            intervals=actual_fixture_intervals(fixture,polygons,boundary,fixture.normal,optimizer.geometry_tolerance_pixels)
            intervals=[(lo,hi) for lo,hi in intervals if hi-lo>=min(item[1] for item in fixture.widths)+2*fixture.margin-1e-6]
            if not intervals:
                raise ValueError(f"{fixture.key}: no fixture size fits the unchanged room wall")
            choices=[]
            for index,(lo,hi) in enumerate(intervals):
                chosen=model.var(f"fixed-segment:{fixture.key}:{index}",integer=True) if len(intervals)>1 else expr(1)
                choices.append(chosen)
                model.constraint(start+big_m*(1-chosen),lower=lo+fixture.margin)
                model.constraint(start+width-big_m*(1-chosen),upper=hi-fixture.margin)
            model.constraint(sum(choices,Expr()),lower=1,upper=1)
            expressions[fixture.key]=(start,width)
        for a,b in combinations(fixtures,2):
            if a.axis!=b.axis or abs(a.normal-b.normal)>optimizer.geometry_tolerance_pixels:
                continue
            first,second=(a,b) if a.start<=b.start else (b,a)
            sa,wa=expressions[first.key]
            sb,_=expressions[second.key]
            model.constraint(sb-sa-wa,lower=optimizer.fixture_gap_pixels)
        solution,_=model.solve(objective,optimizer.backend,10,0)
        model.verify_solution(solution)
        for key,choices in size_choices.items():
            selected[key]=max(range(len(choices)),key=lambda index:choices[index].value(solution))
    records=[]
    for fixture in fixtures:
        size,width,metadata=fixture.widths[selected[fixture.key]]
        records.append({**fixture.to_dict(),"optimizedStartPixels":fixture.start,
                        "wallCoordinate":fixture.normal,"widthPixels":width,"selectedSize":size,
                        "sizeMetadata":metadata,"widthChangePixels":width-fixture.width})
    return records


def preserve_zero_growth(optimizer,data,boundary,rooms,target_id,minimums,pixels_per_metre):
    """Exact unchanged-room result: no area rounding and no grid-area equality."""
    started=time.monotonic()
    polygons={room_id:item["polygon"] for room_id,item in rooms.items()}
    optimizer._validate_partition(boundary,rooms,target_id,minimums,polygons)
    fixtures=collect_fixtures(data,rooms,boundary,None,optimizer,pixels_per_metre)
    attach_original_shared_profiles(fixtures,rooms,optimizer)
    records=fixed_layout_size_records(optimizer,fixtures,polygons,boundary)
    records,placement=refine_fixture_positions(optimizer,fixtures,records,polygons,boundary)
    report={"fixtures":[fixture.to_dict() for fixture in fixtures],"sharedCuts":[],
            "controls":{"fixturePosition":optimizer.fixture_position,
                        "minimumAreaRatio":optimizer.minimum_area_ratio,
                        "maximumTargetGrowth":optimizer.maximum_target_growth},
            "roomGeometryPolicy":"preserve-normalized-polygons-exactly"}
    details={"status":"preserved-zero-growth","backend":"preserved-partition",
             "roomGeometryPreserved":True,"gridOptimalityOnly":False,
             "maximumTargetGrowth":optimizer.maximum_target_growth,"invalidSolutionsRejected":0,
             "fixturePlacement":placement,"elapsedSeconds":time.monotonic()-started}
    return {"polygons":polygons,"cuts":None,"fixtures":records,"constraints":report,"details":details}


def solve_push(optimizer, data, boundary, rooms, target_id, minimums, tree, pixels_per_metre):
    fixtures = collect_fixtures(data, rooms, boundary, tree, optimizer, pixels_per_metre)
    report = graph_report(fixtures, tree)
    report["controls"] = {"fixturePosition":optimizer.fixture_position,
                          "minimumAreaRatio":optimizer.minimum_area_ratio,
                          "maximumTargetGrowth":optimizer.maximum_target_growth}
    x0, y0, x1, y1 = boundary.bounds
    originals = {axis: [cut["coordinatePixels"] for cut in report["sharedCuts"] if cut["axis"] == axis] for axis in ("x", "y")}
    grids = {"x": make_grid(x0,x1,optimizer.grid_step_pixels,originals["x"]),
             "y": make_grid(y0,y1,optimizer.grid_step_pixels,originals["y"])}
    cells = []
    for i, (left, right) in enumerate(zip(grids["x"],grids["x"][1:])):
        for j, (top, bottom) in enumerate(zip(grids["y"],grids["y"][1:])):
            area = boundary.intersection(box(left,top,right,bottom)).area
            if area > 1e-8:
                cells.append((i,j,float(area)))
    if len(cells) > optimizer.max_grid_cells:
        raise ValueError(f"Push grid has {len(cells)} cells, above max_grid_cells={optimizer.max_grid_cells}. Increase --push-step or explicitly increase the limit.")
    model = LinearModel()
    cut_exprs, cut_bits, room_bounds, cut_bounds = {}, {}, {}, {}
    movement = Expr()
    def build(node, key, bounds):
        nonlocal movement
        if node.is_leaf:
            room_bounds[node.room_ids[0]] = bounds.copy()
            return
        grid = grids[node.axis]
        bits = [model.var(f"cut:{key}:at-or-before:{i}", integer=True) for i in range(len(grid)-1)]
        for a,b in zip(bits,bits[1:]):
            model.constraint(a-b, upper=0, label="ordered-cut-grid")
        position = expr(grid[-1])
        for i, bit in enumerate(bits):
            position -= (grid[i+1]-grid[i])*bit
        low, high = bounds[node.axis+"0"], bounds[node.axis+"1"]
        model.constraint(position-low, lower=1e-4, label="cut-inside-parent")
        model.constraint(high-position, lower=1e-4, label="cut-inside-parent")
        cut_exprs[key], cut_bits[key], cut_bounds[key] = position, bits, bounds
        movement += model.absolute(position-float(node.original_cut), f"cut-movement:{key}")
        left, right = bounds.copy(), bounds.copy()
        left[node.axis+"1"] = (position,key)
        right[node.axis+"0"] = (position,key)
        # Bound expressions carry their cut ID for exact column/row membership.
        build(node.first,key+"L",left)
        build(node.second,key+"R",right)
    # Internally bounds are (expression, cut id), with None at the exterior box.
    # A small wrapper lets recursive arithmetic access just the expression.
    class BoundMap(dict):
        def __getitem__(self,k):
            value = super().__getitem__(k)
            return value[0] if isinstance(value,tuple) else value
        def copy(self):
            return BoundMap(dict.items(self))
        def source(self,k):
            value = dict.__getitem__(self,k)
            return value[1] if isinstance(value,tuple) else None
    build(tree,"root",BoundMap({"x0":expr(x0),"y0":expr(y0),"x1":expr(x1),"y1":expr(y1)}))
    # Keep originally aligned cuts aligned, including independent subtrees.
    for a,b in combinations(report["sharedCuts"],2):
        if a["axis"] == b["axis"] and abs(a["coordinatePixels"]-b["coordinatePixels"]) <= optimizer.alignment_tolerance_pixels:
            model.constraint(cut_exprs[a["id"]]-cut_exprs[b["id"]], lower=0, upper=0, label="original-cut-alignment")
    def membership(bounds,axis,index):
        low_id, high_id = bounds.source(axis+"0"), bounds.source(axis+"1")
        low = cut_bits[low_id][index] if low_id else expr(1)
        high = cut_bits[high_id][index] if high_id else expr(0)
        return low-high
    areas = {}
    area_scale = max(boundary.area,1.0)
    for room_id,bounds in room_bounds.items():
        area = Expr()
        for i,j,weight in cells:
            horizontal,vertical = membership(bounds,"x",i),membership(bounds,"y",j)
            if not horizontal.terms and horizontal.constant == 0 or not vertical.terms and vertical.constant == 0:
                continue
            z = model.var(f"cell:{room_id}:{i}:{j}")
            model.constraint(z-horizontal,upper=0)
            model.constraint(z-vertical,upper=0)
            model.constraint(z-horizontal-vertical,lower=-1)
            area += (weight/area_scale)*z
        areas[room_id] = area
        model.constraint(area,lower=minimums[room_id]/area_scale,label=f"minimum-area-room-{room_id}")
    if optimizer.maximum_target_growth is not None:
        maximum = rooms[target_id]["polygon"].area*(1+optimizer.maximum_target_growth)
        model.constraint(areas[target_id],upper=maximum/area_scale,label="maximum-target-growth")
    placement = {}
    resize_cost = Expr()
    support_cache={}
    guarded_domains=0
    for fixture in fixtures:
        start = model.var(f"start:{fixture.key}", lower=min(x0,y0)-1, upper=max(x1,y1)+1)
        if len(fixture.widths) == 1:
            width = expr(fixture.widths[0][1])
            choices = []
        else:
            choices = [model.var(f"size:{fixture.key}:{key}",integer=True) for key,_,_ in fixture.widths]
            model.constraint(sum(choices,Expr()),lower=1,upper=1,label=f"one-size-{fixture.key}")
            width = sum((choice*item[1] for choice,item in zip(choices,fixture.widths)),Expr())
            preferred = max(item[1] for item in fixture.widths)
            smallest = min(item[1] for item in fixture.widths)
            resize_cost += optimizer.window_resize_penalty * (preferred-width)/max(preferred-smallest,1e-9)
        end = start+width
        a = room_bounds[fixture.room_ids[0]]
        if len(fixture.room_ids) == 2:
            b = room_bounds[fixture.room_ids[1]]
            normal = a[fixture.side]
            model.constraint(normal-b[fixture.other_side],lower=0,upper=0,label=f"same-wall-{fixture.key}")
            guarded_domains+=constrain_internal_fixture(model,fixture,start,width,a.source(fixture.side),normal,
                                                         grids,cut_bits,boundary,support_cache)
        else:
            normal = expr(fixture.normal)
            perpendicular = "y" if fixture.axis == "x" else "x"
            minimum_normal=fixture.normal if fixture.host_normal_min is None else fixture.host_normal_min
            maximum_normal=fixture.normal if fixture.host_normal_max is None else fixture.host_normal_max
            model.constraint(a[perpendicular+"0"],upper=minimum_normal+fixture.inward*.01,label=f"exterior-owner-{fixture.key}")
            model.constraint(a[perpendicular+"1"],lower=maximum_normal+fixture.inward*.01,label=f"exterior-owner-{fixture.key}")
            model.constraint(start,lower=fixture.host_min+fixture.margin,label=f"exterior-start-{fixture.key}")
            model.constraint(end,upper=fixture.host_max-fixture.margin,label=f"exterior-end-{fixture.key}")
        for room_id in fixture.room_ids:
            bounds = room_bounds[room_id]
            model.constraint(start-bounds[fixture.axis+"0"],lower=fixture.margin,label=f"start-inside-room-{fixture.key}")
            model.constraint(bounds[fixture.axis+"1"]-end,lower=fixture.margin,label=f"end-inside-room-{fixture.key}")
        movement += model.absolute(start-fixture.start,f"fixture-movement:{fixture.key}")
        placement[fixture.key] = (start,width,normal,choices)
    for a,b in combinations(fixtures,2):
        if a.axis != b.axis or abs(a.normal-b.normal) > optimizer.alignment_tolerance_pixels:
            continue
        first,second = (a,b) if a.start <= b.start else (b,a)
        sa,wa,_,_ = placement[first.key]
        sb,_,_,_ = placement[second.key]
        model.constraint(sb-sa-wa,lower=optimizer.fixture_gap_pixels,label=f"non-overlapping-{first.key}-{second.key}")
    objective = -1*areas[target_id] + resize_cost + movement * (1e-8 / max(x1-x0,y1-y0,1))
    baseline=None
    baseline_error=None
    try:
        baseline=preserve_zero_growth(optimizer,data,boundary,rooms,target_id,minimums,pixels_per_metre)
    except (ValueError,RuntimeError) as error:
        baseline_error=str(error)
    started = time.monotonic()
    report["grid"] = {"xCoordinates":grids["x"],"yCoordinates":grids["y"],"cellCount":len(cells),"requestedStepPixels":optimizer.grid_step_pixels}
    invalid = []
    def fallback(reason):
        if baseline is None:
            raise RuntimeError(reason+" The unchanged partition was not a valid fallback: "+str(baseline_error))
        baseline["details"].update(status="feasible-fallback",fallbackReason=reason,
                                   fallbackSource="validated-unchanged-normalized-partition",
                                   optimizationImprovementFound=False,
                                   invalidSolutionsRejected=len(invalid),invalidReasons=list(invalid),
                                   elapsedSeconds=time.monotonic()-started,
                                   actualWallDomainsPrecomputed=guarded_domains)
        return baseline
    for attempt in range(optimizer.max_invalid_solutions+1):
        remaining = optimizer.time_limit_seconds-(time.monotonic()-started)
        if remaining <= 0:
            return fallback("Push reached its layout-search time budget; returning the validated unchanged partition with no target growth.")
        try:
            solution,details = model.solve(objective,optimizer.backend,remaining,optimizer.mip_relative_gap)
        except RuntimeError as error:
            return fallback("The grid search did not return an improved valid layout: "+str(error))
        model.verify_solution(solution)
        polygons = {}
        reason = None
        bad_fixture = None
        bad_room_id = None
        for room_id,bounds in room_bounds.items():
            bounds_values = [bounds[key].value(solution) for key in ("x0","y0","x1","y1")]
            polygon = polygon_only(boundary.intersection(box(*bounds_values)))
            if polygon is None or polygon.interiors:
                reason = f"room {room_id} disconnected or contains a hole"
                bad_room_id=room_id
                break
            polygons[room_id] = polygon
        optimized_fixtures = []
        if reason is None:
            for fixture in fixtures:
                start_expr,width_expr,normal_expr,choices = placement[fixture.key]
                start,width,normal = (value.value(solution) for value in (start_expr,width_expr,normal_expr))
                # Read the chosen catalogue record, never resize a door/opening.
                chosen_index = max(range(len(choices)),key=lambda i:choices[i].value(solution)) if choices else 0
                size_id,_,size_meta = fixture.widths[chosen_index]
                line=fixture_path(fixture,start,width,normal)
                # Validate the complete occupied interval plus endpoint margins.
                expanded=fixture_path(fixture,start,width,normal,fixture.margin)
                for room_id in fixture.room_ids:
                    wall = polygons[room_id].boundary.buffer(optimizer.geometry_tolerance_pixels,cap_style=2,join_style=2)
                    if expanded.difference(wall).length > 1e-5:
                        reason = f"{fixture.key} does not fit the actual wall of room {room_id}"
                        bad_fixture = fixture
                        break
                if len(fixture.room_ids)==1 and line.difference(boundary.boundary.buffer(optimizer.geometry_tolerance_pixels)).length>1e-5:
                    reason = f"{fixture.key} left the exterior boundary"
                    bad_fixture = fixture
                optimized_fixtures.append({**fixture.to_dict(),"optimizedStartPixels":start,"widthPixels":width,
                                           "wallCoordinate":normal,"selectedSize":size_id,"sizeMetadata":size_meta,
                                           "line":[{"x":float(x),"y":float(y)} for x,y in line.coords],
                                           "widthChangePixels":width-fixture.width})
                if reason:
                    break
        if reason is None:
            optimizer._validate_partition(boundary,rooms,target_id,minimums,polygons)
            # Exact reconstruction must match the cell model's areas.
            for room_id,polygon in polygons.items():
                if abs(polygon.area-areas[room_id].value(solution)*area_scale)>optimizer.area_tolerance_pixels:
                    raise RuntimeError("Push grid area and polygon area disagree; refusing to return the layout")
            optimized_fixtures,position_details = refine_fixture_positions(optimizer,fixtures,optimized_fixtures,polygons,boundary)
            details.update({"gridOptimalityOnly":True,"invalidSolutionsRejected":len(invalid),"invalidReasons":invalid,
                            "variables":len(model.names),"constraints":len(model.rows),"gridCells":len(cells),
                            "windowResizePenaltyAreaFraction":optimizer.window_resize_penalty,
                            "maximumTargetGrowth":optimizer.maximum_target_growth,
                            "actualWallDomainsPrecomputed":guarded_domains,
                            "fixturePlacement":position_details,
                            "elapsedSeconds":time.monotonic()-started})
            return {"polygons":polygons,"cuts":{key:value.value(solution) for key,value in cut_exprs.items()},
                    "fixtures":optimized_fixtures,"constraints":report,"details":details}
        invalid.append(reason)
        terms = Expr()
        context_rooms=bad_fixture.room_ids if bad_fixture is not None else [bad_room_id]
        relevant_cuts=set()
        for room_id in context_rooms:
            for side in ("x0","y0","x1","y1"):
                source=room_bounds[room_id].source(side)
                if source is not None:
                    relevant_cuts.add(source)
        for cut_id in sorted(relevant_cuts):
            bits=cut_bits[cut_id]
            for bit in bits:
                terms += 1-bit if bit.value(solution)>.5 else bit
        if bad_fixture is None:
            # Exclude the offending room box independently of unrelated cuts.
            model.constraint(terms,lower=1,label="invalid-geometry-cut")
        else:
            # Do not ban a feasible cut layout merely because a fixture could
            # slide to another real segment of a concave wall. Conditional on
            # these cut choices, require it to fit one actual common segment.
            fixture = bad_fixture
            start,width,normal_expr,_ = placement[fixture.key]
            normal = normal_expr.value(solution)
            full_line = LineString(fixture.host_profile) if fixture.host_profile else LineString([(x0,normal),(x1,normal)] if fixture.axis=="x" else [(normal,y0),(normal,y1)])
            common = full_line
            for room_id in fixture.room_ids:
                common = common.intersection(polygons[room_id].boundary)
            if len(fixture.room_ids)==1:
                common = common.intersection(boundary.boundary)
            pieces = line_components(common)
            intervals = []
            along_index = 0 if fixture.axis=="x" else 1
            for piece in pieces:
                lo,hi = piece.bounds[along_index],piece.bounds[along_index+2]
                if hi-lo >= min(item[1] for item in fixture.widths)+2*fixture.margin-1e-6:
                    intervals.append((lo,hi))
            selected_segments = []
            big_m = 4*max(x1-x0,y1-y0,1)+max(item[1] for item in fixture.widths)+2*fixture.margin
            for index,(lo,hi) in enumerate(intervals):
                chosen = model.var(f"repair:{attempt}:{fixture.key}:{index}",integer=True)
                selected_segments.append(chosen)
                model.constraint(start+big_m*(1-chosen),lower=lo+fixture.margin)
                model.constraint(start+width-big_m*(1-chosen),upper=hi-fixture.margin)
            model.constraint(sum(selected_segments,Expr())+terms,lower=1,label=f"actual-wall-interval-{fixture.key}")
    return fallback(f"The grid search exhausted {len(invalid)} geometry retries. Last rejected candidate: {invalid[-1]}")
