"""Pure fail-closed data licensing policy for AlgoFortis Data V2.

The legacy acquisition/use decision is preserved. External/provider processing is
an additive, separately fingerprinted decision so Phase-8 cloud egress cannot
silently change Phase-3 semantics.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from engine.reproducibility.codec import CanonicalCodec

class DataLicenceError(ValueError): pass

class AcquisitionPermission(str, Enum):
    ALLOWED="ALLOWED"; PROHIBITED="PROHIBITED"; UNKNOWN="UNKNOWN"

class ExternalProcessingPermission(str, Enum):
    ALLOWED="ALLOWED"; PROHIBITED="PROHIBITED"; UNKNOWN="UNKNOWN"

class DataUse(str, Enum):
    RESEARCH="RESEARCH"; BACKTEST="BACKTEST"; PROMOTION="PROMOTION"

class DataLicenceReason(str, Enum):
    ACQUISITION_PERMISSION_MISSING="ACQUISITION_PERMISSION_MISSING"
    ACQUISITION_PERMISSION_UNKNOWN="ACQUISITION_PERMISSION_UNKNOWN"
    ACQUISITION_PROHIBITED="ACQUISITION_PROHIBITED"
    NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED="NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED"
    USE_NOT_PERMITTED="USE_NOT_PERMITTED"
    SYNTHETIC_NOT_PROMOTION_EVIDENCE="SYNTHETIC_NOT_PROMOTION_EVIDENCE"

class ExternalProcessingReason(str, Enum):
    EXTERNAL_PROCESSING_PERMISSION_MISSING="EXTERNAL_PROCESSING_PERMISSION_MISSING"
    EXTERNAL_PROCESSING_PERMISSION_UNKNOWN="EXTERNAL_PROCESSING_PERMISSION_UNKNOWN"
    EXTERNAL_PROCESSING_PROHIBITED="EXTERNAL_PROCESSING_PROHIBITED"
    USE_NOT_PERMITTED="USE_NOT_PERMITTED"


def _text(value:str,name:str)->str:
    if not isinstance(value,str) or not value.strip(): raise DataLicenceError(f"{name} must be non-empty")
    return value.strip()

@dataclass(frozen=True,slots=True)
class DataLicenceMetadata:
    source_id:str
    licence_ref:str
    acquisition_permission:AcquisitionPermission|None
    permitted_uses:tuple[DataUse,...]
    synthetic:bool=False
    external_processing_permission:ExternalProcessingPermission|None=ExternalProcessingPermission.UNKNOWN
    def __post_init__(self):
        object.__setattr__(self,"source_id",_text(self.source_id,"source_id"))
        object.__setattr__(self,"licence_ref",_text(self.licence_ref,"licence_ref"))
        if self.acquisition_permission is not None and not isinstance(self.acquisition_permission,AcquisitionPermission): raise DataLicenceError("acquisition_permission must be AcquisitionPermission or None")
        if self.external_processing_permission is not None and not isinstance(self.external_processing_permission,ExternalProcessingPermission): raise DataLicenceError("external_processing_permission must be ExternalProcessingPermission or None")
        uses=tuple(self.permitted_uses)
        if not uses or any(not isinstance(i,DataUse) for i in uses): raise DataLicenceError("permitted_uses must contain DataUse values")
        if len(set(uses))!=len(uses): raise DataLicenceError("permitted_uses must be unique")
        object.__setattr__(self,"permitted_uses",tuple(sorted(uses,key=lambda i:i.value)))
        if not isinstance(self.synthetic,bool): raise DataLicenceError("synthetic must be bool")

@dataclass(frozen=True,slots=True)
class DataLicenceDecision:
    allowed:bool; reasons:tuple[DataLicenceReason,...]; labels:tuple[str,...]; fingerprint:str

@dataclass(frozen=True,slots=True)
class ExternalProcessingDecision:
    allowed:bool; reasons:tuple[ExternalProcessingReason,...]; fingerprint:str

class DataLicencePolicy:
    def evaluate(self,metadata:DataLicenceMetadata,*,market:str,requested_use:DataUse,programmatic_acquisition:bool)->DataLicenceDecision:
        if not isinstance(metadata,DataLicenceMetadata): raise DataLicenceError("metadata must be DataLicenceMetadata")
        normalized_market=_text(market,"market").upper()
        if not isinstance(requested_use,DataUse): raise DataLicenceError("requested_use must be DataUse")
        if not isinstance(programmatic_acquisition,bool): raise DataLicenceError("programmatic_acquisition must be bool")
        reasons=[]; labels=[]
        if metadata.synthetic:
            labels.append("SYNTHETIC")
            if requested_use is DataUse.PROMOTION: reasons.append(DataLicenceReason.SYNTHETIC_NOT_PROMOTION_EVIDENCE)
        if requested_use not in metadata.permitted_uses: reasons.append(DataLicenceReason.USE_NOT_PERMITTED)
        if programmatic_acquisition:
            if normalized_market=="NSE": reasons.append(DataLicenceReason.NSE_PROGRAMMATIC_ACQUISITION_PROHIBITED)
            p=metadata.acquisition_permission
            if p is None: reasons.append(DataLicenceReason.ACQUISITION_PERMISSION_MISSING)
            elif p is AcquisitionPermission.UNKNOWN: reasons.append(DataLicenceReason.ACQUISITION_PERMISSION_UNKNOWN)
            elif p is AcquisitionPermission.PROHIBITED: reasons.append(DataLicenceReason.ACQUISITION_PROHIBITED)
        nr=tuple(sorted(set(reasons),key=lambda i:i.value)); nl=tuple(sorted(set(labels))); allowed=not nr
        fp=CanonicalCodec.fingerprint("algofortis-data-licence-decision/v1",(("source_id",metadata.source_id),("licence_ref",metadata.licence_ref),("acquisition_permission","" if metadata.acquisition_permission is None else metadata.acquisition_permission.value),("permitted_uses",tuple(i.value for i in metadata.permitted_uses)),("synthetic","true" if metadata.synthetic else "false"),("market",normalized_market),("requested_use",requested_use.value),("programmatic_acquisition","true" if programmatic_acquisition else "false"),("allowed","true" if allowed else "false"),("reasons",tuple(i.value for i in nr)),("labels",nl)))
        return DataLicenceDecision(allowed,nr,nl,fp)

    def evaluate_external_processing(self,metadata:DataLicenceMetadata,*,requested_use:DataUse)->ExternalProcessingDecision:
        if not isinstance(metadata,DataLicenceMetadata): raise DataLicenceError("metadata must be DataLicenceMetadata")
        if not isinstance(requested_use,DataUse): raise DataLicenceError("requested_use must be DataUse")
        reasons=[]
        if requested_use not in metadata.permitted_uses: reasons.append(ExternalProcessingReason.USE_NOT_PERMITTED)
        p=metadata.external_processing_permission
        if p is None: reasons.append(ExternalProcessingReason.EXTERNAL_PROCESSING_PERMISSION_MISSING)
        elif p is ExternalProcessingPermission.UNKNOWN: reasons.append(ExternalProcessingReason.EXTERNAL_PROCESSING_PERMISSION_UNKNOWN)
        elif p is ExternalProcessingPermission.PROHIBITED: reasons.append(ExternalProcessingReason.EXTERNAL_PROCESSING_PROHIBITED)
        nr=tuple(sorted(set(reasons),key=lambda i:i.value)); allowed=not nr
        fp=CanonicalCodec.fingerprint("algofortis-data-external-processing/v1",(("source_id",metadata.source_id),("licence_ref",metadata.licence_ref),("requested_use",requested_use.value),("permitted_uses",tuple(i.value for i in metadata.permitted_uses)),("external_processing_permission","" if p is None else p.value),("allowed","true" if allowed else "false"),("reasons",tuple(i.value for i in nr))))
        return ExternalProcessingDecision(allowed,nr,fp)

__all__=["DataLicenceError","AcquisitionPermission","ExternalProcessingPermission","DataUse","DataLicenceReason","ExternalProcessingReason","DataLicenceMetadata","DataLicenceDecision","ExternalProcessingDecision","DataLicencePolicy"]
