"""Deterministic bounded review-summary serialization for audit handoffs."""
from __future__ import annotations
import hashlib, json
from typing import Mapping

MAX_BYTES=100_000

class ExportError(ValueError): pass

def export_review_summary(summary: Mapping[str,object]) -> dict[str,object]:
    if not isinstance(summary,Mapping): raise ExportError("Summary must be a mapping")
    required=("revision","digest","approved","findings")
    if any(k not in summary for k in required): raise ExportError("Missing required fields")
    rev,digest,approved,findings=(summary[k] for k in required)
    if isinstance(rev,bool) or not isinstance(rev,int) or rev<1: raise ExportError("Invalid revision")
    if not isinstance(digest,str) or len(digest)!=64: raise ExportError("Invalid digest")
    if not isinstance(approved,bool): raise ExportError("Decision must be boolean")
    if not isinstance(findings,list) or len(findings)>500 or not all(isinstance(x,str) and len(x)<=500 for x in findings): raise ExportError("Invalid findings")
    envelope={"schema_version":1,"revision":rev,"digest":digest,"approved":approved,"findings":list(findings)}
    payload=json.dumps(envelope,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    if len(payload.encode("utf-8"))>MAX_BYTES: raise ExportError("Summary too large")
    return {"payload":payload,"sha256":hashlib.sha256(payload.encode("utf-8")).hexdigest(),"schema_version":1}
