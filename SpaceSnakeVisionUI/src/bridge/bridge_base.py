class BridgeBase:
    def publish_command(self, command):
        raise NotImplementedError

    def poll_status(self):
        return []
