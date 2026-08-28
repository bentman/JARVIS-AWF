"""JSON Schema for this AWF registry object kind."""

KIND = "LlmServers"
NAME = "default"
VERSION = "1.0.0"
ACCELERATORS = ("cpu", "gpu.cuda", "gpu.vulkan", "npu.qnn", "gpu.opencl.adreno")
ARCHIVES = ("tar_gz", "zip", "manual")

SCHEMA = {
    "type": "object",
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "additionalProperties": False,
    "properties": {
        "apiVersion": {"const": "awf/v1"},
        "kind": {"const": KIND},
        "metadata": {
            "type": "object",
            "required": ["name", "version"],
            "additionalProperties": True,
            "properties": {
                "name": {"const": NAME},
                "version": {"type": "string"},
                "digest": {"type": "string"},
            },
        },
        "spec": {
            "type": "object",
            "required": ["default_server", "servers"],
            "additionalProperties": False,
            "properties": {
                "default_server": {"type": "string", "minLength": 1},
                "servers": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "required": ["managed", "base_url", "openai_base_path", "provider", "health_paths"],
                        "additionalProperties": False,
                        "properties": {
                            "managed": {"type": "boolean"},
                            "base_url": {"type": "string", "minLength": 1},
                            "openai_base_path": {"type": "string", "minLength": 1},
                            "provider": {"type": "string", "minLength": 1},
                            "health_paths": {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1},
                            },
                            "api_key_secret_name": {"type": ["string", "null"]},
                            "launch": {"type": "object"},
                            "model_defaults": {"type": "object", "additionalProperties": {"type": "string"}},
                            "artifacts": {
                                "type": "object",
                                "additionalProperties": {
                                    "type": "object",
                                    "required": ["url", "archive", "binary", "accelerator"],
                                    "additionalProperties": False,
                                    "properties": {
                                        "url": {"type": "string", "minLength": 1},
                                        "archive": {"type": "string", "enum": list(ARCHIVES)},
                                        "binary": {"type": "string", "minLength": 1},
                                        "accelerator": {"type": "string", "enum": list(ACCELERATORS)},
                                        "launch": {"type": "object"},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}
