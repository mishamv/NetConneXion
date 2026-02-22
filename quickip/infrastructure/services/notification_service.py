import logging
from typing import Literal
try:
    from plyer import notification
except ImportError:
    notification = None

from quickip.domain.interfaces import INotificationService

class ToastNotificationService(INotificationService):
    def __init__(self, app_name: str = "Quick IP Change"):
        self.app_name = app_name
        self.logger = logging.getLogger(__name__)

    def show(self, title: str, message: str, level: Literal['info', 'warning', 'error'] = 'info') -> None:
        self.logger.info(f"Notification [{level}]: {title} - {message}")
        if notification:
            try:
                notification.notify(
                    title=f"{title}",
                    message=message,
                    app_name=self.app_name,
                    timeout=5
                )
            except Exception as e:
                self.logger.error(f"Failed to show notification: {e}")
        else:
            self.logger.warning("Plyer not installed, notification skipped.")
