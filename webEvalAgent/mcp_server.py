#!/usr/bin/env python3

import asyncio
import os
import argparse
import traceback
import uuid
import subprocess
import json
import sys
import getpass # Keep import for potential direct use, but remove interactive calls in setup_agent
import platform
import shutil
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

# Colors for terminal output (kept for potential direct script execution, but not used in setup_agent)
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'  # No Color
    BOLD = '\033[1m'

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

# --- Helper functions (kept for potential direct script execution) ---
def print_header(message):
    """Print a formatted header message"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}=== {message} ==={Colors.NC}\n")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_error_and_exit(message):
    """Print an error message to stderr and exit"""
    # Print errors to stderr so they don't interfere with potential stdout JSON
    print(f"{Colors.RED}✗ {message}{Colors.NC}", file=sys.stderr)
    sys.exit(1)

def print_info(message):
    """Print an info message"""
    print(f"{Colors.YELLOW}ℹ {message}{Colors.NC}")

def print_welcome():
    """Print welcome message with ASCII art"""
    art = """                                    $$$$
                                 $$$    $$$
                              $$$          $$$
                           $$$     $$$$$$     $$$
                        $$$     $$$  $$  $$$     $$$c
                    c$$$     $$$     $$     $$$     $$$$
                   $$$$      $$$x    $$     $$$      $$$$
                   $$  $$$      >$$$ $$ ;$$$      $$$  $$
                   $$     $$$       $$$$8      $$$     $$
                   $$        $$$            $$$        $$
                   $$   $$$     $$$$     $$$     $$$   $$
                   $$   $  $$$     I$$$$$     $$$  $   $$
                   $$   $     $$$    $$    $$$     $   $$
                   $$   $     $$$$   $$   $$$$     $   $$
                   $$   $  $$$   $   $$   $   $$$  $   $$
                   $$   $$$      $   $$   $      $$$   $$
                   $$     $$$    $   $$   $    $$$     $$
                    $$$      $$$ $   $$   $ $$$      $$$
                       $$$      $$   $$   $$      $$$
                          $$$        $$        $$$
                             $$$     $$     $$$
                                $$$  $$  $$$
                                   $$$$$$
