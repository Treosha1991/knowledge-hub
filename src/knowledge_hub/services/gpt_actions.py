from __future__ import annotations

from urllib.parse import urljoin

from .public_urls import get_public_base_url


def build_gpt_actions_schema(config, *, server_url: str | None = None) -> dict:
    base_url = (server_url or get_public_base_url(config) or "").rstrip("/")
    if not base_url:
        base_url = "https://your-knowledge-hub-domain.example"

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Knowledge Hub GPT Actions",
            "version": "1.0.0",
            "description": (
                "Minimal Knowledge Hub action schema for reading project handoffs and "
                "writing session summaries back into the archive."
            ),
        },
        "servers": [
            {
                "url": base_url,
                "description": "Knowledge Hub production server",
            }
        ],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "API token",
                }
            },
            "schemas": {
                "ProjectSummary": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string"},
                        "name": {"type": "string"},
                        "workspace_slug": {"type": "string"},
                        "status": {"type": "string"},
                        "current_goal": {"type": ["string", "null"]},
                        "updated_at": {"type": ["string", "null"]},
                    },
                    "required": ["slug", "name", "workspace_slug", "status"],
                },
                "SessionLogIngest": {
                    "type": "object",
                    "properties": {
                        "workspace_slug": {"type": "string"},
                        "project_slug": {"type": "string"},
                        "source": {"type": "string"},
                        "task": {"type": "string"},
                        "summary": {"type": "string"},
                        "actions_taken": {"type": "array", "items": {"type": "string"}},
                        "files_touched": {"type": "array", "items": {"type": "string"}},
                        "blockers": {"type": "array", "items": {"type": "string"}},
                        "next_step": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["project_slug", "source", "task", "summary"],
                },
            },
        },
        "security": [{"bearerAuth": []}],
        "paths": {
            "/api/gpt-actions/projects": {
                "get": {
                    "operationId": "listKnowledgeHubProjects",
                    "summary": "List accessible projects",
                    "description": "Returns projects available to the current Knowledge Hub API token.",
                    "x-openai-isConsequential": False,
                    "responses": {
                        "200": {
                            "description": "Project list",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ok": {"type": "boolean"},
                                            "projects": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/ProjectSummary"},
                                            },
                                        },
                                        "required": ["ok", "projects"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/gpt-actions/projects/{project_slug}/ready-for-next-chat": {
                "get": {
                    "operationId": "getKnowledgeHubReadyForNextChat",
                    "summary": "Get project handoff",
                    "description": "Returns the latest compact handoff and context fields for a project.",
                    "x-openai-isConsequential": False,
                    "parameters": [
                        {
                            "name": "project_slug",
                            "in": "path",
                            "required": True,
                            "description": "Project slug to read from Knowledge Hub.",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Ready-for-next-chat payload",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ok": {"type": "boolean"},
                                            "project": {"type": "object"},
                                            "text": {"type": "string"},
                                        },
                                        "required": ["text"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/gpt-actions/session-log": {
                "post": {
                    "operationId": "ingestKnowledgeHubSessionLog",
                    "summary": "Save session summary",
                    "description": "Writes a finished AI session summary into Knowledge Hub and refreshes project exports.",
                    "x-openai-isConsequential": True,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/SessionLogIngest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Ingest result",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "ok": {"type": "boolean"},
                                            "project_slug": {"type": ["string", "null"]},
                                            "imported_count": {"type": "integer"},
                                            "skipped_duplicates": {"type": "integer"},
                                            "ready_for_next_chat_url": {"type": ["string", "null"]},
                                        },
                                        "required": ["ok", "imported_count", "skipped_duplicates"],
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
    }


def build_gpt_actions_setup_guide(config, *, server_url: str | None = None) -> dict:
    base_url = (server_url or get_public_base_url(config) or "").rstrip("/")
    if not base_url:
        base_url = "https://your-knowledge-hub-domain.example"

    schema_url = urljoin(base_url + "/", "api/gpt-actions/openapi.json")
    token_ui_url = urljoin(base_url + "/", "settings/api-tokens/")
    setup_url = urljoin(base_url + "/", "gpt-actions/setup")

    return {
        "base_url": base_url,
        "schema_url": schema_url,
        "token_ui_url": token_ui_url,
        "setup_url": setup_url,
        "authentication": {
            "type": "API key",
            "mode": "Bearer",
            "token_value_hint": "Paste the raw khp_... token value without adding the word Bearer yourself.",
        },
        "actions": [
            {
                "operation_id": "listKnowledgeHubProjects",
                "purpose": "Lets the GPT discover which project slugs are available.",
            },
            {
                "operation_id": "getKnowledgeHubReadyForNextChat",
                "purpose": "Fetches the latest short handoff before the GPT starts project work.",
            },
            {
                "operation_id": "ingestKnowledgeHubSessionLog",
                "purpose": "Saves the finished session summary back into Knowledge Hub.",
            },
        ],
        "builder_steps": [
            "Open the GPT editor and create or edit your custom GPT.",
            "Open the Actions section and choose Create new action.",
            "Choose API key authentication and select Bearer mode.",
            "Paste the raw Knowledge Hub API token value from the API Tokens page.",
            "Import the OpenAPI schema from the schema URL below.",
            "Test reading a project handoff first, then test writing one session log.",
        ],
        "notes": [
            "OpenAI supports API key authentication with Basic, Bearer, or Custom header modes for GPT Actions.",
            "GPT Actions can import an OpenAPI schema from a URL.",
            "Custom headers are not supported in GPT Actions production, so Bearer auth is the safest path here.",
            "Public GPTs with actions need a privacy policy URL later, but that is not required for this internal step.",
        ],
        "instruction_template": (
            "Before starting project work, call getKnowledgeHubReadyForNextChat with the project slug. "
            "Use the returned text as the current source of truth. When the work is complete, call "
            "ingestKnowledgeHubSessionLog with a compact session summary JSON."
        ),
    }


def render_gpt_actions_setup_text(setup: dict) -> str:
    lines = [
        "Knowledge Hub GPT Actions Setup",
        f"Base URL: {setup['base_url']}",
        f"Schema URL: {setup['schema_url']}",
        f"Token UI: {setup['token_ui_url']}",
        "",
        f"Authentication: {setup['authentication']['type']} / {setup['authentication']['mode']}",
        setup["authentication"]["token_value_hint"],
        "",
        "Builder steps:",
    ]
    for index, item in enumerate(setup["builder_steps"], start=1):
        lines.append(f"{index}. {item}")

    lines.extend(
        [
            "",
            "Suggested GPT instruction:",
            setup["instruction_template"],
            "",
            "Actions:",
        ]
    )
    for item in setup["actions"]:
        lines.append(f"- {item['operation_id']}: {item['purpose']}")

    return "\n".join(lines)
