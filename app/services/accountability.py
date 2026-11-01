def operator_id(db, user_id):
    return db.info.get("admin_action", {}).get("admin_id", user_id)

def audit_details(db, details=None):
    return {**(details or {}), **{key: str(value) for key, value in db.info.get("admin_action", {}).items()}}
