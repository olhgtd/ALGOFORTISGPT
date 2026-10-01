from dataclasses import dataclass
@dataclass(frozen=True,slots=True)
class ProductOpsHealth:
    unresolved_incidents:int; alert_health:str; privacy_requests:tuple[tuple[str,int],...]; stale_policy_count:int; backup_status:str; restore_status:str; rollback_status:str; active_policy_versions:tuple[str,...]
@dataclass(frozen=True,slots=True)
class UserPrivacyReadModel:
    notice_policy_ref:str; notice_fingerprint:str; consent_state:str; request_statuses:tuple[tuple[str,str],...]

def build_health(*, incidents:int, alert_health:str, request_counts:dict[str,int], stale_policy_count:int, backup_status:str, restore_status:str, rollback_status:str, active_policy_versions:tuple[str,...])->ProductOpsHealth:
    return ProductOpsHealth(incidents,alert_health,tuple(sorted(request_counts.items())),stale_policy_count,backup_status,restore_status,rollback_status,tuple(sorted(active_policy_versions)))
