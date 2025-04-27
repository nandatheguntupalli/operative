#!/usr/bin/env python3

import asyncio
import os
import argparse
import traceback
import uuid
import subprocess
import json
import sys
import getpass
from enum import Enum
from pathlib import Path

# Set the API key to a fake key to avoid error in backend
os.environ["ANTHROPIC_API_KEY"] = 'not_a_real_key'
os.environ["ANONYMIZED_TELEMETRY"] = 'false'

# MCP imports
from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent

# Import our modules
from webEvalAgent.src.browser_manager import PlaywrightBrowserManager
# from webEvalAgent.src.browser_utils import cleanup_resources # Removed import
from webEvalAgent.src.api_utils import validate_api_key
from webEvalAgent.src.tool_handlers import handle_web_evaluation
from webEvalAgent.src.log_server import send_log

# Create the MCP server
mcp = FastMCP("Operative")

# Define the browser tools
class BrowserTools(str, Enum):
    WEB_EVAL_AGENT = "web_eval_agent"

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run the MCP server with browser debugging capabilities')
parser.add_argument('--setup', action='store_true', help='Run setup mode to configure the agent')
parser.add_argument('--run-server', action='store_true', help='Run the MCP server in server mode')
args = parser.parse_args()

def setup_agent():
    """
    Run the setup process for the web-eval-agent.
    This includes installing Playwright browsers, handling API key, and configuring Cursor.
    """
    send_log("Starting web-eval-agent setup", "🚀")
    
    # Step 1: Install Playwright browsers
    send_log("Installing Playwright browsers...", "🔍")
    try:
        subprocess.run(["playwright", "install", "--with-deps"], check=True)
        send_log("Successfully installed Playwright browsers", "✅")
    except subprocess.CalledProcessError as e:
        send_log(f"Error installing Playwright browsers: {e}", "❌")
        send_log("Please install Playwright manually: playwright install --with-deps", "⚠️")
    except FileNotFoundError:
        send_log("Playwright executable not found. Make sure it's installed correctly.", "❌")
        send_log("You can install it with: pip install playwright", "📝")
        sys.exit(1)
        
    # Step 2: Handle Operative API Key
    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        send_log("Operative API key not found in environment variables.", "🔍")
        send_log("You can get an API key (free) from https://operative.sh", "📝")
        api_key = getpass.getpass("Enter your Operative API key: ")
        
    # Validate the API key
    send_log("Validating API key...", "🔍")
    is_valid = asyncio.run(validate_api_key(api_key))
    if not is_valid:
        send_log("Error: Invalid API key. Please provide a valid OperativeAI API key.", "❌")
        send_log("You can get a key at https://operative.sh", "📝")
        sys.exit(1)
    
    send_log("API key validated successfully", "✅")
    
    # Step 3: Configure Cursor
    send_log("Configuring Cursor MCP settings...", "🔍")
    cursor_config_path = Path.home() / ".cursor" / "mcp.json"
    
    # Read existing config or create a new one
    try:
        if cursor_config_path.exists():
            with open(cursor_config_path, 'r') as f:
                config_data = json.load(f)
        else:
            config_data = {"mcpServers": {}}
    except (FileNotFoundError, json.JSONDecodeError):
        send_log(f"Creating new Cursor config at {cursor_config_path}", "📝")
        config_data = {"mcpServers": {}}
    
    # Define the server configuration for Cursor
    server_config_for_cursor = {
        "command": "uvx",
        "args": [
            "--from",
            "git+https://github.com/Operative-Sh/web-eval-agent.git",
            "webEvalAgent"
        ],
        "env": {
            "OPERATIVE_API_KEY": api_key
        }
    }
    
    # Update the configuration
    config_data["mcpServers"]["web-eval-agent"] = server_config_for_cursor
    
    # Write the updated configuration back to the file
    try:
        os.makedirs(cursor_config_path.parent, exist_ok=True)
        with open(cursor_config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        send_log(f"Successfully updated Cursor configuration at {cursor_config_path}", "✅")
    except Exception as e:
        send_log(f"Error writing to Cursor config: {e}", "❌")
        sys.exit(1)
    
    send_log("Setup completed successfully! 🎉", "🏁")
    send_log("Please restart Cursor for the changes to take effect.", "⚠️")
    send_log("You can now use the web-eval-agent in Cursor Agent Mode.", "📝")

@mcp.tool(name=BrowserTools.WEB_EVAL_AGENT)
async def web_eval_agent(url: str, task: str, working_directory: str, ctx: Context) -> list[TextContent]:
    """Evaluate the user experience / interface of a web application.

    This tool allows the AI to assess the quality of user experience and interface design
    of a web application by performing specific tasks and analyzing the interaction flow.

    Before this tool is used, the web application should already be running locally in a separate terminal.

    Args:
        url: Required. The localhost URL of the web application to evaluate, including the port number.
        task: Required. The specific UX/UI aspect to test (e.g., "test the checkout flow",
             "evaluate the navigation menu usability", "check form validation feedback")
             If no task is provided, the tool will high level evaluate the web application
        working_directory: Required. The root directory of the project

    Returns:
        list[TextContent]: A detailed evaluation of the web application's UX/UI, including
                         observations, issues found, and recommendations for improvement
                         Do not save this information to any file, but only return it to the agent
    """
    # Get API key from environment variable
    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        error_message_str = "❌ Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable."
        return [TextContent(type="text", text=error_message_str)]
        
    is_valid = await validate_api_key(api_key)

    if not is_valid:
        error_message_str = "❌ Error: API Key validation failed when running the tool.\n"
        error_message_str += "   Reason: Free tier limit reached.\n"
        error_message_str += "   👉 Please subscribe at https://operative.sh to continue."
        return [TextContent(type="text", text=error_message_str)]
    try:
        # Generate a new tool_call_id for this specific tool call
        tool_call_id = str(uuid.uuid4())
        send_log(f"Generated new tool_call_id for web_eval_agent: {tool_call_id}", "🔍")
        return await handle_web_evaluation(
            {"url": url, "task": task, "tool_call_id": tool_call_id},
            ctx,
            api_key
        )
    except Exception as e:
        tb = traceback.format_exc()
        return [TextContent(
            type="text",
            text=f"Error executing web_eval_agent: {str(e)}\n\nTraceback:\n{tb}"
        )]

def main():
    # Check if the script is run in setup mode or server mode
    if args.run_server:
        # Server Mode: Run the MCP server directly
        api_key = os.environ.get('OPERATIVE_API_KEY')
        if not api_key:
            send_log("Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable.", "❌")
            send_log("Run with --setup to configure the API key.", "📝")
            sys.exit(1)
        
        try:
            # Run the FastMCP server
            send_log("Starting web-eval-agent MCP server", "🚀")
            mcp.run(transport='stdio')
        finally:
            # Ensure resources are cleaned up
            # asyncio.run(cleanup_resources()) # Cleanup now handled in browser_utils
            pass # Keep finally block structure if needed later
    else:
        # Setup Mode: Configure the agent
        setup_agent()

if __name__ == "__main__":
    main()