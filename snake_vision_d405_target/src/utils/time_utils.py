from datetime import datetime
import time

def now_timestamp():
    return time.time()

def filename_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
