from src.interface.command_schema import command_to_json

class DummyControlClient:
    def send_command(self, command):
        print("[DUMMY CONTROL]")
        print(command_to_json(command))
