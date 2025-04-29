#!/usr/bin/env python3

import asyncio
import os
import argparse
import traceback
import uuid
import subprocess
import json
import sys
import getpass # Re-enabled for interactive setup
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
parser.add_argument('--setup', action='store_true', help='Run interactive setup mode to configure the agent')
parser.add_argument('--run-server', action='store_true', help='Run the MCP server in server mode')
args = parser.parse_args()

# --- Helper functions ---
def print_header(message):
    """Print a formatted header message"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}=== {message} ==={Colors.NC}\n")

def print_success(message):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {message}{Colors.NC}")

def print_error_and_exit(message, exit_code=1):
    """Print an error message to stderr and exit"""
    print(f"{Colors.RED}✗ {message}{Colors.NC}", file=sys.stderr)
    sys.exit(exit_code)

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
        print_error_and_exit(f"Command failed: {e}")
        return None

def write_mcp_config(api_key: str):
    """Writes the MCP configuration to ~/.cursor/mcp.json"""
    cursor_config_path = Path.home() / ".cursor" / "mcp.json"
    config_data = {"mcpServers": {}}

    try:
        if cursor_config_path.exists():
            try:
                with open(cursor_config_path, 'r') as f:
                    config_data = json.load(f)
                    if "mcpServers" not in config_data or not isinstance(config_data["mcpServers"], dict):
                        config_data["mcpServers"] = {}
            except json.JSONDecodeError:
                print(f"Warning: Existing MCP config at {cursor_config_path} is corrupted. Creating a new one.", file=sys.stderr)
                config_data = {"mcpServers": {}}

        server_config_for_cursor = {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/nandatheguntupalli/operative",
                "webEvalAgent",
                "--run-server" # IMPORTANT: Add --run-server here for when Cursor launches it
            ],
            "env": {
                "OPERATIVE_API_KEY": api_key
            }
        }

        config_data["mcpServers"]["web-eval-agent"] = server_config_for_cursor

        os.makedirs(cursor_config_path.parent, exist_ok=True)
        with open(cursor_config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        return True # Indicate success

    except Exception as e:
        print(f"Error writing Cursor MCP config: {e}", file=sys.stderr)
        return False # Indicate failure

def interactive_setup_agent():
    """
    Run the INTERACTIVE setup process for the web-eval-agent.
    Prompts for API key, validates it, and configures Cursor.
    Prints status messages to stdout.
    """
    print_welcome()

    # Step 1: Handle Operative API Key
    print_header("API Key Configuration")
    print(f"An Operative.sh API key is required for this installation.")
    print(f"If you don't have one, please visit {Colors.BOLD}https://operative.sh{Colors.NC} to get your key.\n")

    api_key = os.environ.get('OPERATIVE_API_KEY') # Check env first
    if api_key:
         print_info("Found API key in environment. Validating...")
         is_valid = asyncio.run(validate_api_key(api_key))
         if not is_valid:
              print(f"{Colors.YELLOW}API key in environment is invalid. Please enter a valid key.{Colors.NC}")
              api_key = None # Force prompt
         else:
              print_success("API key in environment validated successfully.")

    if not api_key:
        # Prompt for API key with validation
        while True:
            api_key = getpass.getpass("Please enter your Operative.sh API key: ")
            if not api_key:
                print(f"{Colors.RED}✗ API key cannot be empty{Colors.NC}")
                continue

            print_info("Validating API key with Operative servers...")
            is_valid = asyncio.run(validate_api_key(api_key))
            if is_valid:
                print_success("API key validated successfully")
                break
            else:
                print(f"{Colors.YELLOW}API key validation failed.{Colors.NC}")
                print(f"{Colors.YELLOW}Would you like to try again? (y/n){Colors.NC}")
                response = input().lower()
                if response != 'y':
                    print_error_and_exit("Installation cancelled - valid API key required")

    # Step 2: Configure Cursor
    print_header("Configuring MCP server")
    if write_mcp_config(api_key):
        print_success(f"MCP server configuration updated successfully in ~/.cursor/mcp.json")
    else:
        print_error_and_exit("Failed to write MCP configuration.")

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

def silent_setup_agent():
    """
    Run the SILENT setup process (e.g., when called by uvx from mcp.json).
    Relies on OPERATIVE_API_KEY environment variable.
    Writes configuration to ~/.cursor/mcp.json.
    Prints errors to stderr and exits on failure.
    Produces NO stdout output on success.
    """
    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        print_error_and_exit("Setup Error: OPERATIVE_API_KEY environment variable not found.", exit_code=2) # Use different exit code

    is_valid = asyncio.run(validate_api_key(api_key))
    if not is_valid:
        print_error_and_exit("Setup Error: Invalid OPERATIVE_API_KEY provided in environment.", exit_code=3) # Use different exit code

    if not write_mcp_config(api_key):
         print_error_and_exit("Setup Error: Failed to write Cursor MCP config.", exit_code=4) # Use different exit code

    # Silent successful exit (code 0)

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
    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        error_message_str = "❌ Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable."
        return [TextContent(type="text", text=error_message_str)]

    is_valid = await validate_api_key(api_key)
    if not is_valid:
        error_message_str = "❌ Error: API Key validation failed when running the tool.\n"
        error_message_str += "   Reason: Invalid key or free tier limit reached.\n"
        error_message_str += "   👉 Please check your key or subscribe at https://operative.sh to continue."
        return [TextContent(type="text", text=error_message_str)]

    try:
        tool_call_id = str(uuid.uuid4())
        send_log(f"Generated new tool_call_id for web_eval_agent: {tool_call_id}", "🔍")
        return await handle_web_evaluation(
            {"url": url, "task": task, "tool_call_id": tool_call_id},
            ctx,
            api_key
        )
    except Exception as e:
        tb = traceback.format_exc()
        send_log(f"Error executing web_eval_agent: {str(e)}\nTraceback:\n{tb}", "❌")
        return [TextContent(
            type="text",
            text=f"❌ Error executing web evaluation tool: {str(e)}"
        )]

def main():
    if args.run_server:
        # --- Server Mode ---
        api_key = os.environ.get('OPERATIVE_API_KEY')
        if not api_key:
            print_error_and_exit("Server Error: No API key provided. Please set the OPERATIVE_API_KEY environment variable.")

        try:
             is_valid = asyncio.run(validate_api_key(api_key))
             if not is_valid:
                  print_error_and_exit("Server Error: Invalid OPERATIVE_API_KEY provided in environment.")
        except Exception as e:
             print_error_and_exit(f"Server Error: Failed during API key validation: {e}")

        try:
            print_info("Starting web-eval-agent MCP server...") # This is fine, server mode isn't JSON stdio
            mcp.run(transport='stdio')
        finally:
            print_info("MCP server stopped.")
            pass
    elif args.setup:
        # --- Interactive Setup Mode ---
        # Run directly: python operative/webEvalAgent/mcp_server.py --setup
        interactive_setup_agent()
    else:
        # --- Default Mode (uvx without flags) ---
        # Run the silent setup logic expected by Cursor/uvx during initial configuration.
        silent_setup_agent()

if __name__ == "__main__":
    main()
