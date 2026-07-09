import numpy as np

def cluster_targets(points_3d, eps_m=0.08, min_samples=4):
    points_3d = np.asarray(points_3d, dtype=float)
    if len(points_3d) == 0:
        return []
    if len(points_3d) <= 12:
        return [points_3d]
    from sklearn.cluster import DBSCAN
    labels = DBSCAN(eps=eps_m, min_samples=min_samples).fit_predict(points_3d)
    return [points_3d[labels == lab] for lab in sorted(set(labels)) if lab != -1 and (labels == lab).sum() >= min_samples]
