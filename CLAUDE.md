# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server that generates visual diagrams from Mermaid code. It integrates with Claude Code to provide diagram generation capabilities via the Mermaid CLI (`mmdc`).

## Prerequisites

- Node.js with npm
- Mermaid CLI: `npm install -g @mermaid-js/mermaid-cli`
- Python with MCP SDK: `pip install mcp`

## Development Setup

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install mcp

# Register with Claude Code (use absolute paths to venv Python and server script)
claude mcp add -s user mermaid-diagram '/absolute/path/to/venv/bin/python3' '/absolute/path/to/mermaid_mcp_server.py'

# Verify registration
claude mcp list

# Debug mode for troubleshooting
claude --mcp-debug
```

## Architecture

The server (`mermaid_mcp_server.py`) is a single-file MCP server implementation using `mcp.server` that provides:

**Tools:**
- `generate_diagram`: Renders Mermaid code to SVG/PNG/PDF using `mmdc` CLI
- `validate_mermaid`: Validates Mermaid syntax via regex pattern matching

**Resources:**
- `mermaid://syntax-guide`: Returns a syntax guide with common Mermaid examples

**Key functions:**
- `appears_to_be_mermaid_code()`: Regex-based validation against common Mermaid patterns (graph, sequenceDiagram, classDiagram, etc.)
- `extract_mermaid_code()`: Extracts Mermaid code from markdown code blocks
- `handle_call_tool()`: Main tool handler that invokes `mmdc` subprocess with timeout

**Diagram generation flow:**
1. Extract Mermaid code from input (handles code blocks)
2. Validate syntax patterns
3. Write to temp file
4. Execute `mmdc` with resolution/theme/background options
5. Save output to user-specified filename in current working directory
6. For SVG, modify transparent background in output

## Theme Handling

The server maps themes when calling `mmdc`:
- `default` and `dark` both use `mmdc -t dark`
- `forest` and `neutral` use their respective themes directly
