import os
import json
import base64
import threading
from datetime import datetime, timezone
import requests

from location_map import account_location_map as BASE_LOCATIONS

STORE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "location_overrides.json"
)

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
GITHUB_FILE_PATH = os.environ.get("GITHUB_FILE_PATH", "location_overrides.json")
IS_RENDER = os.environ.get("RENDER") == "false"

_lock = threading.RLock()
# _data structure:
# {
#   "additions": { "account": {"location": "...", "kind": "new"|"edited"} },
#   "deletions": ["account_hidden_from_base"],
#   "history":   [ {old_account, old_location, new_account, new_location, edited_at} ]
# }
_data = {"additions": {}, "deletions": [], "history": []}


def github_sync_enabled():
    return IS_RENDER and bool(GITHUB_TOKEN and GITHUB_REPO)


def _github_headers():
    return {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}


def _empty():
    return {"additions": {}, "deletions": [], "history": []}


def _load_local():
    global _data
    if os.path.exists(STORE_FILE):
        try:
            with open(STORE_FILE, "r", encoding="utf-8") as f:
                _data = json.load(f)
        except Exception:
            _data = _empty()
    else:
        _data = _empty()


def _save_local():
    tmp_path = STORE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, STORE_FILE)


def _github_pull():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    try:
        resp = requests.get(url, headers=_github_headers(), params={"ref": GITHUB_BRANCH}, timeout=(3, 6))
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
        elif resp.status_code == 404:
            return _empty(), None
        else:
            return None, None
    except Exception:
        return None, None


def _github_push(new_data, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
    content_str = json.dumps(new_data, indent=2, ensure_ascii=False)
    payload = {
        "message": "Update account/location mappings via app UI",
        "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        resp = requests.put(url, headers=_github_headers(), json=payload, timeout=(3, 6))
        return resp.status_code in (200, 201)
    except Exception:
        return False


def init_store():
    global _data
    with _lock:
        if github_sync_enabled():
            remote, _sha = _github_pull()
            if remote is not None:
                _data = remote
                try:
                    _save_local()
                except Exception:
                    pass
                return
        _load_local()


def _persist(new_data):
    """Push to GitHub if configured, else save locally. Returns (ok, err_msg)."""
    if github_sync_enabled():
        remote, sha = _github_pull()
        if remote is None:
            return False, "Could not reach GitHub. Nothing was saved."
        if not _github_push(new_data, sha):
            return False, "Failed to save to GitHub. Nothing was changed."
        global _data
        _data = new_data
        try:
            _save_local()
        except Exception:
            pass
        return True, None
    else:
        try:
            old = _data
            _data = new_data
            _save_local()
            return True, None
        except Exception as e:
            _data = old
            return False, f"Failed to save locally: {e}"


def get_full_map():
    """Plain account -> location dict, for use by processor.py."""
    with _lock:
        merged = {k: v for k, v in BASE_LOCATIONS.items() if k not in _data.get("deletions", [])}
        for acct, info in _data.get("additions", {}).items():
            merged[acct] = info["location"]
        return merged


def get_current_rows(search_text=""):
    """Rows for the UI table: (account, location, status)."""
    with _lock:
        rows = []
        for acct, loc in BASE_LOCATIONS.items():
            if acct not in _data.get("deletions", []):
                rows.append((acct, loc, "Base"))
        for acct, info in _data.get("additions", {}).items():
            status = "🆕 New" if info["kind"] == "new" else "✏️ Edited"
            rows.append((acct, info["location"], status))
        rows.sort(key=lambda r: r[0])
        if search_text:
            s = search_text.strip().lower()
            rows = [r for r in rows if s in r[0].lower() or s in r[1].lower()]
        return rows


def get_history_rows():
    with _lock:
        rows = [
            (h["old_account"], h["old_location"], h["new_account"], h["new_location"], h["edited_at"])
            for h in reversed(_data.get("history", []))
        ]
        return rows


def add_mapping(account, location):
    account = (account or "").strip()
    location = (location or "").strip()
    if not account:
        return False, "Account number cannot be empty."
    if not account.isdigit():
        return False, "Account number must contain digits only."
    if not location:
        return False, "Location name cannot be empty."

    with _lock:
        merged = get_full_map()
        if account in merged:
            return False, f"Account {account} already exists → '{merged[account]}'. Nothing changed."

        new_data = json.loads(json.dumps(_data))  # deep copy
        new_data["additions"][account] = {"location": location, "kind": "new"}
        ok, err = _persist(new_data)
        if not ok:
            return False, err
        return True, f"Added {account} → '{location}'."


def edit_mapping(old_account, new_account, new_location):
    old_account = (old_account or "").strip()
    new_account = (new_account or "").strip()
    new_location = (new_location or "").strip()

    if not new_account:
        return False, "Account number cannot be empty."
    if not new_account.isdigit():
        return False, "Account number must contain digits only."
    if not new_location:
        return False, "Location name cannot be empty."

    with _lock:
        merged = get_full_map()
        if old_account not in merged:
            return False, f"Account {old_account} was not found (may have already been changed)."

        old_location = merged[old_account]

        if new_account != old_account and new_account in merged:
            return False, f"Account {new_account} already exists → '{merged[new_account]}'. Choose a different number."

        new_data = json.loads(json.dumps(_data))

        if old_account in new_data["additions"]:
            del new_data["additions"][old_account]
        else:
            if old_account not in new_data["deletions"]:
                new_data["deletions"].append(old_account)

        new_data["additions"][new_account] = {"location": new_location, "kind": "edited"}
        new_data["history"].append({
            "old_account": old_account,
            "old_location": old_location,
            "new_account": new_account,
            "new_location": new_location,
            "edited_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        })

        ok, err = _persist(new_data)
        if not ok:
            return False, err
        return True, f"Updated {old_account} → {new_account} ('{new_location}')."


def delete_mapping(account):
    account = (account or "").strip()
    with _lock:
        if account not in _data.get("additions", {}):
            return False, "Only entries added or edited via the UI can be deleted. Base entries are protected."

        new_data = json.loads(json.dumps(_data))
        del new_data["additions"][account]
        ok, err = _persist(new_data)
        if not ok:
            return False, err
        return True, f"Deleted {account}."