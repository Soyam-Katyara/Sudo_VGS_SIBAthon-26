"""
Pydantic Models for Wedding Expense Tracker
Ensures consistent input/output when working with Gemini API and MongoDB.
"""

from pydantic import BaseModel, Field
from typing import Optional


# ──────────────────────── Chat Models ────────────────────────

class ChatRequest(BaseModel):
    """Input model for chat messages sent to the AI agent."""
    message: str = Field(..., description="User's message to the AI agent")
    group_id: Optional[str] = Field(None, description="Current group ID if user is in a group")
    username: Optional[str] = Field(None, description="Current username if known")
    chat_history: list[dict] = Field(default_factory=list, description="Previous chat messages for context")


class ChatResponse(BaseModel):
    """Output model for AI agent responses."""
    reply: str = Field(..., description="AI agent's reply to the user")
    action: Optional[str] = Field(None, description="Action performed: create_group, join_group, add_expense, summary, none")
    group_id: Optional[str] = Field(None, description="Group ID if a group was created or joined")
    username: Optional[str] = Field(None, description="Username if identified")
    expense_data: Optional[dict] = Field(None, description="Expense data if an expense action was taken")


# ──────────────────────── Group Models ────────────────────────

class GroupCreate(BaseModel):
    """Model for creating a new wedding group."""
    username: str = Field(..., description="Username of the group creator")


class GroupJoin(BaseModel):
    """Model for joining an existing wedding group."""
    group_id: str = Field(..., min_length=9, max_length=9, description="9-character group ID")
    username: str = Field(..., description="Username of the person joining")


class GroupResponse(BaseModel):
    """Response model for group operations."""
    group_id: str
    message: str
    members: list[dict] = Field(default_factory=list)


# ──────────────────────── Expense Models ────────────────────────

class ExpenseAdd(BaseModel):
    """Model for adding an expense."""
    group_id: str = Field(..., description="Group ID to add expense to")
    username: str = Field(..., description="Username of the person who made the expense")
    expense_name: str = Field(..., description="Name/description of the expense")
    amount: int = Field(..., gt=0, description="Amount in rupees")
    category: str = Field(..., description="Category of the expense")


class ExpenseResponse(BaseModel):
    """Response model for expense operations."""
    message: str
    expense: Optional[dict] = None


# ──────────────────────── Summary Models ────────────────────────

class SummaryRequest(BaseModel):
    """Model for requesting expense summaries."""
    group_id: str = Field(..., description="Group ID to get summary for")
    summary_type: str = Field(..., description="Type: person, category, overall, custom")
    filter_value: Optional[str] = Field(None, description="Username or category name for filtered summaries")


class SummaryResponse(BaseModel):
    """Response model for summaries."""
    summary_type: str
    total: int = 0
    count: int = 0
    breakdown: list[dict] = Field(default_factory=list)
    message: str = ""
