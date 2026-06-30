"""
Ternary Gibbs free energy polynomial fitting — core logic.

Two fitting modes are supported:

1.  "bivariate" — fit G as a bivariate polynomial in (x1, x2) with independent
    degrees d1, d2. Basis functions are x1^i * x2^j for 0 <= i <= d1,
    0 <= j <= d2.

2.  "ternary"  — fit G as a polynomial in (x1, x2, x3) where x3 = 1 - x1 - x2,
    with independent degrees d1, d2, d3. Basis functions are
    x1^i * x2^j * x3^k for 0 <= i <= d1, 0 <= j <= d2, 0 <= k <= d3.
    This form is more natural for thermodynamic Gibbs-energy surfaces over
    the Gibbs triangle because it treats all three components symmetrically.

Both modes use ordinary least squares (numpy.linalg.lstsq).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class FitResult:
    mode: str                       # "bivariate" or "ternary"
    degrees: Tuple[int, ...]        # (d1, d2) or (d1, d2, d3)
    terms: List[Tuple[int, ...]]    # list of exponent tuples, one per coeff
    coeffs: np.ndarray              # fitted coefficients, same length as terms
    rmse: float
    max_abs_err: float
    r2: float
    n_points: int
    n_params: int

    def formula_string(self, precision: int = 6) -> str:
        """Return a human-readable formula."""
        var_names = ("x1", "x2") if self.mode == "bivariate" else ("x1", "x2", "x3")
        parts = []
        for exps, c in zip(self.terms, self.coeffs):
            term_vars = []
            for name, e in zip(var_names, exps):
                if e == 0:
                    continue
                term_vars.append(name if e == 1 else f"{name}^{e}")
            body = "*".join(term_vars) if term_vars else "1"
            parts.append(f"({c:+.{precision}e}) * {body}")
        return "G = " + "\n    + ".join(parts)


def _build_terms(degrees: Tuple[int, ...]) -> List[Tuple[int, ...]]:
    """Enumerate exponent tuples for a tensor-product polynomial basis."""
    from itertools import product
    ranges = [range(d + 1) for d in degrees]
    return [tuple(t) for t in product(*ranges)]


def _build_design_matrix(
    X: np.ndarray, terms: List[Tuple[int, ...]]
) -> np.ndarray:
    """X has shape (N, k); terms is a list of length-k exponent tuples."""
    N = X.shape[0]
    A = np.ones((N, len(terms)), dtype=float)
    for j, exps in enumerate(terms):
        col = np.ones(N, dtype=float)
        for i, e in enumerate(exps):
            if e != 0:
                col = col * (X[:, i] ** e)
        A[:, j] = col
    return A


def load_csv(path: str) -> pd.DataFrame:
    """Load CSV. Expects columns x1, x2, G (case-insensitive). Tolerates BOM."""
    df = pd.read_csv(path)
    # normalize column names
    lookup = {c.lower().strip().lstrip("\ufeff"): c for c in df.columns}
    needed = ["x1", "x2", "g"]
    missing = [n for n in needed if n not in lookup]
    if missing:
        raise ValueError(
            f"CSV is missing required columns {missing}. "
            f"Found columns: {list(df.columns)}"
        )
    df = df.rename(columns={lookup["x1"]: "x1", lookup["x2"]: "x2", lookup["g"]: "G"})
    df = df[["x1", "x2", "G"]].dropna().reset_index(drop=True)
    return df


def fit(
    df: pd.DataFrame,
    mode: str,
    degrees: Tuple[int, ...],
) -> FitResult:
    """
    Fit G against (x1, x2) or (x1, x2, x3=1-x1-x2) with a tensor-product basis.

    Parameters
    ----------
    df : DataFrame with columns x1, x2, G
    mode : "bivariate" or "ternary"
    degrees : (d1, d2) for bivariate, (d1, d2, d3) for ternary
    """
    if mode == "bivariate":
        if len(degrees) != 2:
            raise ValueError("bivariate mode needs 2 degrees (d1, d2)")
        X = df[["x1", "x2"]].to_numpy(dtype=float)
    elif mode == "ternary":
        if len(degrees) != 3:
            raise ValueError("ternary mode needs 3 degrees (d1, d2, d3)")
        x1 = df["x1"].to_numpy(dtype=float)
        x2 = df["x2"].to_numpy(dtype=float)
        x3 = 1.0 - x1 - x2
        X = np.column_stack([x1, x2, x3])
    else:
        raise ValueError(f"unknown mode {mode!r}")

    y = df["G"].to_numpy(dtype=float)
    terms = _build_terms(tuple(degrees))
    A = _build_design_matrix(X, terms)

    if A.shape[0] < A.shape[1]:
        raise ValueError(
            f"Not enough data points ({A.shape[0]}) for the requested basis "
            f"size ({A.shape[1]}). Lower the degrees."
        )

    coeffs, *_ = np.linalg.lstsq(A, y, rcond=None)
    y_pred = A @ coeffs
    resid = y - y_pred
    rmse = float(np.sqrt(np.mean(resid ** 2)))
    max_abs_err = float(np.max(np.abs(resid)))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    return FitResult(
        mode=mode,
        degrees=tuple(degrees),
        terms=terms,
        coeffs=coeffs,
        rmse=rmse,
        max_abs_err=max_abs_err,
        r2=r2,
        n_points=int(A.shape[0]),
        n_params=int(A.shape[1]),
    )


def predict(result: FitResult, x1: np.ndarray, x2: np.ndarray) -> np.ndarray:
    """Evaluate the fitted polynomial on arbitrary (x1, x2) arrays."""
    x1 = np.asarray(x1, dtype=float)
    x2 = np.asarray(x2, dtype=float)
    shape = x1.shape
    x1f = x1.ravel()
    x2f = x2.ravel()
    if result.mode == "bivariate":
        X = np.column_stack([x1f, x2f])
    else:
        x3f = 1.0 - x1f - x2f
        X = np.column_stack([x1f, x2f, x3f])
    A = _build_design_matrix(X, result.terms)
    y = A @ result.coeffs
    return y.reshape(shape)


def coeff_table(result: FitResult) -> pd.DataFrame:
    """Return coefficients as a tidy DataFrame for display/export."""
    if result.mode == "bivariate":
        cols = ["i (x1)", "j (x2)", "coefficient"]
        rows = [(e[0], e[1], c) for e, c in zip(result.terms, result.coeffs)]
    else:
        cols = ["i (x1)", "j (x2)", "k (x3)", "coefficient"]
        rows = [(e[0], e[1], e[2], c) for e, c in zip(result.terms, result.coeffs)]
    return pd.DataFrame(rows, columns=cols)
