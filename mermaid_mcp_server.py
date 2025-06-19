#!/usr/bin/env python3

# Setup Requirements:
# 1. Install MCP Python SDK:
#    pip install mcp
# 2. Install Mermaid CLI:
#    npm install -g @mermaid-js/mermaid-cli
# 3. Add to Claude Code:
#    claude mcp add mermaid-diagram python '/path/to/mermaid_mcp_server.py'
#    # For user-level (global) config:
#    claude mcp add -s user mermaid-diagram python '/path/to/mermaid_mcp_server.py'
# 4. Verify it's working:
#    claude mcp list
#    claude --mcp-debug  # if troubleshooting needed

import asyncio
import os
import re
import subprocess
import tempfile
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent
from typing import Any

server = Server("mermaid-diagram")

def appears_to_be_mermaid_code(code: str) -> bool:
    """
    Basic Mermaid syntax validation.
    Checks if the code contains common Mermaid syntax patterns.
    """
    # Common Mermaid syntax patterns
    mermaid_patterns = [
        r'graph\s+[TBLR]?[DRLR]?',  # Graph declarations
        r'sequenceDiagram',  # Sequence diagrams
        r'classDiagram',  # Class diagrams
        r'stateDiagram-v2',  # State diagrams
        r'erDiagram',  # Entity Relationship diagrams
        r'pie\s*title',  # Pie charts
        r'gantt',  # Gantt charts
        r'flowchart\s+[TBLR]?[DRLR]?',  # Flowcharts
        r'-->|--[x]|==>',  # Various arrow types
        r'subgraph',  # Subgraph declarations
        r'participant',  # Sequence diagram participants
        r'class\s+\w+',  # Class definitions
        r'state\s+\w+',  # State definitions
    ]
    
    # Check if the code contains at least one Mermaid-like pattern
    # and doesn't contain obvious non-Mermaid patterns
    return (any(re.search(pattern, code, re.IGNORECASE) for pattern in mermaid_patterns) and
           not re.search(r'import\s+|def\s+|class\s*:', code))  # Not Python code

