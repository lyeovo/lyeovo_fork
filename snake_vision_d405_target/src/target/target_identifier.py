class TargetIdentifier:
    def __init__(self, config_path=None):
        self.config_path = config_path

    def identify(self, points_3d):
        return "unknown", 0.0