"""
    print(art)
    print(f"\n{Colors.BOLD}🚀 Welcome to the Operative Web Eval Agent Installer{Colors.NC}")
    print(f"This script will set up everything you need to get started.\n")

def command_exists(command):
    """Check if a command exists in the system PATH"""
    return shutil.which(command) is not None

def run_command(command, shell=False):
    """Run a command and return its output"""
    try:
        result = subprocess.run(
            command,
            shell=shell,
            check=True,
            text=True,
            capture_output=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        # Use the error printing function
        print_error_and_exit(f"Command failed: {e}")
        return None

# Removed check_and_install_dependencies function

def setup_agent():
    """
    Run the setup process silently for the web-eval-agent.
    Relies on OPERATIVE_API_KEY environment variable.
    Writes configuration to ~/.cursor/mcp.json.
    Prints errors to stderr and exits on failure.
    Produces NO stdout output on success.
    """
    # --- Step 1: Validate Operative API Key from Environment ---
    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        # Print error to stderr and exit
        print_error_and_exit("Setup Error: OPERATIVE_API_KEY environment variable not found.")

    # Validate the API key silently
    is_valid = asyncio.run(validate_api_key(api_key))
    if not is_valid:
        # Print error to stderr and exit
        print_error_and_exit("Setup Error: Invalid OPERATIVE_API_KEY provided in environment.")

    # --- Step 2: Configure Cursor MCP ---
    cursor_config_path = Path.home() / ".cursor" / "mcp.json"
    config_data = {"mcpServers": {}} # Start fresh or load existing

    try:
        if cursor_config_path.exists():
            try:
                with open(cursor_config_path, 'r') as f:
                    config_data = json.load(f)
                    # Ensure mcpServers key exists
                    if "mcpServers" not in config_data or not isinstance(config_data["mcpServers"], dict):
                         config_data["mcpServers"] = {}
            except json.JSONDecodeError:
                 # If file is corrupted, start fresh but log to stderr
                 print(f"Warning: Existing MCP config at {cursor_config_path} is corrupted. Creating a new one.", file=sys.stderr)
                 config_data = {"mcpServers": {}}
        # Define the server configuration for Cursor
        server_config_for_cursor = {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/nandatheguntupalli/operative",
                "webEvalAgent"
            ],
            "env": {
                "OPERATIVE_API_KEY": api_key # Use the validated key from env
            }
        }

        # Update the configuration
        config_data["mcpServers"]["web-eval-agent"] = server_config_for_cursor

        # Write the updated configuration back to the file
        os.makedirs(cursor_config_path.parent, exist_ok=True)
        with open(cursor_config_path, 'w') as f:
            json.dump(config_data, f, indent=2)

    except Exception as e:
        # Print error to stderr and exit
        print_error_and_exit(f"Setup Error: Failed to write Cursor MCP config to {cursor_config_path}: {e}")

    # --- Success ---
    # No stdout output on success, as required by MCP protocol during setup via uvx.
    # A silent exit with code 0 indicates success.

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

    # Validate key *before* attempting tool logic
    is_valid = await validate_api_key(api_key)
    if not is_valid:
        error_message_str = "❌ Error: API Key validation failed when running the tool.\n"
        error_message_str += "   Reason: Invalid key or free tier limit reached.\n"
        error_message_str += "   👉 Please check your key or subscribe at https://operative.sh to continue."
        return [TextContent(type="text", text=error_message_str)]

    try:
        # Generate a new tool_call_id for this specific tool call
        tool_call_id = str(uuid.uuid4())
        # Log tool call ID internally if needed (using send_log which doesn't go to MCP stdout)
        send_log(f"Generated new tool_call_id for web_eval_agent: {tool_call_id}", "🔍")
        return await handle_web_evaluation(
            {"url": url, "task": task, "tool_call_id": tool_call_id},
            ctx,
            api_key
        )
    except Exception as e:
        tb = traceback.format_exc()
        # Log the error internally
        send_log(f"Error executing web_eval_agent: {str(e)}\nTraceback:\n{tb}", "❌")
        # Return a user-friendly error message via MCP
        return [TextContent(
            type="text",
            text=f"❌ Error executing web evaluation tool: {str(e)}"
        )]

def main():
    # Check if the script is run in server mode or setup mode
    if args.run_server:
        # Server Mode: Run the MCP server directly
        api_key = os.environ.get('OPERATIVE_API_KEY')
        if not api_key:
            # Use the error printing function for server mode startup issues
            print_error_and_exit("Server Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable.")

        # Validate API key before starting server
        # Use run_until_complete for async function outside event loop
        try:
             is_valid = asyncio.run(validate_api_key(api_key))
             if not is_valid:
                  print_error_and_exit("Server Error: Invalid OPERATIVE_API_KEY provided in environment.")
        except Exception as e:
             print_error_and_exit(f"Server Error: Failed during API key validation: {e}")


        try:
            # Run the FastMCP server
            # Use print_info for server startup messages (goes to console, not MCP)
            print_info("Starting web-eval-agent MCP server...")
            mcp.run(transport='stdio')
        finally:
            # Cleanup logic if needed
            print_info("MCP server stopped.")
            pass
    elif args.setup:
         # Explicit Setup Mode (run directly from terminal: python mcp_server.py --setup)
         # Use interactive prints here
         print_welcome()
         print_header("Manual Setup Mode")
         # Add manual setup logic here if desired, potentially reusing parts of the old setup_agent
         # For now, just indicate it needs to be run via uvx
         print_info("Manual setup via 'python mcp_server.py --setup' is currently disabled.")
         print_info("Please run the setup through Cursor/uvx:")
         print("uvx --from git+https://github.com/nandatheguntupalli/operative webEvalAgent")
    else:
        # Default Mode (invoked by uvx without --run-server): Run the silent setup
        setup_agent()

if __name__ == "__main__":
    main()
