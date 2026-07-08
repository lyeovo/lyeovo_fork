from pathlib import Path
import cv2
import numpy as np
from src.calibration.stereo_params import load_stereo_params
from src.calibration.stereo_rectifier import StereoRectifier
from src.detection.circle_detector import CircleDetector
from src.detection.visualization_2d import draw_matches
from src.interface.json_publisher import JsonResultPublisher
from src.interface.result_schema import TargetPoseResult
from src.stereo.stereo_matcher import StereoPointMatcher
from src.stereo.triangulator import StereoTriangulator
from src.target.pose_estimator import estimate_pose_with_fallback, estimate_target_pose
from src.target.target_cluster import cluster_targets
from src.target.target_identifier import TargetIdentifier
from src.target.template_database import TargetTemplateDatabase
from src.target.template_matcher import compute_confidence, confidence_status, match_current_points
from src.utils.config_io import load_yaml
from src.utils.time_utils import now_timestamp, filename_timestamp

def load_runtime_config(path="config/runtime_config.yaml"):
    return load_yaml(path)

def build_components(config):
    stereo = load_stereo_params(config["paths"]["stereo_params"])
    rectifier = StereoRectifier(stereo, alpha=float(config["rectification"].get("alpha", 0)))
    detector = CircleDetector.from_config(config)
    matcher = StereoPointMatcher(**config["stereo_matching"])
    triangulator = StereoTriangulator(rectifier.P1, rectifier.P2)
    identifier = TargetIdentifier(config["paths"].get("target_config"))
    out = config["output"]
    publisher = JsonResultPublisher(config["paths"]["output_json_dir"], out["save_json"], out["print_json"])
    database = TargetTemplateDatabase(config["paths"].get("target_database", "config/target_database.yaml"))
    return rectifier, detector, matcher, triangulator, identifier, publisher, database

def process_pair(left_img, right_img, config, save_visualization=True):
    rectifier, detector, matcher, triangulator, identifier, publisher, database = build_components(config)
    left_rect, right_rect = rectifier.rectify(left_img, right_img)
    left_circles = detector.detect(left_rect, side="left", debug_name="left")
    right_circles = detector.detect(right_rect, side="right", debug_name="right")
    min_points = int(config.get("circle_detection", {}).get("min_points", 0))
    if min_points:
        if len(left_circles) < min_points:
            print(f"[WARN] Only {len(left_circles)} left circles detected, expected at least {min_points}.")
        if len(right_circles) < min_points:
            print(f"[WARN] Only {len(right_circles)} right circles detected, expected at least {min_points}.")
    if not left_circles:
        print("[WARN] No circles detected in left image.")
    if not right_circles:
        print("[WARN] No circles detected in right image.")
    matches = matcher.match(left_circles, right_circles)
    if len(matches) < 3:
        print(f"[WARN] Only {len(matches)} stereo matches found, skip pose estimation.")
    points_3d = triangulator.triangulate(matches) if len(matches) >= 3 else np.empty((0, 3))
    if len(points_3d) == 0:
        print("[WARN] No valid 3D points after triangulation.")
    results = []
    for cluster in cluster_targets(points_3d, config["target"]["cluster_eps_m"], config["target"]["cluster_min_samples"]):
        if len(cluster) < int(config["target"]["min_points_for_pose"]):
            print(f"[WARN] Only {len(cluster)} 3D points in cluster, pose quality may be low.")
        template_match = match_current_points(cluster, database.targets(), config.get("target_matching", {}))
        if template_match.target_id == "unknown":
            target_id, id_conf = identifier.identify(cluster)
            position, quat, quality = estimate_target_pose(cluster, config["target"]["max_plane_rmse_m"])
            match_confidence = 0.0
        else:
            target_id, id_conf = template_match.target_id, template_match.confidence
            position, quat, quality = estimate_pose_with_fallback(
                template_match.matched_template_points,
                template_match.matched_measured_points,
                config["target"]["max_plane_rmse_m"],
            )
            match_confidence = template_match.confidence
        pose_rmse = quality.get("pose_rmse_m")
        confidence = compute_confidence(
            valid_depth_points=len(cluster),
            num_dots=max(len(left_circles), 1),
            match_error_m=template_match.match_error_m,
            plane_rmse_m=quality.get("plane_rmse_m", template_match.plane_rmse_m),
            pose_rmse_m=pose_rmse,
        )
        status = "unknown" if template_match.target_id == "unknown" else confidence_status(confidence)
        quality.update({
            "num_dots": int(len(left_circles)),
            "valid_depth_points": int(len(cluster)),
            "num_matches": int(len(matches)),
            "id_confidence": float(id_conf),
            "match_confidence": float(match_confidence),
            "match_error_m": template_match.match_error_m,
            "confidence": float(confidence),
            "status": status,
        })
        result = TargetPoseResult(now_timestamp(), target_id, "camera_left", position.tolist(), quat.tolist(), cluster.tolist(), quality)
        publisher.publish(result)
        results.append(result)
    vis = draw_matches(left_rect, right_rect, left_circles, right_circles, matches)
    if save_visualization:
        out_dir = Path(config["paths"]["output_image_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"matches_{filename_timestamp()}.png"
        cv2.imwrite(str(out_path), vis)
        print(f"[INFO] Visualization saved: {out_path}")
    return results, vis, points_3d
