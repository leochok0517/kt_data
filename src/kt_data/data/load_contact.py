"""NIMS contact matrices (15 age groups) loader.

원본 .npz 형식: [participant, contact]  (NIMS 컨벤션)
모델 컨벤션:    [contact, participant]   (Y=contact, X=participant — origin='lower' 좌표평면)
→ transpose_to_model_convention=True 면 .T 적용.

사용 키: home / work / school / other (각 15×15, contacts per person per day)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from kt_data.data import DATA_ROOT

AGE_LABELS_15: list[str] = [
    "0-4", "5-9", "10-14", "15-19", "20-24", "25-29",
    "30-34", "35-39", "40-44", "45-49", "50-54", "55-59",
    "60-64", "65-69", "70+",
]
AGE_STARTS_15: list[int] = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]

SETTINGS = ("home", "work", "school", "other")

# 잠정 λ — NIMS notebook 04/06 확인 후 조정 예정
DEFAULT_LAMBDAS: dict[str, dict[str, float]] = {
    "weekday_school":   {"home": 1.0, "work": 1.0, "school": 1.0, "other": 1.0},
    "vacation_weekday": {"home": 1.1, "work": 1.0, "school": 0.2, "other": 1.1},
    "weekend":          {"home": 1.3, "work": 0.2, "school": 0.0, "other": 1.2},
    "holiday":          {"home": 1.3, "work": 0.2, "school": 0.0, "other": 1.2},
}


def load_contact_matrices(
    path: Path | None = None,
    transpose_to_model_convention: bool = True,
) -> dict:
    """NIMS contact matrices를 모델 컨벤션으로 로드.

    Args:
        path: empirical_matrices_15.npz
        transpose_to_model_convention: True면 [contact, participant] 형태로 transpose

    Returns:
        dict {
            'C_home', 'C_work', 'C_school', 'C_other': (15,15) np.float64,
            'age_labels': 15개,
            'age_starts': 15개,
            'metadata': dict,
        }
    """
    if path is None:
        path = DATA_ROOT / "external" / "contact_matrices" / "empirical_matrices_15.npz"
    if not path.exists():
        raise FileNotFoundError(path)

    with np.load(path, allow_pickle=True) as npz:
        raw = {s: np.asarray(npz[s], dtype=np.float64) for s in SETTINGS}

    matrices: dict[str, np.ndarray] = {}
    for s, M in raw.items():
        if M.shape != (15, 15):
            raise ValueError(f"{s} expected (15,15), got {M.shape}")
        matrices[f"C_{s}"] = M.T.copy() if transpose_to_model_convention else M.copy()

    return {
        **matrices,
        "age_labels": list(AGE_LABELS_15),
        "age_starts": list(AGE_STARTS_15),
        "metadata": {
            "source": str(path),
            "transposed": bool(transpose_to_model_convention),
            "sums": {f"C_{s}": float(matrices[f"C_{s}"].sum()) for s in SETTINGS},
        },
    }


def get_contact_matrix(
    matrices: dict,
    daytype: str,
    lambdas: dict | None = None,
) -> np.ndarray:
    """C(t) = λ_home·C_home + λ_work·C_work + λ_school·C_school + λ_other·C_other."""
    if lambdas is None:
        if daytype not in DEFAULT_LAMBDAS:
            raise ValueError(
                f"unknown daytype {daytype!r}; choose from {list(DEFAULT_LAMBDAS)} "
                f"or pass `lambdas` explicitly"
            )
        lambdas = DEFAULT_LAMBDAS[daytype]

    C = np.zeros((15, 15), dtype=np.float64)
    for s in SETTINGS:
        if s in lambdas:
            C += lambdas[s] * matrices[f"C_{s}"]
    return C


def plot_contact_matrices(
    matrices: dict,
    output_path: Path | None = None,
    log_scale: bool = False,
) -> None:
    """2×2 heatmap.  Y=contact (origin='lower'), X=participant."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    labels = matrices["age_labels"]
    layout = [("C_home", 0, 0), ("C_work", 0, 1), ("C_school", 1, 0), ("C_other", 1, 1)]

    fig, axes = plt.subplots(2, 2, figsize=(12, 11))
    for key, r, c in layout:
        M = matrices[key]
        ax = axes[r, c]
        if log_scale:
            vmin = max(M[M > 0].min(), 1e-4) if (M > 0).any() else 1e-4
            im = ax.imshow(M, origin="lower", cmap="viridis", norm=LogNorm(vmin=vmin, vmax=M.max()))
        else:
            im = ax.imshow(M, origin="lower", cmap="viridis")
        ax.set_title(f"{key}  (Σ = {M.sum():.2f})")
        ax.set_xlabel("Participant age")
        ax.set_ylabel("Contact age")
        ax.set_xticks(range(15))
        ax.set_yticks(range(15))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(labels, fontsize=8)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    plt.tight_layout()
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=120, bbox_inches="tight")
        print(f"saved {output_path}")
    plt.close(fig)


if __name__ == "__main__":
    result = load_contact_matrices()
    labels = result["age_labels"]

    print(f"Shape: {result['C_home'].shape}")
    print(f"Age labels: {labels}")
    print()

    for name in ("C_home", "C_work", "C_school", "C_other"):
        M = result[name]
        idx = int(np.argmax(M))
        c_idx, p_idx = divmod(idx, 15)  # M is (contact, participant)
        print(f"{name}:")
        print(f"  Σ = {M.sum():.2f}")
        print(f"  대각선(row=col) 평균 = {np.diag(M).mean():.3f}")
        print(
            f"  최대값 = {M.max():.3f}  "
            f"at (contact={labels[c_idx]}, participant={labels[p_idx]})"
        )
        print()

    plot_contact_matrices(result, output_path=Path("outputs/contact_matrices_15.png"))

    C_weekday = get_contact_matrix(result, daytype="weekday_school")
    C_vacation = get_contact_matrix(result, daytype="vacation_weekday")
    C_weekend = get_contact_matrix(result, daytype="weekend")
    print(f"\nC(weekday_school)   Σ = {C_weekday.sum():.2f}")
    print(f"C(vacation_weekday) Σ = {C_vacation.sum():.2f}")
    print(f"C(weekend)          Σ = {C_weekend.sum():.2f}")
    print(f"학교 폐쇄(weekday→weekend) 감소: {C_weekday.sum() - C_weekend.sum():.2f}")