def extract_mermaid_code(text: str) -> str:
    """
    Extract Mermaid code from text, handling code blocks if present.
    """
    # First try to extract from code blocks
    code_block_matches = re.findall(r"```(?:\w*\n)?(.*?)```", text, re.DOTALL)
    
    if code_block_matches:
        # Return the first code block
        return code_block_matches[0].strip()
    
    # If no code blocks, return the text as-is
    return text.strip()

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available resources"""
    return [
        Resource(
            uri="mermaid://syntax-guide",
            name="Mermaid Syntax Guide",
            description="A guide to Mermaid diagram syntax and examples",
            mimeType="text/plain"
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read a resource"""
    if uri == "mermaid://syntax-guide":
        return """Mermaid Diagram Syntax Guide

Common Mermaid diagram types:

1. Flowchart:
flowchart TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Process]
    B -->|No| D[End]

2. Sequence Diagram:
sequenceDiagram
    participant A as Alice
    participant B as Bob
    A->>B: Hello Bob, how are you?
    B-->>A: Great!

3. Class Diagram:
classDiagram
    class Animal {
        +String name
        +eat()
    }
    Animal <|-- Dog

4. State Diagram:
stateDiagram-v2
    [*] --> Still
    Still --> [*]
    Still --> Moving

5. ER Diagram:
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains

For more syntax, visit: https://mermaid.js.org/
"""
    else:
        raise ValueError(f"Unknown resource: {uri}")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available tools"""
    return [
        Tool(
            name="generate_diagram",
            description="Generate a Mermaid diagram from code and return it as an SVG image",
            inputSchema={
                "type": "object",
                "properties": {
                    "mermaid_code": {
                        "type": "string",
                        "description": "Mermaid diagram code to render"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["svg", "png", "pdf"],
                        "default": "svg",
                        "description": "Output format for the diagram"
                    },
                    "theme": {
                        "type": "string",
                        "enum": ["default", "dark", "forest", "base"],
                        "default": "dark",
                        "description": "Theme to use for the diagram"
                    },
                    "width": {
                        "type": "integer",
                        "minimum": 800,
                        "maximum": 4000,
                        "default": 1920,
                        "description": "Width of the output image in pixels"
                    },
                    "height": {
                        "type": "integer",
                        "minimum": 600,
                        "maximum": 4000,
                        "default": 1080,
                        "description": "Height of the output image in pixels"
                    },
                    "scale": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": 4,
                        "default": 2,
                        "description": "Scale factor for higher resolution (1-4)"
                    },
                    "backgroundColor": {
                        "type": "string",
                        "default": "#0d1117",
                        "description": "Background color for the diagram (hex color, named color, or 'transparent')"
                    }
                },
                "required": ["mermaid_code"]
            }
        ),
        Tool(
            name="validate_mermaid",
            description="Validate Mermaid diagram syntax and provide feedback",
            inputSchema={
                "type": "object",
                "properties": {
                    "mermaid_code": {
                        "type": "string",
                        "description": "Mermaid diagram code to validate"
                    }
                },
                "required": ["mermaid_code"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """Handle tool calls"""
    if name == "generate_diagram":
        if not arguments:
            raise ValueError("generate_diagram tool requires arguments")
        
        mermaid_code = arguments.get("mermaid_code", "")
        output_format = arguments.get("format", "svg")
        theme = arguments.get("theme", "dark")
        width = arguments.get("width", 1920)
        height = arguments.get("height", 1080)
        scale = arguments.get("scale", 2)
        background_color = arguments.get("backgroundColor", "#0d1117")
        
        if not mermaid_code:
            raise ValueError("No Mermaid code provided")
        
        # Extract code from text if it contains code blocks
        extracted_code = extract_mermaid_code(mermaid_code)
        
        # Validate that it looks like Mermaid code
        if not appears_to_be_mermaid_code(extracted_code):
            return [
                TextContent(
                    type="text",
                    text="Warning: The provided code doesn't appear to contain valid Mermaid diagram syntax. Attempting to generate anyway..."
                )
            ]
        
        # Generate the diagram using mmdc
        try:
            with tempfile.TemporaryDirectory() as tmpdirname:
                input_path = os.path.join(tmpdirname, "input.mmd")
                output_path = os.path.join(tmpdirname, f"output.{output_format}")
                
                # Write the Mermaid code to a temporary file
                with open(input_path, "w") as f:
                    f.write(extracted_code)
                
                # Build the mmdc command with resolution parameters
                command = [
                    "mmdc",
                    "-q",  # Quiet mode
                    "-i", input_path,
                    "-o", output_path,
                    "-t", theme,
                    "-w", str(width),    # Width
                    "-H", str(height),   # Height
                    "-s", str(scale),    # Scale factor
                    "-b", background_color  # Background color
                ]
                
                # Execute the command with timeout
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30
                )
                
                if result.returncode != 0:
                    return [
                        TextContent(
                            type="text",
                            text=f"Failed to generate diagram. Error: {result.stderr}"
                        )
                    ]
                
                # Read the generated file and handle different formats
                if os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        file_content = f.read()
                    
                    if output_format == "svg":
                        # For SVG, return the content directly for embedding
                        return [
                            TextContent(
                                type="text",
                                text=f"Successfully generated SVG diagram:\n\n{file_content.decode('utf-8')}"
                            )
                        ]
                    else:
                        # For binary formats (PNG, PDF), save to a permanent location and provide path
                        import time
                        timestamp = int(time.time())
                        permanent_filename = f"mermaid_diagram_{timestamp}.{output_format}"
                        permanent_path = os.path.join(os.getcwd(), permanent_filename)
                        
                        # Copy the file to permanent location
                        with open(permanent_path, "wb") as f:
                            f.write(file_content)
                        
                        return [
                            TextContent(
                                type="text",
                                text=f"Successfully generated {output_format.upper()} diagram!\n\nFile saved to: {permanent_path}\n\nFile size: {len(file_content)} bytes\n\nTo view the image, open the file at the path above in your image viewer or web browser."
                            )
                        ]
                else:
                    return [
                        TextContent(
                            type="text",
                            text="Failed to generate diagram: Output file not created"
                        )
                    ]
                    
        except subprocess.TimeoutExpired:
            return [
                TextContent(
                    type="text",
                    text="Diagram generation timed out. The diagram might be too complex."
                )
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"An error occurred while generating the diagram: {str(e)}"
                )
            ]
            
    elif name == "validate_mermaid":
        if not arguments:
            raise ValueError("validate_mermaid tool requires arguments")
        
        mermaid_code = arguments.get("mermaid_code", "")
        
        if not mermaid_code:
            return [
                TextContent(
                    type="text",
                    text="No Mermaid code provided for validation"
                )
            ]
        
        # Extract code from text if it contains code blocks
        extracted_code = extract_mermaid_code(mermaid_code)
        
        # Validate the syntax
        if not extracted_code.strip():
            return [
                TextContent(
                    type="text",
                    text="Validation failed: Empty code block found"
                )
            ]
        
        if appears_to_be_mermaid_code(extracted_code):
            return [
                TextContent(
                    type="text",
                    text="Validation passed: The code appears to contain valid Mermaid diagram syntax"
                )
            ]
        else:
            return [
                TextContent(
                    type="text",
                    text="Validation warning: The code doesn't appear to contain valid Mermaid diagram syntax. Please check for common patterns like 'graph', 'sequenceDiagram', 'classDiagram', etc."
                )
            ]
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the server using stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="simple-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())