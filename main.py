#!/usr/bin/env python3
"""
Reader API MCP Server

This MCP server connects to the Readwise Reader API and exposes resources to retrieve document lists
based on specified time ranges, locations, or types.
"""

import os
import httpx
import logging
from dotenv import load_dotenv
from typing import Dict, Any, cast
from contextlib import asynccontextmanager
from dataclasses import dataclass
from mcp.server.fastmcp import FastMCP


# Set up logging
logger = logging.getLogger("reader-server")

# Reader API endpoints
READER_API_BASE_URL = "https://readwise.io/api/v3"
READER_AUTH_URL = "https://readwise.io/api/v2/auth/"


@dataclass
class ReaderContext:
    """Reader API Context"""
    access_token: str
    client: httpx.AsyncClient


@asynccontextmanager
async def reader_lifespan(_: FastMCP):
    """Manage the lifecycle of Reader API client"""
    # Get access token from environment variables
    load_dotenv()
    access_token = os.environ.get("READER_ACCESS_TOKEN")
    if not access_token:
        logger.error("READER_ACCESS_TOKEN environment variable is not set")
        raise ValueError("READER_ACCESS_TOKEN environment variable is not set")

    # Create HTTP client
    async with httpx.AsyncClient(
        base_url=READER_API_BASE_URL,
        headers={"Authorization": f"Token {access_token}"},
        timeout=30.0
    ) as client:
        # Provide context
        yield ReaderContext(access_token=access_token, client=client)


# Create MCP server
mcp = FastMCP(
    "reader-api",
    lifespan=reader_lifespan,
    dependencies=["httpx"]
)


def get_reader_context() -> ReaderContext:
    """Get Reader API context"""
    ctx = mcp.get_context()
    return cast(ReaderContext, ctx.request_context.lifespan_context)


def validate_list_params(location: str, after: str) -> Dict[str, str]:
    """
    Validate and filter list documents parameters.

    Args:
        location: The location parameter to validate
        after: The timestamp parameter to validate

    Returns:
        Dict containing valid parameters
    """
    valid_locations = {'new', 'later', 'shortlist', 'archive', 'feed'}
    params = {}

    if location in valid_locations:
        params['location'] = location
    else:
        logger.warning(f"Invalid location: {location}, parameter will be ignored")

    try:
        # Basic ISO 8601 format validation
        if 'T' in after and (after.endswith('Z') or '+' in after):
            params['updatedAfter'] = after
        else:
            logger.warning(f"Invalid ISO 8601 datetime: {after}, parameter will be ignored")
    except (TypeError, ValueError):
        logger.warning(f"Invalid datetime format: {after}, parameter will be ignored")

    return params


@mcp.resource("reader://documents/location={location};after={after}",
              mime_type="application/json")
async def list_documents(location: str, after: str) -> Dict[str, Any]:
    """
    List documents based on location (folder) and last modification time.

    Args:
        location: The location where documents are stored. Valid values are: new, later, shortlist, archive, feed
        after: ISO 8601 datetime to filter documents modified after this time

    Returns:
        A dict containing count, results list and pagination cursor
    """
    ctx = get_reader_context()
    logger.debug(f"list documents @{location} after {after}")

    try:
        params = validate_list_params(location, after)
        response = await ctx.client.get("/list/", params=params)
        response.raise_for_status()
        data = response.json()
        return data
    except Exception as e:
        logger.error(f"Error retrieving document list: {str(e)}")
        raise


if __name__ == "__main__":
    # Run server
    mcp.run()
