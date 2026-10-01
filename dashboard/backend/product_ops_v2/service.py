from __future__ import annotations
from .read_models import ProductOpsHealth, UserPrivacyReadModel
class ProductOpsService:
    """Thin service facade. No database, broker, Live, risk-mint or AI execution authority."""
    def __init__(self, repository): self._repo=repository
    def owner_health(self, *, health:ProductOpsHealth)->ProductOpsHealth: return health
    def user_privacy(self, *, principal_ref:str, model:UserPrivacyReadModel, requested_principal_ref:str)->UserPrivacyReadModel:
        if principal_ref!=requested_principal_ref: raise PermissionError('CROSS_USER_READ_DENIED')
        return model
