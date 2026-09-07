"""
app_controller.py — Multi-file test: references UserService and DataProcessor
from sample.py to test cross-file fan_in detection.
"""
from typing import Optional
from sample import UserService, DataProcessor


class AppController:
    """Main application controller that coordinates services."""

    def __init__(self):
        self.user_svc: UserService = UserService(None, None)
        self.processor: DataProcessor = DataProcessor({"version": "2.0"})

    def handle_request(self, user_id: int, data: list) -> dict:
        user = self.user_svc.get_user(user_id)
        if not user:
            return {"error": "User not found"}
        results = self.processor.process_batch(data)
        return {"user": user, "results": results}

    def login(self, username: str, password: str) -> Optional[str]:
        return self.user_svc.authenticate(username, password)
