#!/usr/bin/env python3

import asyncio
import io
import json
import logging
import uuid
import warnings
from contextlib import redirect_stdout, redirect_stderr
from typing import Dict, Any, Tuple, List, Optional
from collections import deque
import os # <--- Add os import
import subprocess # <--- Add subprocess import
import sys # <--- Add sys import


# Import log server function
from .log_server import send_log

# Import Playwright types
from playwright.async_api import async_playwright, Error as PlaywrightError, Browser as PlaywrightBrowser, BrowserContext as PlaywrightBrowserContext, Page as PlaywrightPage

# Local imports (assuming browser_manager is potentially still used for singleton logic elsewhere, or can be removed if fully replaced)
# from browser_manager import PlaywrightBrowserManager # Commented out if not needed

# Browser-use imports
from browser_use.agent.service import Agent
from browser_use.browser.browser import Browser, BrowserConfig
from browser_use.browser.context import BrowserContext # Import BrowserContext

# Langchain/MCP imports
from langchain_anthropic import ChatAnthropic
from mcp.server.fastmcp import Context
from langchain.globals import set_verbose

# This prevents the browser window from stealing focus during execution.
async def _no_bring_to_front(self, *args, **kwargs):
    print("Skipping bring_to_front call.") # Optional: for debugging
    return None

PlaywrightPage.bring_to_front = _no_bring_to_front
# --- End Patch ---

# Global variable to store agent instance - might be less necessary if Agent is created per task run
agent_instance = None
# Global variable to store the original patched method if patching class-level
original_create_context: Optional[callable] = None

# Define the maximum number of logs/requests to keep
MAX_LOG_ENTRIES = 10

