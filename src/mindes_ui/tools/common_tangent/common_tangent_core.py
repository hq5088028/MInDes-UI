"""NumPy/VTK numerical core for two-phase constrained ternary sections."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import vtk


def _aggregate_xy(x, y, values):
    buckets = {}
    for xv, yv, value in zip(x, y, values):
        if np.isfinite(xv) and np.isfinite(yv) and np.isfinite(value):
            buckets.setdefault((float(xv), float(yv)), []).append(float(value))
    points = np.asarray(list(buckets), float)
    result = np.asarray([np.mean(buckets[key]) for key in buckets], float)
    return points, result


class LinearTriangleInterpolator:
    """Piecewise-linear 2D interpolation with nearest-neighbour fallback."""
    def __init__(self, x, y, values):
        points, values = _aggregate_xy(np.asarray(x, float), np.asarray(y, float), np.asarray(values, float))
        if len(points) < 3: raise ValueError("At least three finite, distinct composition points are required.")
        if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2: raise ValueError("Composition points are collinear.")
        vtk_points = vtk.vtkPoints()
        for point in points: vtk_points.InsertNextPoint(float(point[0]), float(point[1]), 0.0)
        source = vtk.vtkPolyData(); source.SetPoints(vtk_points)
        delaunay = vtk.vtkDelaunay2D(); delaunay.SetInputData(source); delaunay.SetTolerance(0.0); delaunay.Update()
        triangles_filter = vtk.vtkTriangleFilter(); triangles_filter.SetInputConnection(delaunay.GetOutputPort()); triangles_filter.Update()
        output = triangles_filter.GetOutput()
        if output.GetNumberOfCells() == 0: raise ValueError("VTK could not triangulate the composition points.")
        out_points = np.asarray([output.GetPoint(i)[:2] for i in range(output.GetNumberOfPoints())], float)
        distances = ((out_points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2)
        out_values = values[np.argmin(distances, axis=1)]
        triangles = []
        for cell_index in range(output.GetNumberOfCells()):
            cell = output.GetCell(cell_index)
            if cell.GetNumberOfPoints() == 3: triangles.append([cell.GetPointId(i) for i in range(3)])
        if not triangles: raise ValueError("VTK triangulation contains no triangles.")
        self.points = out_points; self.values = out_values; self.triangles = np.asarray(triangles, int)
        tri_points = self.points[self.triangles]
        self._p0 = tri_points[:, 0]
        matrices = np.stack([tri_points[:, 1] - tri_points[:, 0], tri_points[:, 2] - tri_points[:, 0]], axis=2)
        valid = np.abs(np.linalg.det(matrices)) > 1e-15
        self.triangles = self.triangles[valid]; self._p0 = self._p0[valid]; self._inverse = np.linalg.inv(matrices[valid])

    def __call__(self, x, y):
        x_array, y_array = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        queries = np.column_stack([x_array.ravel(), y_array.ravel()]); output = np.empty(len(queries), float)
        for start in range(0, len(queries), 256):
            query = queries[start:start + 256]; delta = query[:, None, :] - self._p0[None, :, :]
            bary = np.einsum("tij,btj->bti", self._inverse, delta)
            inside = (bary[..., 0] >= -1e-10) & (bary[..., 1] >= -1e-10) & (bary.sum(axis=2) <= 1.0 + 1e-10)
            found = inside.any(axis=1); indices = inside.argmax(axis=1)
            chosen = self.triangles[indices]
            weights = np.column_stack([1.0 - bary[np.arange(len(query)), indices].sum(axis=1),
                                       bary[np.arange(len(query)), indices, 0], bary[np.arange(len(query)), indices, 1]])
            values = (self.values[chosen] * weights).sum(axis=1)
            if (~found).any():
                nearest = ((query[~found, None, :] - self.points[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
                values[~found] = self.values[nearest]
            output[start:start + len(query)] = values
        return output.reshape(x_array.shape)


def triangle_grid(n):
    if n < 2: raise ValueError("Grid resolution must be at least 2.")
    return np.asarray([(i / n, j / n) for i in range(n + 1) for j in range(n + 1 - i)], float)


def lower_hull_simplices(points3d):
    points = np.asarray(points3d, float)
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 4: raise ValueError("At least four 3D points are required for a convex hull.")
    if not np.isfinite(points).all(): raise ValueError("Convex-hull points must be finite.")
    span = np.ptp(points, axis=0); span[span <= 1e-15] = 1.0
    normalized = (points - points.min(axis=0)) / span
    if np.linalg.matrix_rank(normalized - normalized.mean(axis=0)) < 3: raise ValueError("The combined free-energy points are coplanar; a 3D lower hull cannot be formed.")
    vtk_points = vtk.vtkPoints(); original = vtk.vtkIdTypeArray(); original.SetName("original_id")
    for index, point in enumerate(normalized): vtk_points.InsertNextPoint(*map(float, point)); original.InsertNextValue(index)
    source = vtk.vtkPolyData(); source.SetPoints(vtk_points); source.GetPointData().AddArray(original)
    delaunay = vtk.vtkDelaunay3D(); delaunay.SetInputData(source); delaunay.SetTolerance(0.0); delaunay.BoundingTriangulationOff(); delaunay.Update()
    if delaunay.GetOutput().GetNumberOfCells() == 0: raise ValueError("VTK could not construct the 3D convex hull.")
    surface = vtk.vtkDataSetSurfaceFilter(); surface.SetInputConnection(delaunay.GetOutputPort()); surface.PassThroughPointIdsOn(); surface.Update()
    triangles_filter = vtk.vtkTriangleFilter(); triangles_filter.SetInputConnection(surface.GetOutputPort()); triangles_filter.Update()
    poly = triangles_filter.GetOutput(); ids = poly.GetPointData().GetArray("original_id"); center = normalized.mean(axis=0); selected = []
    for cell_index in range(poly.GetNumberOfCells()):
        cell = poly.GetCell(cell_index)
        if cell.GetNumberOfPoints() != 3: continue
        local = [cell.GetPointId(i) for i in range(3)]; face = np.asarray([poly.GetPoint(value) for value in local], float)
        normal = np.cross(face[1] - face[0], face[2] - face[0]); length = np.linalg.norm(normal)
        if length <= 1e-14: continue
        normal /= length
        if np.dot(normal, face.mean(axis=0) - center) < 0: normal *= -1
        if normal[2] >= -1e-12: continue
        if ids is not None: mapped = [int(ids.GetTuple1(value)) for value in local]
        else: mapped = [int(np.argmin(((normalized - face_point) ** 2).sum(axis=1))) for face_point in face]
        if len(set(mapped)) == 3: selected.append(tuple(mapped))
    unique = list(dict.fromkeys(tuple(sorted(value)) for value in selected))
    if not unique: raise ValueError("No lower convex-hull faces were found.")
    return np.asarray(unique, int)


def _deduplicate_ties(segments_xy, segments_3d):
    seen = set(); xy_result = []; xyz_result = []
    for xy, xyz in zip(segments_xy, segments_3d):
        key = tuple(sorted((tuple(np.round(xy[0], 12)), tuple(np.round(xy[1], 12)))))
        if key in seen: continue
        seen.add(key); xy_result.append(xy); xyz_result.append(xyz)
    return xy_result, xyz_result


def compute_common_tangent(Ga_func, Gb_func, n=60):
    grid = triangle_grid(n); Ga = np.asarray(Ga_func(grid[:, 0], grid[:, 1]), float).reshape(-1); Gb = np.asarray(Gb_func(grid[:, 0], grid[:, 1]), float).reshape(-1)
    finite = np.concatenate([Ga[np.isfinite(Ga)], Gb[np.isfinite(Gb)]])
    if not len(finite): raise ValueError("Both free-energy functions returned only invalid values.")
    big = float(np.max(finite) + max(np.ptp(finite), 1.0) * 1000.0); Ga = np.where(np.isfinite(Ga), Ga, big); Gb = np.where(np.isfinite(Gb), Gb, big)
    all_points = np.vstack([np.column_stack([grid, Ga]), np.column_stack([grid, Gb])]); count = len(grid)
    labels = np.concatenate([np.zeros(count, int), np.ones(count, int)]); simplices = lower_hull_simplices(all_points)
    tie_xy = []; tie_3d = []; mixed = []
    for simplex in simplices:
        phases = labels[simplex]
        if phases.min() == phases.max(): continue
        mixed.append(all_points[simplex])
        for i in range(3):
            for j in range(i + 1, 3):
                if labels[simplex[i]] == labels[simplex[j]]: continue
                a_index = simplex[i] if labels[simplex[i]] == 0 else simplex[j]; b_index = simplex[j] if labels[simplex[j]] == 1 else simplex[i]
                tie_xy.append((all_points[a_index, :2], all_points[b_index, :2])); tie_3d.append((all_points[a_index], all_points[b_index]))
    tie_xy, tie_3d = _deduplicate_ties(tie_xy, tie_3d)
    return {"grid": grid, "all_points": all_points, "phase_label": labels, "simplices": simplices,
            "tie_segments_xy": tie_xy, "tie_segments_3d": tie_3d, "mixed_faces_3d": mixed,
            "grid_resolution": 1.0 / n, "grid_n": int(n)}


def phase_fraction(x_total, tie_segments_xy):
    x_total = np.asarray(x_total, float); best = None; best_distance = np.inf
    for pa, pb in tie_segments_xy:
        pa = np.asarray(pa, float); pb = np.asarray(pb, float); vector = pb - pa; length2 = vector @ vector
        if length2 < 1e-14: continue
        fraction_b = np.clip((x_total - pa) @ vector / length2, 0.0, 1.0); distance = np.linalg.norm(x_total - (pa + fraction_b * vector))
        if distance < best_distance: best_distance = distance; best = (pa, pb, 1.0 - fraction_b, fraction_b, distance)
    return best


@dataclass
class PhaseTable:
    components: tuple[str, ...]
    compositions: np.ndarray
    gibbs: np.ndarray
    label: str = ""

    def __post_init__(self):
        self.compositions = np.asarray(self.compositions, float); self.gibbs = np.asarray(self.gibbs, float)
        self.components = tuple(str(value) for value in self.components)
        if len(set(self.components)) != len(self.components): raise ValueError("Component names must be unique.")
        if self.compositions.ndim != 2 or self.compositions.shape[1] != len(self.components): raise ValueError("Composition table shape does not match component names.")
        if len(self.compositions) != len(self.gibbs): raise ValueError("Composition and G columns must have equal length.")
        finite = np.isfinite(self.compositions).all(axis=1) & np.isfinite(self.gibbs); self.compositions = self.compositions[finite]; self.gibbs = self.gibbs[finite]
        if len(self.compositions) < 3: raise ValueError("At least three finite rows are required.")
        if np.any(self.compositions < -1e-8) or np.any(np.abs(self.compositions.sum(axis=1) - 1.0) > 1e-5): raise ValueError("Each composition row must be non-negative and sum to 1.")

    def section(self, active_components, fixed_values=None, tolerances=None):
        active = tuple(active_components)
        if len(active) != 3 or len(set(active)) != 3 or any(value not in self.components for value in active): raise ValueError("Exactly three distinct active components are required.")
        fixed_values = dict(fixed_values or {}); tolerances = dict(tolerances or {})
        fixed_names = [value for value in self.components if value not in active]
        if set(fixed_values) != set(fixed_names): raise ValueError("A fixed value is required for every non-active component.")
        if any(float(fixed_values[name]) < 0.0 for name in fixed_names): raise ValueError("Fixed component fractions must be non-negative.")
        if any(float(tolerances.get(name, 1e-6)) < 0.0 for name in fixed_names): raise ValueError("Fixed-component tolerances must be non-negative.")
        fixed_sum = sum(float(fixed_values[name]) for name in fixed_names); active_total = 1.0 - fixed_sum
        if active_total <= 1e-12: raise ValueError("Fixed component fractions must sum to less than 1.")
        mask = np.ones(len(self.compositions), bool)
        for name in fixed_names:
            index = self.components.index(name); mask &= np.abs(self.compositions[:, index] - float(fixed_values[name])) <= float(tolerances.get(name, 1e-6))
        rows = self.compositions[mask]; gibbs = self.gibbs[mask]
        if len(rows) < 3: raise ValueError(f"Only {len(rows)} rows match the requested fixed-component section.")
        indices = [self.components.index(name) for name in active]; selected = rows[:, indices]; totals = selected.sum(axis=1)
        if np.any(totals <= 1e-12): raise ValueError("The active-component total is zero in the selected section.")
        normalized = selected / totals[:, None]
        interpolator = LinearTriangleInterpolator(normalized[:, 0], normalized[:, 1], gibbs)
        return CompositionSection(self.components, active, fixed_values, active_total, interpolator, int(len(rows)), self.label)


@dataclass
class CompositionSection:
    components: tuple[str, ...]
    active_components: tuple[str, str, str]
    fixed_values: dict[str, float]
    active_total: float
    interpolator: LinearTriangleInterpolator
    n_points: int
    label: str = ""

    def __call__(self, u1, u2): return self.interpolator(u1, u2)

    def full_composition(self, u1, u2):
        values = dict(self.fixed_values); u3 = 1.0 - float(u1) - float(u2)
        for name, value in zip(self.active_components, (u1, u2, u3)): values[name] = float(value) * self.active_total
        return np.asarray([values[name] for name in self.components], float)
