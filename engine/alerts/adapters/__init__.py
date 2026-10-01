"""Phase-5 alert delivery adapters."""

from engine.alerts.adapters.telegram import TelegramAlertAdapter
from engine.alerts.adapters.windows_local import WindowsLocalAlertAdapter

__all__ = ["TelegramAlertAdapter", "WindowsLocalAlertAdapter"]
