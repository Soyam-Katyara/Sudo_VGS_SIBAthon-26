"""
Gemini AI Agent for Wedding Expense Tracker.
Handles communication with Gemini API and processes agent actions.
"""

import os
import json
import re
import string
import random
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from prompt import SYSTEM_PROMPT
import database as db

# Load .env from the same directory as this file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# ──────────────────────── Gemini Client Setup ────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    raise ValueError(
        "GEMINI_API_KEY not set! Edit the .env file at:\n"
        f"  {env_path}\n"
        "and replace 'your_gemini_api_key_here' with your actual Gemini API key."
    )

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash-lite"


# ──────────────────────── Helper Functions ────────────────────────

def generate_group_id() -> str:
    """Generate a random 9-character uppercase letter group ID."""
    return "".join(random.choices(string.ascii_uppercase, k=9))


def extract_json_from_response(text: str) -> dict | None:
    """Extract JSON action block from the agent's response text."""
    # Look for ```json ... ``` blocks
    json_match = re.search(r"```json\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            return None
    return None


def clean_response_text(text: str) -> str:
    """Remove JSON code blocks from the response text for display."""
    cleaned = re.sub(r"```json\s*\n?.*?\n?\s*```", "", text, flags=re.DOTALL).strip()
    return cleaned


def build_context_message(group_id: str | None, username: str | None) -> str:
    """Build context information to append to the user message."""
    context_parts = []
    if group_id:
        context_parts.append(f"[Current Group ID: {group_id}]")
        # Fetch group members for context
        members = db.get_members(group_id)
        if members:
            member_names = [m["username"] for m in members]
            context_parts.append(f"[Group Members: {', '.join(member_names)}]")
    if username:
        context_parts.append(f"[Current Username: {username}]")
    return "\n".join(context_parts)


# ──────────────────────── Main Agent Function ────────────────────────

def chat_with_agent(
    user_message: str,
    group_id: str | None = None,
    username: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """
    Send a message to the Gemini AI agent and process the response.

    Returns:
        dict with keys: reply, action, group_id, username, expense_data
    """
    if chat_history is None:
        chat_history = []

    # Build the conversation messages for Gemini
    contents = []

    # Add chat history
    for msg in chat_history:
        role = msg.get("role", "user")
        text = msg.get("text", "")
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        else:
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))

    # Build the current message with context and language reminder
    context = build_context_message(group_id, username)
    full_message = f"{context}\n\nUser message: {user_message}" if context else user_message
    full_message += "\n\n[Reply in the SAME language as the user's message above: English → English, Roman Urdu → Roman Urdu.]"

    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=full_message)]))

    # Call Gemini API
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    raw_text = response.text
    action_data = extract_json_from_response(raw_text)
    display_text = clean_response_text(raw_text)

    # Process the action
    result = {
        "reply": display_text,
        "action": None,
        "group_id": group_id,
        "username": username,
        "expense_data": None,
    }

    if action_data:
        action = action_data.get("action")
        result["action"] = action

        if action == "create_group":
            new_group_id = generate_group_id()
            creator = action_data.get("username", username)
            db.create_group(new_group_id, creator)
            result["group_id"] = new_group_id
            result["username"] = creator
            result["reply"] = display_text + f"\n\nYour Group ID is: **{new_group_id}**\nShare this ID with other members so they can join! 🎊"

        elif action == "join_group":
            join_gid = action_data.get("group_id", "")
            joiner = action_data.get("username", username)

            if not db.group_exists(join_gid):
                result["reply"] = "This Group ID is invalid. Please check and try again. ❌"
                result["action"] = "invalid_group"
            elif db.member_exists(join_gid, joiner):
                result["reply"] = f"{joiner} is already a member of group {join_gid}. ✅"
                result["group_id"] = join_gid
                result["username"] = joiner
            else:
                db.add_member(join_gid, joiner)
                result["group_id"] = join_gid
                result["username"] = joiner
                members = db.get_members(join_gid)
                member_names = [m["username"] for m in members]
                result["reply"] = display_text + f"\n\nWelcome to the group, {joiner}! 🎉\nCurrent members: {', '.join(member_names)}"

        elif action == "add_expense":
            if group_id and username:
                expense_name = action_data.get("expense_name", "")
                amount = action_data.get("amount", 0)
                category = action_data.get("category", "Other")

                member = db.get_member(group_id, username)
                if member:
                    expense = db.add_expense(
                        group_id=group_id,
                        user_id=member["user_id"],
                        username=username,
                        expense_name=expense_name,
                        amount=amount,
                        category=category,
                    )
                    result["expense_data"] = {
                        "expense_name": expense_name,
                        "amount": amount,
                        "category": category,
                    }
            else:
                result["reply"] = "Please join or create a group first before adding expenses."
                result["action"] = "error"

        elif action == "get_summary":
            if group_id:
                summary_type = action_data.get("summary_type", "overall")
                filter_value = action_data.get("filter_value")

                if summary_type == "overall":
                    summary = db.get_expense_summary(group_id)
                    expenses = db.get_expenses(group_id)
                    summary_text = f"\n\n📊 **Overall Summary**\nTotal Expenses: {summary['count']}\nTotal Amount: {summary['total']}rs\n"
                    if expenses:
                        summary_text += "\nDetails:\n"
                        for e in expenses:
                            summary_text += f"• {e['expense_name']} - {e['amount']}rs ({e['category']}) by {e['username']}\n"
                    result["reply"] = display_text + summary_text

                elif summary_type == "person":
                    if filter_value:
                        expenses = db.get_expenses_by_user(group_id, filter_value)
                        total = sum(e["amount"] for e in expenses)
                        summary_text = f"\n\n👤 **{filter_value}'s Expenses**\nTotal: {total}rs ({len(expenses)} expenses)\n"
                        for e in expenses:
                            summary_text += f"• {e['expense_name']} - {e['amount']}rs ({e['category']})\n"
                        result["reply"] = display_text + summary_text

                elif summary_type == "category":
                    if filter_value:
                        expenses = db.get_expenses_by_category(group_id, filter_value)
                        total = sum(e["amount"] for e in expenses)
                        summary_text = f"\n\n📁 **{filter_value} Expenses**\nTotal: {total}rs ({len(expenses)} expenses)\n"
                        for e in expenses:
                            summary_text += f"• {e['expense_name']} - {e['amount']}rs by {e['username']}\n"
                        result["reply"] = display_text + summary_text

                elif summary_type == "custom":
                    # For custom, send expenses data back to Gemini for analysis
                    expenses = db.get_expenses(group_id)
                    if expenses:
                        expenses_json = json.dumps(expenses, default=str)
                        custom_prompt = f"Based on the following expenses data, answer the user's query: '{user_message}'\n\nExpenses data:\n{expenses_json}"
                        custom_response = client.models.generate_content(
                            model=MODEL_NAME,
                            contents=[types.Content(role="user", parts=[types.Part.from_text(text=custom_prompt)])],
                            config=types.GenerateContentConfig(
                                system_instruction="You are a wedding expense analyst. Analyze the provided expense data and answer the user's query concisely. Only talk about wedding expenses. If the question is unrelated to wedding expenses, say 'I can't help with that.'",
                                temperature=0.3,
                                max_output_tokens=1024,
                            ),
                        )
                        result["reply"] = custom_response.text
            else:
                result["reply"] = "Please join or create a group first to view summaries."
                result["action"] = "error"

    return result
