#!/usr/bin/env python3

import asyncio
import os
import argparse
import traceback
import uuid
import subprocess
import json
import sys
import getpass # Needed for interactive prompt
import platform
import shutil
from enum import Enum
from pathlib import Path

# --- Core MCP/Tool Imports ---
# Set the API key to a fake key to avoid error in backend (if needed by imports)
os.environ["ANTHROPIC_API_KEY"] = 'not_a_real_key'
os.environ["ANONYMIZED_TELEMETRY"] = 'false'

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent

# --- Agent Specific Imports ---
# Attempt imports, handle if they fail during initial setup runs where
# dependencies might not be fully available yet.
try:
    from webEvalAgent.src.browser_manager import PlaywrightBrowserManager
    from webEvalAgent.src.api_utils import validate_api_key
    from webEvalAgent.src.tool_handlers import handle_web_evaluation
    # --- CORRECTED IMPORT HERE ---
    from webEvalAgent.src.log_server import send_log, start_log_server, open_log_dashboard # Corrected import
    # --- END CORRECTION ---
except ImportError as e:
    # Allow script to run for setup even if agent modules fail initially
    print(f"Initial import warning (expected during setup): {e}", file=sys.stderr)
    validate_api_key = None # Ensure setup doesn't crash trying to call it
    handle_web_evaluation = None
    # --- Ensure these match the imported names ---
    send_log = None
    start_log_server = None
    open_log_dashboard = None
    # --- END ---

# --- Terminal Colors (for interactive setup ONLY) ---
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    BLUE = '\033[0;34m'
    YELLOW = '\033[1;33m'
    NC = '\033[0m'  # No Color
    BOLD = '\033[1m'

# Create the MCP server instance
mcp = FastMCP("Operative")

# Define the browser tools
class BrowserTools(str, Enum):
    WEB_EVAL_AGENT = "web_eval_agent"

# --- Helper functions (for interactive setup ONLY) ---
# These functions print directly and MUST NOT be called in server mode

def _print_interactive(message_type, message):
    """Helper to print only if stdout is a TTY (interactive session)"""
    if sys.stdout.isatty():
        colors = {
            "header": f"\n{Colors.BLUE}{Colors.BOLD}=== {message} ==={Colors.NC}\n",
            "success": f"{Colors.GREEN}✓ {message}{Colors.NC}",
            "error": f"{Colors.RED}✗ {message}{Colors.NC}",
            "info": f"{Colors.YELLOW}ℹ {message}{Colors.NC}",
            "welcome": message # ASCII art doesn't need color codes here
        }
        print(colors.get(message_type, message))
    elif message_type == "error":
        # Ensure errors are still visible in logs even if not interactive
        print(f"ERROR: {message}", file=sys.stderr)


def print_header(message): _print_interactive("header", message)
def print_success(message): _print_interactive("success", message)
def print_error(message): _print_interactive("error", message) # Still prints error to stderr if not TTY
def print_info(message): _print_interactive("info", message)
def print_welcome(art): _print_interactive("welcome", art)


def print_error_and_exit(message, exit_code=1):
    """Prints error (respecting TTY) and exits."""
    print_error(message)
    sys.exit(exit_code)

def command_exists(command):
    """Check if a command exists in the system PATH"""
    return shutil.which(command) is not None

