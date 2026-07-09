import cv2

def load_gray_pair(left_path, right_path):
    left = cv2.imread(str(left_path), cv2.IMREAD_GRAYSCALE)
    right = cv2.imread(str(right_path), cv2.IMREAD_GRAYSCALE)
    if left is None:
        raise FileNotFoundError(f"Cannot read left image: {left_path}")
    if right is None:
        raise FileNotFoundError(f"Cannot read right image: {right_path}")
    return left, right
