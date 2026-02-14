"""
Local file-based storage for Wedding Expense Tracker.
Uses a single JSON file (no MongoDB). Data persists across server restarts.
"""

import json
import threading
from pathlib import Path
from datetime import datetime, timezone

# Data file next to this module
_DATA_DIR = Path(__file__).resolve().parent
DATA_FILE = _DATA_DIR / "data.json"

# In-memory storage (loaded from / saved to JSON)
_lock = threading.RLock()
_groups: list[dict] = []
_members: list[dict] = []
_expenses: list[dict] = []


def _serialize_dt(dt: datetime) -> str:
    return dt.isoformat()


def _deserialize_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _load_data() -> None:
    """Load groups, members, expenses from JSON file."""
    global _groups, _members, _expenses
    with _lock:
        if not DATA_FILE.exists():
            _groups, _members, _expenses = [], [], []
            return
        try:
            raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            _groups = raw.get("groups", [])
            _members = raw.get("members", [])
            _expenses = raw.get("expenses", [])
            # Normalize datetime fields where used
            for g in _groups:
                if isinstance(g.get("created_at"), str):
                    g["created_at"] = _deserialize_dt(g["created_at"])
            for m in _members:
                if isinstance(m.get("joined_at"), str):
                    m["joined_at"] = _deserialize_dt(m["joined_at"])
            for e in _expenses:
                if isinstance(e.get("created_at"), str):
                    e["created_at"] = _deserialize_dt(e["created_at"])
        except (json.JSONDecodeError, OSError):
            _groups, _members, _expenses = [], [], []


def _save_data() -> None:
    """Persist current in-memory data to JSON file."""
    with _lock:
        out = {
            "groups": [
                {**g, "created_at": _serialize_dt(g["created_at"]) if isinstance(g.get("created_at"), datetime) else g.get("created_at")}
                for g in _groups
            ],
            "members": [
                {**m, "joined_at": _serialize_dt(m["joined_at"]) if isinstance(m.get("joined_at"), datetime) else m.get("joined_at")}
                for m in _members
            ],
            "expenses": [
                {
                    **e,
                    "created_at": _serialize_dt(e["created_at"]) if isinstance(e.get("created_at"), datetime) else e.get("created_at"),
                }
                for e in _expenses
            ],
        }
        DATA_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")


# Load on first import
_load_data()


# ──────────────────────── Group Operations ────────────────────────

def create_group(group_id: str, creator_username: str) -> dict:
    """Create a new wedding group and add the creator as the first member."""
    now = datetime.now(timezone.utc)
    group_doc = {
        "group_id": group_id,
        "created_by": creator_username,
        "created_at": now,
    }
    with _lock:
        _groups.append(group_doc)
        add_member(group_id, creator_username)
        _save_data()
    return group_doc


def group_exists(group_id: str) -> bool:
    """Check if a group exists."""
    return any(g["group_id"] == group_id for g in _groups)


# ──────────────────────── Member Operations ────────────────────────

def add_member(group_id: str, username: str) -> dict:
    """Add a member to a wedding group."""
    with _lock:
        group_members = [m for m in _members if m["group_id"] == group_id]
        last_member = max(group_members, key=lambda m: m["user_id"], default=None)
        next_user_id = (last_member["user_id"] + 1) if last_member else 1

        now = datetime.now(timezone.utc)
        member_doc = {
            "group_id": group_id,
            "user_id": next_user_id,
            "username": username,
            "joined_at": now,
        }
        _members.append(member_doc)
        _save_data()
    return member_doc


def member_exists(group_id: str, username: str) -> bool:
    """Check if a member already exists in a group."""
    return any(
        m["group_id"] == group_id and m["username"] == username
        for m in _members
    )


def get_member(group_id: str, username: str) -> dict | None:
    """Get a member document."""
    for m in _members:
        if m["group_id"] == group_id and m["username"] == username:
            return dict(m)
    return None


def get_members(group_id: str) -> list[dict]:
    """Get all members of a group (without internal _id)."""
    return [{"group_id": m["group_id"], "user_id": m["user_id"], "username": m["username"], "joined_at": m["joined_at"]} for m in _members if m["group_id"] == group_id]


# ──────────────────────── Expense Operations ────────────────────────

def add_expense(
    group_id: str,
    user_id: int,
    username: str,
    expense_name: str,
    amount: int,
    category: str,
) -> dict:
    """Add an expense to a group."""
    now = datetime.now(timezone.utc)
    expense_doc = {
        "group_id": group_id,
        "user_id": user_id,
        "username": username,
        "expense_name": expense_name,
        "amount": amount,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "category": category,
        "created_at": now,
    }
    with _lock:
        _expenses.append(expense_doc)
        _save_data()
    return expense_doc


def get_expenses(group_id: str) -> list[dict]:
    """Get all expenses for a group."""
    return [
        {"group_id": e["group_id"], "user_id": e["user_id"], "username": e["username"], "expense_name": e["expense_name"], "amount": e["amount"], "date": e["date"], "time": e["time"], "category": e["category"]}
        for e in _expenses
        if e["group_id"] == group_id
    ]


def get_expenses_by_user(group_id: str, username: str) -> list[dict]:
    """Get expenses for a specific user in a group."""
    return [
        {"group_id": e["group_id"], "user_id": e["user_id"], "username": e["username"], "expense_name": e["expense_name"], "amount": e["amount"], "date": e["date"], "time": e["time"], "category": e["category"]}
        for e in _expenses
        if e["group_id"] == group_id and e["username"] == username
    ]


def get_expenses_by_category(group_id: str, category: str) -> list[dict]:
    """Get expenses by category in a group (case-insensitive match)."""
    cat_lower = category.lower()
    return [
        {"group_id": e["group_id"], "user_id": e["user_id"], "username": e["username"], "expense_name": e["expense_name"], "amount": e["amount"], "date": e["date"], "time": e["time"], "category": e["category"]}
        for e in _expenses
        if e["group_id"] == group_id and cat_lower in e["category"].lower()
    ]


def get_expense_summary(group_id: str) -> dict:
    """Get overall expense summary for a group."""
    group_expenses = [e for e in _expenses if e["group_id"] == group_id]
    total = sum(e["amount"] for e in group_expenses)
    return {"total": total, "count": len(group_expenses)}


def get_category_summary(group_id: str) -> list[dict]:
    """Get expense summary grouped by category."""
    group_expenses = [e for e in _expenses if e["group_id"] == group_id]
    by_cat: dict[str, list] = {}
    for e in group_expenses:
        c = e["category"]
        if c not in by_cat:
            by_cat[c] = []
        by_cat[c].append(e)
    result = [
        {"_id": cat, "total": sum(x["amount"] for x in items), "count": len(items)}
        for cat, items in by_cat.items()
    ]
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


def get_member_summary(group_id: str) -> list[dict]:
    """Get expense summary grouped by member."""
    group_expenses = [e for e in _expenses if e["group_id"] == group_id]
    by_user: dict[str, list] = {}
    for e in group_expenses:
        u = e["username"]
        if u not in by_user:
            by_user[u] = []
        by_user[u].append(e)
    result = [
        {"_id": user, "total": sum(x["amount"] for x in items), "count": len(items)}
        for user, items in by_user.items()
    ]
    result.sort(key=lambda x: x["total"], reverse=True)
    return result