# --- Configuration Writing ---

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
                print_error(f"Existing MCP config at {cursor_config_path} is corrupted. Creating a new one.")
                config_data = {"mcpServers": {}}
        else:
             print_info(f"No existing MCP config found at {cursor_config_path}. Creating.")


        # Define the server configuration for Cursor
        # IMPORTANT: Add --run-server here so Cursor launches the server next time
        server_config_for_cursor = {
            "command": "uvx",
            "args": [
                "--from",
                "git+https://github.com/nandatheguntupalli/operative",
                "webEvalAgent",
                "--run-server" # Make sure this flag is present for subsequent runs
            ],
            "env": {
                "OPERATIVE_API_KEY": api_key,
                # Set Playwright browser path for hermetic install
                "PLAYWRIGHT_BROWSERS_PATH": "0"
            }
        }

        # Update the configuration
        config_data["mcpServers"]["web-eval-agent"] = server_config_for_cursor

        # Write the updated configuration back to the file
        os.makedirs(cursor_config_path.parent, exist_ok=True)
        with open(cursor_config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        return True # Indicate success

    except Exception as e:
        # Print error to stderr and exit
        print_error(f"Error writing Cursor MCP config: {e}")
        return False # Indicate failure

# --- Setup Functions (Interactive / Silent) ---

async def _validate_key_wrapper(api_key):
    """Async wrapper for API key validation."""
    if validate_api_key:
        return await validate_api_key(api_key)
    print_error("Validation function not available (Import failed). Cannot validate key.")
    return False


def interactive_setup_agent():
    """
    Run the INTERACTIVE setup process. Prompts for API key if not in env.
    Prints status messages to stdout using helper functions.
    """
    welcome_art = """
                                    $$$$
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
    print_welcome(welcome_art)
    print_header("Operative Agent Setup")

    # Check if validation function loaded
    if not validate_api_key:
         print_error_and_exit("Core agent modules failed to load. Cannot run setup.", 5)


    api_key = os.environ.get('OPERATIVE_API_KEY')
    key_validated = False

    if api_key:
        print_info("Found API key in environment. Validating...")
        try:
            # Use asyncio.run for the async validation function
            is_valid = asyncio.run(_validate_key_wrapper(api_key))
            if is_valid:
                print_success("API key in environment validated successfully.")
                key_validated = True
            else:
                print_error("API key in environment is invalid. Please enter a valid key.")
                api_key = None # Force prompt
        except Exception as e:
             print_error(f"Error validating API key from environment: {e}. Please enter key manually.")
             api_key = None # Force prompt
    else:
        print_info("No OPERATIVE_API_KEY found in environment.")

    if not key_validated:
        print_info("An Operative.sh API key is required.")
        print_info(f"If you don't have one, please visit {Colors.BOLD}https://operative.sh{Colors.NC}")
        while True:
            try:
                api_key = getpass.getpass("Please enter your Operative.sh API key: ")
            except EOFError:
                print_error_and_exit("\nInput stream closed. Cannot get API key.", 6)
            if not api_key:
                print_error("API key cannot be empty")
                continue

            print_info("Validating API key with Operative servers...")
            try:
                is_valid = asyncio.run(_validate_key_wrapper(api_key))
                if is_valid:
                    print_success("API key validated successfully")
                    key_validated = True
                    break
                else:
                    print_error("API key validation failed.")
                    print_info("Would you like to try again? (y/n)")
                    try:
                        response = input().lower()
                        if response != 'y':
                             print_error_and_exit("Installation cancelled - valid API key required")
                    except EOFError:
                         print_error_and_exit("\nInput stream closed. Installation cancelled.", 7)

            except Exception as e:
                 print_error(f"Error during API key validation: {e}")
                 print_info("Would you like to try again? (y/n)")
                 try:
                     response = input().lower()
                     if response != 'y':
                         print_error_and_exit("Installation cancelled - validation failed")
                 except EOFError:
                     print_error_and_exit("\nInput stream closed. Installation cancelled.", 8)


    # Configure Cursor
    print_header("Configuring Cursor")
    if write_mcp_config(api_key):
        print_success("MCP server configuration updated successfully in ~/.cursor/mcp.json")
    else:
        # write_mcp_config prints the error
        print_error_and_exit("Failed to write MCP configuration.", 9)

    # Installation complete
    print_header("Installation Complete! 🎉")
    print_info("Your Operative Web Eval Agent has been set up successfully.")
    print_info(f"You can now use the {Colors.BOLD}web_eval_agent{Colors.NC} in Cursor Agent Mode.")
    print_info(f"""
{Colors.BOLD}{Colors.RED}⚠️  IMPORTANT: You MUST restart Cursor for changes to take effect! ⚠️{Colors.NC}
{Colors.RED}   Close and reopen Cursor, or use the Command Palette to restart it.{Colors.NC}
""")
    print_info("Thank you for installing! 🙏")
    print_info("Built with ❤️  by Operative.sh")

def silent_setup_agent():
    """
    Run the SILENT setup process (e.g., when called by uvx non-interactively).
    Relies *strictly* on OPERATIVE_API_KEY environment variable.
    Writes configuration to ~/.cursor/mcp.json.
    Prints errors ONLY to stderr and exits on failure.
    Produces NO stdout output on success.
    """
    # Check if validation function loaded
    if not validate_api_key:
         print_error_and_exit("Setup Error: Core agent modules failed to load.", 5)

    api_key = os.environ.get('OPERATIVE_API_KEY')
    if not api_key:
        print_error_and_exit("Setup Error: OPERATIVE_API_KEY environment variable not found.", exit_code=2)

    try:
        is_valid = asyncio.run(_validate_key_wrapper(api_key))
    except Exception as e:
         print_error_and_exit(f"Setup Error: Exception during API key validation: {e}", exit_code=5)

    if not is_valid:
        print_error_and_exit("Setup Error: Invalid OPERATIVE_API_KEY provided in environment.", exit_code=3)

    # write_mcp_config handles its own errors and exits
    if not write_mcp_config(api_key):
         # Explicit exit here in case write_mcp_config failed but didn't exit (e.g., if run interactively)
         sys.exit(4)

    # Silent successful exit (code 0) - no stdout print

# --- MCP Tool Definition ---

# Define the tool only if the handler function was imported successfully
if handle_web_evaluation:
    @mcp.tool(name=BrowserTools.WEB_EVAL_AGENT)
    async def web_eval_agent(url: str, task: str, working_directory: str, ctx: Context) -> list[TextContent]:
        """Evaluate the user experience / interface of a web application.
        (Args and Returns documentation omitted for brevity)
        """
        # Ensure validation function is available before proceeding
        if not validate_api_key:
            return [TextContent(type="text", text="❌ Error: Core validation module not loaded.")]

        # Use os.environ directly inside the tool
        api_key = os.environ.get('OPERATIVE_API_KEY')
        if not api_key:
            # This shouldn't happen if setup ran correctly, but check anyway
            error_message_str = "❌ Server Error: No API key found in environment during tool execution."
            if send_log: send_log(error_message_str, "🔐", log_type='status')
            return [TextContent(type="text", text=error_message_str)]

        # Re-validate key just before running? (Optional, adds overhead)
        # is_valid = await _validate_key_wrapper(api_key)
        # if not is_valid:
        #     error_message_str = "❌ Error: API Key validation failed when running the tool.\n"
        #     error_message_str += "   Reason: Invalid key or free tier limit reached.\n"
        #     error_message_str += "   👉 Please check your key or subscribe at https://operative.sh to continue."
        #     if send_log: send_log(error_message_str, "🔐", log_type='status')
        #     return [TextContent(type="text", text=error_message_str)]

        try:
            tool_call_id = str(uuid.uuid4())
            # Use send_log if available
            if send_log: send_log(f"Generated new tool_call_id for web_eval_agent: {tool_call_id}", "🔍", log_type='agent')
            return await handle_web_evaluation(
                {"url": url, "task": task, "tool_call_id": tool_call_id},
                ctx,
                api_key
            )
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = f"Error executing web_eval_agent: {str(e)}\nTraceback:\n{tb}"
             # Use send_log if available, otherwise print to stderr
            if send_log:
                send_log(error_msg, "❌", log_type='status')
            else:
                print(error_msg, file=sys.stderr)
            return [TextContent(
                type="text",
                text=f"❌ Error executing web evaluation tool: {str(e)}" # Return simpler error via MCP
            )]
else:
     # If the handler failed to import, the tool cannot be defined.
     # MCP server will start but won't offer the tool.
     print("ERROR: handle_web_evaluation not loaded. web_eval_agent tool will be unavailable.", file=sys.stderr)


# --- Main Execution Logic ---

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Run the MCP server with browser debugging capabilities')
    parser.add_argument('--setup', action='store_true', help='Force interactive setup mode')
    parser.add_argument('--run-server', action='store_true', help='Run the MCP server in server mode')
    args = parser.parse_args()

    if args.run_server:
        # --- Server Mode ---
        # Check API key from environment - crucial for server operation
        api_key = os.environ.get('OPERATIVE_API_KEY')
        if not api_key:
             # Use print_error_and_exit which writes to stderr
             print_error_and_exit("Server Error: OPERATIVE_API_KEY environment variable not found.", exit_code=10)

        # Validate key ONLY if the validation function is available
        if validate_api_key:
            try:
                 is_valid = asyncio.run(_validate_key_wrapper(api_key))
                 if not is_valid:
                      print_error_and_exit("Server Error: Invalid OPERATIVE_API_KEY provided in environment.", exit_code=11)
            except Exception as e:
                 print_error_and_exit(f"Server Error: Failed during API key validation: {e}", exit_code=12)
        else:
            # If validation isn't available, maybe proceed but log a warning?
            # Or exit? Exiting is safer.
            print_error_and_exit("Server Error: Core validation module not loaded. Cannot verify API key.", 13)

        # Key is present and validated (if possible). Run the server.
        # Do NOT print informational messages to stdout here. Use stderr if needed.
        print("Starting web-eval-agent MCP server... (JSON mode)", file=sys.stderr)
        try:
            mcp.run(transport='stdio')
        except Exception as e:
             print(f"FATAL: MCP server crashed: {e}\n{traceback.format_exc()}", file=sys.stderr)
             sys.exit(14) # Exit with error code if server crashes
        finally:
            # This might print to stderr if needed, but avoid stdout
            print("MCP server stopped.", file=sys.stderr)

    elif args.setup:
         # --- Explicit Interactive Setup Mode ---
         # Called via: python path/to/mcp_server.py --setup
         interactive_setup_agent()
    else:
        # --- Default Mode (uvx without flags / direct run without flags) ---
        # Detect if running interactively (likely user running manually) or not (likely uvx/Cursor)
        if sys.stdout.isatty():
            # Interactive TTY detected: Perform interactive setup
            print("Interactive mode detected. Running setup...", file=sys.stderr) # Log intent to stderr
            interactive_setup_agent()
        else:
            # Non-interactive: Perform silent setup
            # Requires OPERATIVE_API_KEY env var to be set externally.
            print("Non-interactive mode detected. Running silent setup...", file=sys.stderr) # Log intent to stderr
            silent_setup_agent()
            print("Silent setup complete.", file=sys.stderr) # Log completion to stderr


if __name__ == "__main__":
    # This check ensures the main logic runs only when the script is executed directly
    main()
