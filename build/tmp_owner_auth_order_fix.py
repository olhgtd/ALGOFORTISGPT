from pathlib import Path

path = Path("dashboard/backend/api.py")
text = path.read_text(encoding="utf-8")

anchor = '''    def owner_session(session=Depends(session_from_header)):
        if session.user.role is not Role.OWNER:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="owner authorization required")
        return session

'''
insert = anchor + '''    def owner_mutable_session(session=Depends(mutable_session)) -> Any:
        if session.user.role is not Role.OWNER or session.user.account_status != AccountAccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="owner role and active account status required")
        return session

'''
if anchor not in text:
    raise SystemExit("owner_session anchor missing")
text = text.replace(anchor, insert, 1)

old = '''    def owner_mutable_session(session=Depends(mutable_session)) -> Any:
        if session.user.role is not Role.OWNER or session.user.account_status != AccountAccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="owner role and active account status required")
        return session

'''
# Remove the later duplicate, not the freshly inserted first occurrence.
first = text.find(old)
second = text.find(old, first + len(old))
if first < 0 or second < 0:
    raise SystemExit("expected duplicate owner_mutable_session blocks not found")
text = text[:second] + text[second + len(old):]

path.write_text(text, encoding="utf-8")
