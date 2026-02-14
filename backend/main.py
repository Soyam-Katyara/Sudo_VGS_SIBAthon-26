"""
FastAPI Main Server for Wedding Expense Tracker.
Provides REST API endpoints for the React frontend.
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from models import (
    ChatRequest,
    ChatResponse,
    ExpenseAdd,
    ExpenseResponse,
    GroupCreate,
    GroupJoin,
    SummaryRequest,
    SummaryResponse,
)
import database as db
from agent import chat_with_agent, generate_group_id

load_dotenv()

app = FastAPI(
    title="Wedding Expense Tracker API",
    description="AI-powered wedding expense tracking with Gemini",
    version="1.0.0",
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────── Health Check ────────────────────────

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Wedding Expense Tracker API is running 🎉"}


# ──────────────────────── Chat Endpoint ────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Send a message to the AI agent and get a response."""
    try:
        result = chat_with_agent(
            user_message=request.message,
            group_id=request.group_id,
            username=request.username,
            chat_history=request.chat_history,
        )
        return ChatResponse(
            reply=result["reply"],
            action=result.get("action"),
            group_id=result.get("group_id"),
            username=result.get("username"),
            expense_data=result.get("expense_data"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────── Group Endpoints ────────────────────────

@app.post("/api/group")
def create_group_direct(body: GroupCreate):
    """Create a new group directly (no AI). Returns group_id and username."""
    group_id = generate_group_id()
    db.create_group(group_id, body.username.strip())
    return {"group_id": group_id, "username": body.username.strip()}


@app.post("/api/group/join")
def join_group_direct(body: GroupJoin):
    """Join an existing group directly (no AI). Returns group_id and username."""
    gid = body.group_id.strip().upper()
    if len(gid) != 9:
        raise HTTPException(status_code=400, detail="Group ID must be 9 characters")
    if not db.group_exists(gid):
        raise HTTPException(status_code=404, detail="Invalid Group ID. Please check and try again.")
    username = body.username.strip()
    if db.member_exists(gid, username):
        return {"group_id": gid, "username": username, "message": "Already a member"}
    db.add_member(gid, username)
    return {"group_id": gid, "username": username, "message": "Joined successfully"}


@app.get("/api/group/{group_id}/exists")
def check_group(group_id: str):
    """Check if a group exists."""
    exists = db.group_exists(group_id)
    return {"exists": exists, "group_id": group_id}


@app.get("/api/group/{group_id}/members")
def get_members(group_id: str):
    """Get all members of a group."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    members = db.get_members(group_id)
    return {"group_id": group_id, "members": members}


# ──────────────────────── Expense Endpoints ────────────────────────

@app.post("/api/expense", response_model=ExpenseResponse)
def add_expense(expense: ExpenseAdd):
    """Add an expense directly (bypass AI agent)."""
    if not db.group_exists(expense.group_id):
        raise HTTPException(status_code=404, detail="Group not found")

    member = db.get_member(expense.group_id, expense.username)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found in this group")

    result = db.add_expense(
        group_id=expense.group_id,
        user_id=member["user_id"],
        username=expense.username,
        expense_name=expense.expense_name,
        amount=expense.amount,
        category=expense.category,
    )
    return ExpenseResponse(
        message="Expense added successfully! ✅",
        expense={
            "expense_name": result["expense_name"],
            "amount": result["amount"],
            "category": result["category"],
            "date": result["date"],
            "time": result["time"],
        },
    )


@app.get("/api/group/{group_id}/expenses")
def get_expenses(group_id: str):
    """Get all expenses for a group."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    expenses = db.get_expenses(group_id)
    return {"group_id": group_id, "expenses": expenses}


@app.get("/api/group/{group_id}/expenses/{username}")
def get_user_expenses(group_id: str, username: str):
    """Get expenses for a specific user in a group."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    expenses = db.get_expenses_by_user(group_id, username)
    total = sum(e["amount"] for e in expenses)
    return {
        "group_id": group_id,
        "username": username,
        "expenses": expenses,
        "total": total,
        "count": len(expenses),
    }


# ──────────────────────── Summary Endpoints ────────────────────────

@app.get("/api/group/{group_id}/summary")
def get_overall_summary(group_id: str):
    """Get overall expense summary for a group."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    summary = db.get_expense_summary(group_id)
    return {"group_id": group_id, **summary}


@app.get("/api/group/{group_id}/summary/categories")
def get_category_summary(group_id: str):
    """Get expense summary grouped by category."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    categories = db.get_category_summary(group_id)
    result = [{"category": c["_id"], "total": c["total"], "count": c["count"]} for c in categories]
    return {"group_id": group_id, "categories": result}


@app.get("/api/group/{group_id}/summary/members")
def get_member_summary(group_id: str):
    """Get expense summary grouped by member."""
    if not db.group_exists(group_id):
        raise HTTPException(status_code=404, detail="Group not found")
    members = db.get_member_summary(group_id)
    result = [{"username": m["_id"], "total": m["total"], "count": m["count"]} for m in members]
    return {"group_id": group_id, "members": result}


# ──────────────────────── Run Server ────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
