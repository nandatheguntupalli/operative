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

# Colors for terminal output
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

def print_header(message):
    """Print a formatted header message"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}=== {message} ==={Colors.NC}\n")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_error(message):
    """Print an error message and exit"""
    print(f"{Colors.RED}✗ {message}{Colors.NC}")
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
        print_error(f"Command failed: {e}")
        return None

# Removed check_and_install_dependencies function

def setup_agent():
    """
    Run the setup process for the web-eval-agent.
    This includes handling API key and configuring Cursor.
    """
    # Print welcome message with ASCII art
    print_welcome()

    # Removed call to check_and_install_dependencies()

    # Step 1: Handle Operative API Key
    print_header("API Key Configuration")
    print(f"An Operative.sh API key is required for this installation.")
    print(f"If you don't have one, please visit {Colors.BOLD}https://operative.sh{Colors.NC} to get your key.\n")

    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        # Prompt for API key with validation
        while True:
            api_key = getpass.getpass("Please enter your Operative.sh API key: ")
            if not api_key:
                print(f"{Colors.RED}✗ API key cannot be empty{Colors.NC}")
                continue

            # Validate the API key
            print_info("Validating API key with Operative servers...")
            is_valid = asyncio.run(validate_api_key(api_key))
            if is_valid:
                print_success("API key validated successfully")
                break
            else:
                print(f"{Colors.YELLOW}Would you like to try again? (y/n){Colors.NC}")
                response = input().lower()
                if response != 'y':
                    print_error("Installation cancelled - valid API key required")
    else:
        # Validate existing API key
        print_info("Found API key in environment. Validating...")
        is_valid = asyncio.run(validate_api_key(api_key))
        if not is_valid:
            print_error("Invalid API key in environment. Please provide a valid OperativeAI API key.")

    # Step 2: Configure Cursor
    print_header("Configuring MCP server")
    cursor_config_path = Path.home() / ".cursor" / "mcp.json"

    # Read existing config or create a new one
    try:
        if cursor_config_path.exists():
            with open(cursor_config_path, 'r') as f:
                config_data = json.load(f)
            print_info(f"Found existing MCP configuration file")
        else:
            config_data = {"mcpServers": {}}
            print_info(f"Creating new MCP configuration file")
    except (FileNotFoundError, json.JSONDecodeError):
        config_data = {"mcpServers": {}}
        print_info(f"Creating new MCP configuration file")

    # Define the server configuration for Cursor
    server_config_for_cursor = {
        "command": "uvx",
        "args": [
            "--from",
            "git+https://github.com/nandatheguntupalli/operative",
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
        print_success(f"MCP server configuration updated successfully")
    except Exception as e:
        print_error(f"Error writing to Cursor config: {e}")

    # Installation complete
    print_header("Installation Complete! 🎉")
    print("Your Operative Web Eval Agent has been set up successfully.")
    print(f"\nYou can now use the web_eval_agent in Cursor Agent Mode.")
    print(f"""
{Colors.BOLD}{Colors.RED}⚠️  IMPORTANT: You must restart Cursor for changes to take effect! ⚠️{Colors.NC}
{Colors.RED}To restart the MCP server, you can close and reopen Cursor, or restart it from the Command Palette.{Colors.NC}
""")
    print(f"\nThank you for installing! 🙏\n")
    print(f"Built with ❤️  by Operative.sh")

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
            print_error("Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable.")

        try:
            # Run the FastMCP server
            print_info("Starting web-eval-agent MCP server")
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
