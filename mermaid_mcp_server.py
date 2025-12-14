#!/usr/bin/env python3

# Setup Requirements:
# 1. Install MCP Python SDK (in a venv):
#    python3 -m venv venv
#    source venv/bin/activate
#    pip install mcp
# 2. Install Mermaid CLI:
#    npm install -g @mermaid-js/mermaid-cli
# 3. Add to Claude Code (use absolute paths to ensure it works from any project):
#    claude mcp add -s user mermaid-diagram '/path/to/venv/bin/python3' '/path/to/mermaid_mcp_server.py'
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


def sanitize_markdown_in_labels(code: str) -> str:
    """
    Sanitize text inside node labels to prevent mermaid from interpreting
    content as markdown lists (e.g., "1. Something" or "- Something").

    This replaces patterns that look like markdown lists inside quoted labels:
    - "1. Text" becomes "1: Text"
    - "- Text" becomes "– Text" (en-dash)
    - "<br/>" becomes newline character for proper line breaks
    """
    # Find all quoted strings (node labels) and sanitize them
    def sanitize_label(match):
        label = match.group(1)
        # Replace numbered list patterns: "1. " -> "1: "
        label = re.sub(r'(\d+)\. ', r'\1: ', label)
        # Replace dash list patterns: "- " -> "– " (en-dash)
        label = re.sub(r'^- ', '– ', label)
        label = re.sub(r'\n- ', '\n– ', label)
        # Replace <br/> with actual line break for mermaid
        label = label.replace('<br/>', '\\n')
        label = label.replace('<br>', '\\n')
        return f'["{label}"]'

    # Match node labels in square brackets with quotes: ["..."]
    code = re.sub(r'\["([^"]+)"\]', sanitize_label, code)

    return code

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
                        "enum": ["default", "dark", "forest", "neutral"],
                        "default": "default",
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
                        "default": "transparent",
                        "description": "Background color for the diagram (hex color, named color, or 'transparent')"
                    },
                    "file_name": {
                        "type": "string",
                        "description": "Name of the output file (without extension, will be added automatically based on format)"
                    }
                },
                "required": ["mermaid_code", "file_name"]
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
        theme = arguments.get("theme", "default")
        width = arguments.get("width", 1920)
        height = arguments.get("height", 1080)
        scale = arguments.get("scale", 2)
        background_color = arguments.get("backgroundColor", "transparent")
        file_name = arguments.get("file_name", "")
        
        if not mermaid_code:
            raise ValueError("No Mermaid code provided")
        
        if not file_name:
            raise ValueError("No file name provided")
        
        # Extract code from text if it contains code blocks
        extracted_code = extract_mermaid_code(mermaid_code)

        # Sanitize markdown patterns in labels to prevent rendering issues
        extracted_code = sanitize_markdown_in_labels(extracted_code)

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
                    "-w", str(width),    # Width
                    "-H", str(height),   # Height
                    "-s", str(scale),    # Scale factor
                    "--backgroundColor", background_color  # Background color
                ]

                # Handle dark theme styling with custom config for good contrast
                if theme == "default" or theme == "dark":
                    # Create a custom dark theme config with good contrast
                    import json
                    config_path = os.path.join(tmpdirname, "config.json")
                    dark_config = {
                        "theme": "base",
                        "themeVariables": {
                            "primaryColor": "#3b82f6",      # Blue boxes
                            "primaryTextColor": "#ffffff",   # White text on primary
                            "primaryBorderColor": "#60a5fa",
                            "secondaryColor": "#374151",     # Gray secondary
                            "secondaryTextColor": "#ffffff",
                            "secondaryBorderColor": "#4b5563",
                            "tertiaryColor": "#1f2937",      # Dark gray tertiary
                            "tertiaryTextColor": "#ffffff",
                            "background": "#000000",         # Black background
                            "mainBkg": "#1f2937",            # Dark gray box background
                            "textColor": "#f9fafb",          # Light text
                            "lineColor": "#6b7280",          # Gray lines
                            "nodeTextColor": "#ffffff",      # White node text
                            "nodeBorder": "#60a5fa",
                            "clusterBkg": "#000000",         # Black cluster background
                            "clusterBorder": "#374151",
                            "titleColor": "#f9fafb",
                            "edgeLabelBackground": "#1f2937",
                            "actorBkg": "#3b82f6",
                            "actorTextColor": "#ffffff",
                            "actorBorder": "#60a5fa",
                            "actorLineColor": "#6b7280",
                            "labelBoxBkgColor": "#1f2937",
                            "labelBoxBorderColor": "#4b5563",
                            "labelTextColor": "#f9fafb",
                            "noteBkgColor": "#fbbf24",       # Amber notes
                            "noteTextColor": "#000000",      # Black text on notes
                            "noteBorderColor": "#f59e0b"
                        }
                    }
                    with open(config_path, "w") as f:
                        json.dump(dark_config, f)
                    command.extend(["--configFile", config_path])
                else:
                    # Use the specified theme normally (forest, neutral, etc.)
                    command.extend(["-t", theme])
                
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
                            text=f"UPDATED VERSION: Failed to generate diagram. Error: {result.stderr}"
                        )
                    ]
                
                # Read the generated file and save to specified filename
                if os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        file_content = f.read()
                    
                    # Create the permanent filename with proper extension
                    permanent_filename = f"{file_name}.{output_format}"
                    permanent_path = os.path.join(os.getcwd(), permanent_filename)
                    
                    # Save to the user-specified filename with error handling
                    try:
                        with open(permanent_path, "wb") as f:
                            f.write(file_content)
                        
                        # Verify the file was actually written
                        if not os.path.exists(permanent_path):
                            raise Exception(f"File was not created at {permanent_path}")
                        
                        # Get actual file size for verification
                        actual_size = os.path.getsize(permanent_path)
                        if actual_size != len(file_content):
                            raise Exception(f"File size mismatch: expected {len(file_content)}, got {actual_size}")

                        # Auto-open the file on macOS
                        import platform
                        if platform.system() == "Darwin":
                            subprocess.run(["open", permanent_path], check=False)

                    except Exception as e:
                        return [
                            TextContent(
                                type="text",
                                text=f"Error saving file to {permanent_path}: {str(e)}"
                            )
                        ]
                    
                    if output_format == "svg":
                        # For SVG, handle transparent background by modifying the content
                        svg_content = file_content.decode('utf-8')
                        if background_color == "transparent":
                            # Remove background-color: white; from the SVG style
                            svg_content = svg_content.replace('background-color: white;', 'background-color: transparent;')
                            # Also save the corrected content
                            with open(permanent_path, "w", encoding="utf-8") as f:
                                f.write(svg_content)
                        
                        # For SVG, save the file AND return the content for embedding
                        return [
                            TextContent(
                                type="text",
                                text=f"Successfully generated SVG diagram and saved to: {permanent_path}\n\nWorking directory: {os.getcwd()}\nFile size: {len(svg_content.encode('utf-8'))} bytes\nFile exists: {os.path.exists(permanent_path)}\n\nSVG Content:\n\n{svg_content}"
                            )
                        ]
                    else:
                        # For binary formats (PNG, PDF), just provide the saved file path
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