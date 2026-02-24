#!/usr/bin/env python3
import json
import os

from websocket import WebSocket, create_connection
from dotenv import load_dotenv

load_dotenv()
WS_URL = "wss://api.openai.com/v1/responses"
MODEL = "gpt-5-nano-2025-08-07"


def send_response_create(
    ws: WebSocket,
    input_items,
    previous_response_id=None,
    store=False,
    tools=None,
    instructions=None,
):
    payload = {
        "type": "response.create",
        "model": MODEL,
        "store": store,
        "input": input_items,
        "tools": tools or [],
    }
    if previous_response_id:
        payload["previous_response_id"] = previous_response_id
    if instructions:
        payload["instructions"] = instructions

    ws.send(json.dumps(payload))


def parse_completed_response(response_obj, streamed_text_parts):
    text_parts = []
    function_calls = []

    for item in response_obj.get("output", []):
        item_type = item.get("type")

        if item_type == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text = part.get("text", "")
                    if text:
                        text_parts.append(text)

        elif item_type == "function_call":
            raw_args = item.get("arguments", "")
            try:
                if isinstance(raw_args, str) and raw_args:
                    parsed_args = json.loads(raw_args)
                else:
                    parsed_args = raw_args
            except json.JSONDecodeError:
                parsed_args = raw_args

            function_calls.append(
                {
                    "call_id": item.get("call_id"),
                    "name": item.get("name"),
                    "arguments": parsed_args,
                }
            )

    final_text = "".join(text_parts).strip() or "".join(streamed_text_parts).strip()
    return {
        "response_id": response_obj.get("id"),
        "text": final_text,
        "function_calls": function_calls,
    }


def read_one_response(ws: WebSocket) -> dict:
    streamed_text_parts = []

    while True:
        event = json.loads(ws.recv())
        event_type = event.get("type")

        if event_type == "response.output_text.delta":
            delta = event.get("delta", "")
            if delta:
                streamed_text_parts.append(delta)
                print(delta, end="", flush=True)

        elif event_type == "response.completed":
            print()
            return parse_completed_response(
                event.get("response", {}), streamed_text_parts
            )

        elif event_type == "error":
            error = event.get("error", {})
            code = error.get("code", "unknown_error")
            message = error.get("message", "No error message")
            raise RuntimeError(f"{code}: {message}")


def get_horoscope(sign: str) -> str:
    return f"{sign}: Next Tuesday you will befriend a baby otter."


def run_tool_call_example(ws: WebSocket):
    tools = [
        {
            "type": "function",
            "name": "get_horoscope",
            "description": "Get today's horoscope for an astrological sign.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sign": {
                        "type": "string",
                        "description": "An astrological sign like Taurus or Aquarius",
                    }
                },
                "required": ["sign"],
            },
        }
    ]

    send_response_create(
        ws,
        input_items=[
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "What is my horoscope? I am an Aquarius.",
                    }
                ],
            }
        ],
        tools=tools,
        store=False,
    )

    first = read_one_response(ws)
    print("\nTool-call turn 1 parsed:")
    print(json.dumps(first, indent=2))

    if not first["function_calls"]:
        print("No function call requested by model.")
        return

    tool_outputs = []
    for call in first["function_calls"]:
        if call["name"] != "get_horoscope":
            continue

        args = call.get("arguments") or {}
        sign = args.get("sign") if isinstance(args, dict) else None
        if not sign:
            sign = "Aquarius"

        horoscope = get_horoscope(sign)
        tool_outputs.append(
            {
                "type": "function_call_output",
                "call_id": call["call_id"],
                "output": json.dumps({"horoscope": horoscope}),
            }
        )

    if not tool_outputs:
        print("Model called an unexpected function; nothing to execute.")
        return

    send_response_create(
        ws,
        previous_response_id=first["response_id"],
        input_items=tool_outputs,
        tools=tools,
        instructions="Respond only with a horoscope generated by a tool.",
        store=False,
    )
    second = read_one_response(ws)
    print("\nTool-call turn 2 parsed:")
    print(json.dumps(second, indent=2))


def main():
    api_key = os.environ["OPENAI_API_KEY"]

    ws = create_connection(
        WS_URL,
        header=[f"Authorization: Bearer {api_key}"],
    )

    try:
        # send_response_create(
        #     ws,
        #     input_items=[
        #         {
        #             "type": "message",
        #             "role": "user",
        #             "content": [
        #                 {
        #                     "type": "input_text",
        #                     "text": "Give me 3 short bullets about WebSocket mode.",
        #                 }
        #             ],
        #         }
        #     ],
        #     store=False,
        # )
        # first = read_one_response(ws)
        # print("\nParsed turn 1:")
        # print(json.dumps(first, indent=2))

        # send_response_create(
        #     ws,
        #     previous_response_id=first["response_id"],
        #     input_items=[
        #         {
        #             "type": "message",
        #             "role": "user",
        #             "content": [
        #                 {
        #                     "type": "input_text",
        #                     "text": "Now summarize that in one sentence.",
        #                 }
        #             ],
        #         }
        #     ],
        #     store=False,
        # )
        # second = read_one_response(ws)
        # print("\nParsed turn 2:")
        # print(json.dumps(second, indent=2))

        print("\n--- Tool call example ---")
        run_tool_call_example(ws)
    finally:
        ws.close()


if __name__ == "__main__":
    main()
