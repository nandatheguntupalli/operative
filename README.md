# 🚀 operative.sh web-eval-agent MCP Server

> *Let the coding agent debug itself, you've got better things to do.*

![Demo](./demo.gif)



## 🔥 Supercharge Your Debugging

[operative.sh](https://www.operative.sh)'s MCP Server unleashes LLM-powered agents to autonomously execute and debug web apps directly in your code editor.

## ⚡ Features

This weapon in your development arsenal transforms your Code IDE experience (Cline, Cursor):

- 🌐 **Navigate your webapp** using BrowserUse (2x faster with operative backend)
- 📊 **Capture network traffic** - all requests/responses at your fingertips
- 🚨 **Collect console errors** - nothing escapes detection
- 🤖 **Autonomous debugging** - the Cursor agent calls the web QA agent mcp server to test if the code it wrote works as expected end-to-end.

## 🏁 Quick Start (macOS/Linux/Windows)

1. One-command setup with [uvx](https://docs.astral.sh/uv/guides/tools/):
```bash
# Run the setup command (interactive - will prompt for API key)
uvx --from git+https://github.com/nandatheguntupalli/operative webEvalAgent
```

2. The command will:
   - Display ASCII art and a welcome message
   - Check for and install required dependencies (npm, jq) if missing
   - Prompt you for your Operative API key
   - Validate your API key
   - Configure Cursor's MCP settings

3. Restart Cursor when prompted for the changes to take effect

4. The web-eval-agent will now be available in Cursor Agent Mode

## 🚨 Issues 

- For npm installation, the script uses Homebrew on macOS, apt-get/yum on Linux, and prompts for manual installation on Windows
- If jq can't be installed automatically, the script will continue without it (not critical for functionality)
- If you encounter API key validation issues, the installer will guide you through the process
- Any other issues? Feel free to open an Issue on this repo!

## 📋 Example MCP Server Output Report

```text
📊 Web Evaluation Report for http://localhost:5173 complete!
📝 Task: Test the API-key deletion flow by navigating to the API Keys section, deleting a key, and judging the UX.

🔍 Agent Steps
  📍 1. Navigate → http://localhost:5173
  📍 2. Click     "Login"        (button index 2)
  📍 3. Click     "API Keys"     (button index 4)
  📍 4. Click     "Create Key"   (button index 9)
  📍 5. Type      "Test API Key" (input index 2)
  📍 6. Click     "Done"         (button index 3)
  📍 7. Click     "Delete"       (button index 10)
  📍 8. Click     "Delete"       (confirm index 3)
  🏁 Flow tested successfully – UX felt smooth and intuitive.

🖥️ Console Logs (10)
  1. [debug] [vite] connecting…
  2. [debug] [vite] connected.
  3. [info]  Download the React DevTools …
     …

🌐 Network Requests (10)
  1. GET /src/pages/SleepingMasks.tsx                   304
  2. GET /src/pages/MCPRegistryRegistry.tsx             304
     …

⏱️ Chronological Timeline
  01:16:23.293 🖥️ Console [debug] [vite] connecting…
  01:16:23.303 🖥️ Console [debug] [vite] connected.
  01:16:23.312 ➡️ GET /src/pages/SleepingMasks.tsx
  01:16:23.318 ⬅️ 304 /src/pages/SleepingMasks.tsx
     …
  01:17:45.038 🤖 🏁 Flow finished – deletion verified
  01:17:47.038 🤖 📋 Conclusion repeated above
👁️  See the "Operative Control Center" dashboard for live logs.


---

Built with <3 @ [operative.sh](https://www.operative.sh)
