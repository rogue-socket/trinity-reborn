"""Local OpenAI-compatible test stub for the end-to-end smoke check."""

import json

from fastapi import FastAPI, Request


app = FastAPI()


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> dict:
    request_body = await request.json()
    generation_request = json.loads(request_body["messages"][-1]["content"])
    entity_map = []
    for entity in generation_request["entities_to_fictionalize"]:
        source_type = entity["source_type"]
        fictional_type = "place" if source_type in {"city_or_locality", "country"} else "faction"
        entity_map.append({
            "source_entity_id": entity["entity_id"],
            "fictional_name": f"Fictional {entity['entity_id']}",
            "fictional_type": fictional_type,
            "description": "A wholly fictional fixture detail.",
        })
    characters = [
        {
            "source_entity_id": character["source_entity_id"],
            "name": f"Character {character['source_entity_id']}",
            "goals": ["Protect a fictional community"],
            "fears": ["Losing trust"],
            "personality": ["resilient"],
            "emotion_state": {"primary": "determined", "secondary": "wary"},
        }
        for character in generation_request["characters_to_create"]
    ]
    content = json.dumps({"world_name": "The Lantern Coast", "entity_map": entity_map, "characters": characters})
    return {
        "id": "chatcmpl_test",
        "object": "chat.completion",
        "created": 0,
        "model": "gpt-5.6-sol",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