# --- URL Filtering for Network Requests ---
# ... (should_log_network_request function remains the same) ...
def should_log_network_request(url: str) -> bool:
    # Filter out common static assets that aren't usually relevant
    if '/node_modules/' in url: return False
    extensions_to_filter = ['.js', '.css', '.woff', '.woff2', '.ttf', '.eot', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.map']
    for ext in extensions_to_filter:
        if url.endswith(ext) or f"{ext}?" in url: return False
    if '/api/' in url or '/graphql' in url: return True
    if '?' not in url and '.' not in url.split('/')[-1]: return True
    return True


# --- Log Storage (Global within this module using deque) ---
console_log_storage: deque = deque(maxlen=MAX_LOG_ENTRIES)
network_request_storage: deque = deque(maxlen=MAX_LOG_ENTRIES)

# --- Log Handlers (Use deque's append and send_log with type) ---
# ... (handle_console_message, handle_request, handle_response functions remain the same) ...
async def handle_console_message(message):
    try:
        text = message.text
        log_entry = { "type": message.type, "text": text, "location": message.location, "timestamp": asyncio.get_event_loop().time() }
        console_log_storage.append(log_entry)
        send_log(f"CONSOLE [{log_entry['type']}]: {log_entry['text']}", "🖥️", log_type='console')
    except Exception as e:
        send_log(f"Error handling console message: {e}", "❌", log_type='status')

async def handle_request(request):
    try:
        if not should_log_network_request(request.url): return
        try: headers = await request.all_headers()
        except PlaywrightError as e: headers = {"error": f"Req Header Error: {e}"}
        except Exception as e: headers = {"error": f"Unexpected Req Header Error: {e}"}
        post_data = None
        try:
            if request.post_data:
                 post_data_buffer = await request.post_data_buffer()
                 if post_data_buffer:
                     try: post_data = post_data_buffer.decode('utf-8', errors='replace')
                     except Exception: post_data = repr(post_data_buffer)
                 else: post_data = ""
            else: post_data = None
        except PlaywrightError as e: post_data = f"Post Data Error: {e}"
        except Exception as e: post_data = f"Unexpected Post Data Error: {e}"
        request_entry = { "url": request.url, "method": request.method, "headers": headers, "postData": post_data, "timestamp": asyncio.get_event_loop().time(), "resourceType": request.resource_type, "is_navigation": request.is_navigation_request(), "id": id(request) }
        network_request_storage.append(request_entry)
        send_log(f"NET REQ [{request_entry['method']}]: {request_entry['url']}", "➡️", log_type='network')
    except Exception as e:
        url = request.url if request else 'Unknown URL'
        send_log(f"Error handling request event for {url}: {e}", "❌", log_type='status')

async def handle_response(response):
    req_id = id(response.request)
    url = response.url
    if not should_log_network_request(url): return
    try:
        try: headers = await response.all_headers()
        except PlaywrightError as e: headers = {"error": f"Resp Header Error: {e}"}
        except Exception as e: headers = {"error": f"Unexpected Resp Header Error: {e}"}
        status = response.status
        body_size = -1
        try:
            body_buffer = await response.body()
            body_size = len(body_buffer) if body_buffer else 0
        except PlaywrightError as e: print(f"Warning: Could not get response body size for {url}: {e}")
        except Exception as e: print(f"Warning: Unexpected error getting response body size for {url}: {e}")
        for req in network_request_storage:
            if req.get("id") == req_id and "response_status" not in req:
                req["response_status"] = status
                req["response_headers"] = headers
                req["response_body_size"] = body_size
                req["response_timestamp"] = asyncio.get_event_loop().time()
                send_log(f"NET RESP [{status}]: {url}", "⬅️", log_type='network')
                break
        else:
             send_log(f"NET RESP* [{status}]: {url} (req not matched/updated)", "⬅️", log_type='network')
    except Exception as e:
        send_log(f"Error handling response event for {url}: {e}", "❌", log_type='status')


# --- Function to ensure browsers are installed ---
def ensure_playwright_browsers_installed():
    """Checks if browsers are installed and attempts installation if not."""
    try:
        # We will attempt to install using subprocess, setting the env var
        # Use 'python -m playwright install' for better cross-platform compatibility
        # Only install chromium as it's the one used
        command = [sys.executable, "-m", "playwright", "install", "chromium"]
        send_log(f"Running command to ensure Playwright browsers: {' '.join(command)}", "⚙️", log_type='status')

        # Set environment variable specifically for this subprocess call
        install_env = os.environ.copy()
        install_env["PLAYWRIGHT_BROWSERS_PATH"] = "0"

        # Run the command
        result = subprocess.run(
            command,
            env=install_env,
            capture_output=True,
            text=True,
            check=False # Don't throw error immediately, check output
        )

        # Log output
        if result.stdout:
            send_log(f"Playwright install STDOUT:\n{result.stdout}", "📄", log_type='status')
        if result.stderr:
            send_log(f"Playwright install STDERR:\n{result.stderr}", "⚠️", log_type='status')

        if result.returncode == 0:
            send_log("Playwright browser check/install command completed successfully.", "✅", log_type='status')
        else:
            send_log(f"Playwright browser check/install command failed with code {result.returncode}.", "❌", log_type='status')
            # Optionally raise an exception or handle failure
            # raise RuntimeError(f"Failed to install playwright browsers: {result.stderr}")

    except FileNotFoundError:
        # This might happen if playwright CLI is not in PATH even if library is installed
        send_log("Error: 'playwright' command not found. Cannot ensure browsers are installed.", "❌", log_type='status')
        raise RuntimeError("Playwright CLI command not found. Is Playwright installed correctly in the environment?")
    except Exception as e:
        send_log(f"An unexpected error occurred during Playwright browser installation check: {e}", "❌", log_type='status')
        raise RuntimeError(f"Failed during Playwright browser setup: {e}")


async def run_browser_task(task: str, model: str = "gemini-2.0-flash-001", ctx: Context = None, tool_call_id: str = None, api_key: str = None) -> str:
    """
    Run a task using browser-use agent, sending logs to the dashboard.

    Args:
        task: The task to run.
        model: The model identifier (not directly used for LLM here, taken from ChatAnthropic).
        ctx: The MCP context for progress reporting.
        tool_call_id: The tool call ID for API headers.
        api_key: The API key for authentication.

    Returns:
        str: Agent's final result (stringified).
    """
    global agent_instance, console_log_storage, network_request_storage, original_create_context
    import traceback # Make sure traceback is imported for error logging

    # --- Clear Logs for this Run ---
    console_log_storage.clear()
    network_request_storage.clear()

    # Local Playwright variables for this run
    playwright = None
    playwright_browser = None
    agent_browser = None # browser-use Browser instance
    local_original_create_context = None # To store original method for this run's finally block

    # Configure logging suppression
    logging.basicConfig(level=logging.CRITICAL) # Set root logger level first
    # Then configure specific loggers
    for logger_name in ['browser_use', 'root', 'agent', 'browser']:
        current_logger = logging.getLogger(logger_name)
        current_logger.setLevel(logging.CRITICAL)

    warnings.filterwarnings("ignore", category=UserWarning)
    set_verbose(False)

    try:
        # --- *** NEW: Ensure browsers are installed before initializing Playwright *** ---
        send_log("Ensuring Playwright browser executables are installed...", "🛠️", log_type='status')
        ensure_playwright_browsers_installed()
        send_log("Browser installation check/attempt complete.", "✔️", log_type='status')
        # --- *** END NEW SECTION *** ---


        # --- Initialize Playwright Directly ---
        # Make sure PLAYWRIGHT_BROWSERS_PATH is set if ensure_playwright_browsers_installed ran
        # Although ensure_... set it for the subprocess, we might need it here too for lookup
        # Note: This might conflict if mcp.json also tries to set it. Relying on ensure_... is likely better.
        # os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0" # Might be redundant or cause issues

        playwright = await async_playwright().start()
        # Now attempt to launch, hopefully the executable exists after ensure_... ran
        playwright_browser = await playwright.chromium.launch(headless=False)
        send_log("Playwright initialized for task.", "🎭", log_type='status') # Type: status

        # --- Create browser-use Browser ---
        browser_config = BrowserConfig(disable_security=True, headless=False)
        agent_browser = Browser(config=browser_config)
        agent_browser.playwright = playwright
        agent_browser.playwright_browser = playwright_browser
        send_log("Linked Playwright to agent browser.", "🔗", log_type='status') # Type: status

        # --- Patch BrowserContext._create_context ---
        # (Patching logic remains the same)
        if original_create_context is None:
            original_create_context = BrowserContext._create_context
            local_original_create_context = original_create_context
        else:
            local_original_create_context = original_create_context
        async def patched_create_context(self: BrowserContext, browser_pw: PlaywrightBrowser) -> PlaywrightBrowserContext:
            if original_create_context is None: raise RuntimeError("Original _create_context not stored correctly")
            raw_playwright_context: PlaywrightBrowserContext = await original_create_context(self, browser_pw)
            send_log("BrowserContext patched, attaching log handlers...", "🔧", log_type='status')
            if raw_playwright_context:
                raw_playwright_context.on("console", handle_console_message)
                raw_playwright_context.on("request", handle_request)
                raw_playwright_context.on("response", handle_response)
                send_log("Log listeners attached.", "👂", log_type='status')
            else:
                 send_log("Original _create_context did not return a context.", "⚠️", log_type='status')
            return raw_playwright_context
        BrowserContext._create_context = patched_create_context


        # --- Ensure Tool Call ID ---
        if tool_call_id is None:
            tool_call_id = str(uuid.uuid4())
            send_log(f"Generated tool_call_id: {tool_call_id}", "🆔", log_type='status') # Type: status

        # --- LLM Setup ---
        from .env_utils import get_backend_url

        llm = ChatAnthropic(model="claude-3-5-sonnet-20240620",
            base_url=get_backend_url(f"v1beta/models/claude-3-5-sonnet-20240620"),
            extra_headers={
                "x-operative-api-key": api_key,
                "x-operative-tool-call-id": tool_call_id
            })
        send_log(f"LLM ({llm.model}) configured.", "🤖", log_type='status') # Type: status

        # --- Agent Callback ---
        async def state_callback(browser_state, agent_output, step_number):
            send_log(f"Step {step_number}", "📍", log_type='agent')
            send_log(f"URL: {browser_state.url}", "🔗", log_type='agent')
            output_str = str(agent_output)
            send_log(f"Agent Output: {output_str}", "💬", log_type='agent')

        # --- Initialize and Run Agent ---
        agent = Agent(
            task=task,
            llm=llm,
            browser=agent_browser,
            register_new_step_callback=state_callback
        )
        agent_instance = agent

        send_log(f"Agent starting task: {task}", "🏃", log_type='agent') # Type: agent
        agent_result = await agent.run()
        send_log(f"Agent run finished.", "🏁", log_type='agent') # Type: agent

        # --- Prepare Combined Results ---
        serialized_result = str(agent_result)

        # Return only the agent result
        return serialized_result

    except Exception as e:
        error_message = f"Error in run_browser_task: {e}\n{traceback.format_exc()}"
        # Check if the error is the specific executable missing error
        if "Executable doesn't exist" in str(e):
            error_message += "\n\nPossible cause: Playwright browser executable failed to install automatically within the uvx environment, even after explicit check/install attempt. Check permissions and network access for the environment, or consider running 'playwright install' manually if issues persist."
            send_log("Playwright executable still missing after install attempt. Check logs.", "❌", log_type='status')
        else:
            send_log(error_message, "❌", log_type='status') # Type: status
        return error_message # Return the detailed error
    finally:
        # --- Cleanup ---
        if local_original_create_context:
            BrowserContext._create_context = local_original_create_context
            send_log("Original BrowserContext restored.", "🔧", log_type='status') # Type: status

        if agent_browser:
            await agent_browser.close()
            agent_browser = None
            send_log("Agent browser resources cleaned up.", "🧹", log_type='status') # Type: status
        if playwright:
            await playwright.stop()
            playwright = None
            send_log("Playwright instance for task stopped.", "🧹", log_type='status') # Type: status

        agent_instance = None