#!/usr/bin/env python3
# ==============================================================================
# Script: office365_mcp.py
# Description: Custom simulated MCP server for SharePoint, Outlook, and Teams
# ==============================================================================

import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server named "office365"
mcp = FastMCP("office365")

# --- Outlook Tools ---
@mcp.tool()
def outlook_send_email(to: str, subject: str, body: str) -> str:
    """
    Send an email using Outlook.
    
    :param to: Recipient email address.
    :param subject: Email subject.
    :param body: Email body content.
    """
    return f"Email sent to {to} with subject '{subject}' (Simulated Outlook)"

@mcp.tool()
def outlook_list_emails(limit: int = 10) -> list:
    """
    List recent emails from Outlook inbox.
    
    :param limit: Number of emails to retrieve.
    """
    return [
        {"id": "mail-101", "subject": "Project Status Update", "from": "manager@company.com", "body": "Please send the report."},
        {"id": "mail-102", "subject": "Lunch Today?", "from": "colleague@company.com", "body": "Are you free at 12?"}
    ][:limit]

@mcp.tool()
def outlook_create_event(subject: str, start_time: str, end_time: str, location: str = "") -> str:
    """
    Create a new calendar event in Outlook.
    
    :param subject: Title of the calendar event.
    :param start_time: Event start time (ISO format).
    :param end_time: Event end time (ISO format).
    :param location: Event location.
    """
    return f"Event '{subject}' created from {start_time} to {end_time} at '{location}' (Simulated Calendar)"

# --- SharePoint Tools ---
@mcp.tool()
def sharepoint_search_files(query: str) -> list:
    """
    Search files and documents inside SharePoint sites.
    
    :param query: Term to search for.
    """
    return [
        {"name": "Architecture_Overview.pdf", "path": "/sites/dev/documents/Architecture_Overview.pdf", "modified": "2026-06-01"},
        {"name": "Sprint_Planning.docx", "path": "/sites/pm/documents/Sprint_Planning.docx", "modified": "2026-06-08"}
    ]

@mcp.tool()
def sharepoint_read_file(path: str) -> str:
    """
    Read content of a document stored in SharePoint.
    
    :param path: SharePoint document path.
    """
    return f"Content of document '{path}' (Simulated SharePoint File Data)"

# --- MS Teams Tools ---
@mcp.tool()
def teams_send_message(channel_id: str, message: str) -> str:
    """
    Send a chat message to a Microsoft Teams channel or chat.
    
    :param channel_id: Teams Channel ID or User Chat ID.
    :param message: Message body.
    """
    return f"Message sent to channel/chat '{channel_id}': '{message}' (Simulated MS Teams)"

@mcp.tool()
def teams_list_channels() -> list:
    """
    List active Teams channels.
    """
    return [
        {"id": "teams-ch-001", "name": "General", "description": "General discussions"},
        {"id": "teams-ch-002", "name": "Development", "description": "Tech discussions"}
    ]

if __name__ == "__main__":
    mcp.run()
