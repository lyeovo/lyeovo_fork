from dataclasses import dataclass
import numpy as np
from src.utils.config_io import load_yaml, save_yaml

@dataclass
class StereoParams:
    image_width: int
    image_height: int
    K_left: np.ndarray
    D_left: np.ndarray
    K_right: np.ndarray
    D_right: np.ndarray
    R: np.ndarray
    T: np.ndarray

def load_stereo_params(path: str) -> StereoParams:
    d = load_yaml(path)
    return StereoParams(
        int(d["image_width"]), int(d["image_height"]),
        np.asarray(d["K_left"], dtype=float).reshape(3, 3),
        np.asarray(d["D_left"], dtype=float).reshape(-1, 1),
        np.asarray(d["K_right"], dtype=float).reshape(3, 3),
        np.asarray(d["D_right"], dtype=float).reshape(-1, 1),
        np.asarray(d["R"], dtype=float).reshape(3, 3),
        np.asarray(d["T"], dtype=float).reshape(3, 1),
    )

def save_stereo_params(params: StereoParams, path: str) -> None:
    save_yaml({
        "image_width": int(params.image_width),
        "image_height": int(params.image_height),
        "K_left": params.K_left.tolist(),
        "D_left": np.ravel(params.D_left).tolist(),
        "K_right": params.K_right.tolist(),
        "D_right": np.ravel(params.D_right).tolist(),
        "R": params.R.tolist(),
        "T": np.asarray(params.T).reshape(3, 1).tolist(),
    }, path)
