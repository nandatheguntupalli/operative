#!/bin/bash
echo "Clearing uv cache..."
uv cache clean
echo "Removing API key from environment..."
unset OPERATIVE_API_KEY
echo "Temporarily moving npm to test installation..."
NPM_PATH=$(which npm)
if [ ! -z "$NPM_PATH" ]; then sudo mv "$NPM_PATH" "${NPM_PATH}_backup"; echo "npm temporarily backed up"; fi
echo "Temporarily moving jq to test installation..."
JQ_PATH=$(which jq)
if [ ! -z "$JQ_PATH" ]; then sudo mv "$JQ_PATH" "${JQ_PATH}_backup"; echo "jq temporarily backed up"; fi
echo "Removing Cursor MCP configuration..."
rm -f ~/.cursor/mcp.json
echo "Cleanup complete! Now run: uvx --from git+https://github.com/nandatheguntupalli/operative webEvalAgent"
