import cv2

def show_image(window_name, image, wait_ms=1):
    cv2.imshow(window_name, image)
    return cv2.waitKey(wait_ms) & 0xFF
