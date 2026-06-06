You can use Anthropic's SDK or curl commands to send requests to the
Gemini Enterprise Agent Platform endpoint using the following model names:

- For Claude Opus 4.8, use `claude-opus-4-8`
- For Claude Opus 4.7, use `claude-opus-4-7`
- For Claude Opus 4.6, use `claude-opus-4-6`
- For Claude Sonnet 4.6, use `claude-sonnet-4-6`
- For Claude Opus 4.5, use `claude-opus-4-5`
- For Claude Opus 4.1, use `claude-opus-4-1`
- For Claude Opus 4, use `claude-opus-4`
- For Claude Sonnet 4.5, use `claude-sonnet-4-5`
- For Claude Sonnet 4, use `claude-sonnet-4`
- For Claude 3.7 Sonnet, use `claude-3-7-sonnet`
- For Claude 3.5 Sonnet v2, use `claude-3-5-sonnet-v2`
- For Claude Haiku 4.5, use `claude-haiku-4-5`
- For Claude 3.5 Haiku, use `claude-3-5-haiku`
- For Claude 3.5 Sonnet, use `claude-3-5-sonnet`
- For Claude 3 Opus, use `claude-3-opus`
- For Claude 3 Haiku, use `claude-3-haiku`

> [!NOTE]
> **Note:** The maximum allowed image file size is 5 MB and you can include up to 100 images in one request.

### Before you begin

Anthropic enforces policies that prohibit certain resellers from reselling their
products. If your Google Cloud billing account is managed by a prohibited
reseller, you will be unable to accept the Terms of Service or enable Claude
models. If this occurs, please contact your reseller directly.

> [!NOTE]
> **Note:** If enabling Claude models using Marketplace within an Assured Workloads boundary, you may be required to create an exception for `cloudcommerceconsumerprocurement.googleapis.com` and `commerceagreement.googleapis.com`. For more information on the exception process, see [Add violation exceptions](https://docs.cloud.google.com/assured-workloads/docs/monitor-folder#exception).

To use the Anthropic Claude models with Gemini Enterprise Agent Platform, you must perform the
following steps. The Agent Platform API (`aiplatform.googleapis.com`) must
be enabled to use Gemini Enterprise Agent Platform. If you already have an existing project with
the Agent Platform API enabled, you can use that project instead of creating
a new project.

Make sure you have the required permissions to enable and use partner models.
For more information, see [Grant the required permissions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#grant-permissions).

1. Go to one of the following Model Garden model cards, then click **Enable** :
   - [Go to the Claude Opus 4.8 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4-8)
   - [Go to the Claude Opus 4.7 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4-7)
   - [Go to the Claude Opus 4.6 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4-6)
   - [Go to the Claude Sonnet 4.6 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-sonnet-4-6)
   - [Go to the Claude Opus 4.5 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4-5)
   - [Go to the Claude Opus 4.1 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4-1)
   - [Go to the Claude Opus 4 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-opus-4)
   - [Go to the Claude Sonnet 4.5 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-sonnet-4-5)
   - [Go to the Claude Sonnet 4 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-sonnet-4)
   - [Go to the Claude Haiku 4.5 model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-haiku-4-5)
   - [Go to the Claude 3.5 Haiku model card](https://console.cloud.google.com/agent-platform/publishers/anthropic/model-garden/claude-3-5-haiku)

Anthropic recommends that you enable 30-day logging of your prompt and
completion activity to record any model misuse. To enable logging, see [Log
requests and responses](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/request-response-logging).

### Use the Anthropic SDK

You can make API requests to the Anthropic Claude models using the [Anthropic
Claude SDK](https://pypi.org/project/anthropic/). To learn more, see the
following:

- [Claude messages API reference](https://docs.anthropic.com/claude/reference/messages_post)
- [Anthropic Python API library](https://github.com/anthropics/anthropic-sdk-python)
- [Anthropic Gemini Enterprise Agent Platform TypeScript API Library](https://github.com/anthropics/anthropic-sdk-typescript/tree/main/packages/vertex-sdk)

#### Make a streaming call to a Claude model using the Anthropic Vertex SDK

The following code sample uses the Anthropic Vertex SDK to perform a streaming
call to a Claude model.

### Python

To learn how to install or update the Vertex AI SDK for Python, see [Install the Vertex AI SDK for Python](https://docs.cloud.google.com/vertex-ai/docs/start/use-vertex-ai-python-sdk).

For more information, see the
[Python API reference documentation](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest).

The following sample uses regional endpoints. To use the multi-region or global endpoint, see [Specify the multi-region endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#multi-region) or [Specify the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).

    # TODO(developer): Vertex AI SDK - uncomment below & run
    # pip3 install --upgrade --user google-cloud-aiplatform
    # gcloud auth application-default login
    # pip3 install -U 'anthropic[vertex]'

    # TODO(developer): Update and un-comment below line
    # PROJECT_ID = "your-project-id"

    from anthropic import AnthropicVertex

    client = AnthropicVertex(project_id=PROJECT_ID, region="us-east5")
    result = []

    with client.messages.stream(
        model="claude-3-5-sonnet-v2@20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": "Send me a recipe for banana bread.",
            }
        ],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            result.append(text)

    # Example response:
    # Here's a simple recipe for delicious banana bread:
    # Ingredients:
    # - 2-3 ripe bananas, mashed
    # - 1/3 cup melted butter
    # ...
    # ...
    # 8. Bake for 50-60 minutes, or until a toothpick inserted into the center comes out clean.
    # 9. Let cool in the pan for a few minutes, then remove and cool completely on a wire rack.

#### Make a unary call to a Claude model using the Anthropic Vertex SDK

The following code sample uses the Anthropic Vertex SDK to perform a unary call
to a Claude model.

### Python

To learn how to install or update the Vertex AI SDK for Python, see [Install the Vertex AI SDK for Python](https://docs.cloud.google.com/vertex-ai/docs/start/use-vertex-ai-python-sdk).

For more information, see the
[Python API reference documentation](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest).

The following sample uses regional endpoints. To use the multi-region or global endpoint, see [Specify the multi-region endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#multi-region) or [Specify the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).

    # TODO(developer): Vertex AI SDK - uncomment below & run
    # pip3 install --upgrade --user google-cloud-aiplatform
    # gcloud auth application-default login
    # pip3 install -U 'anthropic[vertex]'

    # TODO(developer): Update and un-comment below line
    # PROJECT_ID = "your-project-id"

    from anthropic import AnthropicVertex

    client = AnthropicVertex(project_id=PROJECT_ID, region="us-east5")
    message = client.messages.create(
        model="claude-3-5-sonnet-v2@20241022",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": "Send me a recipe for banana bread.",
            }
        ],
    )
    print(message.model_dump_json(indent=2))
    # Example response:
    # {
    #   "id": "msg_vrtx_0162rhgehxa9rvJM5BSVLZ9j",
    #   "content": [
    #     {
    #       "text": "Here's a simple recipe for delicious banana bread:\n\nIngredients:\n- 2-3 ripe bananas...
    #   ...

### Use a curl command

You can use a curl command to make a request to the Gemini Enterprise Agent Platform endpoint.
The curl command specifies which supported Claude model you want to use.

The following topic shows you how to create a curl command and includes a sample
curl command.

### REST

To test a text prompt by using the Agent Platform API, send a POST request to the
publisher model endpoint.
The following sample uses regional endpoints. To use the multi-region or global endpoint, see [Specify the multi-region endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#multi-region) or [Specify the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).


Before using any of the request data,
make the following replacements:

- <var class="edit" scope="LOCATION" translate="no">LOCATION</var>: A [region](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude#regions) that supports Anthropic Claude models. To use the global endpoint, see [Specify
  the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).
- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The [model name](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude#model-list) you want to use.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. Claude models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="STREAM" translate="no">STREAM</var>: A boolean that specifies whether the response is streamed or not. Stream your response to reduce the end-use latency perception. Set to `true` to stream the response and `false` to return the response all at once.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_TOKENS" translate="no">MAX_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately 3.5 characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.
- <var class="edit" scope="TOP_P" translate="no">TOP_P</var> (Optional): Top-P changes how the model selects tokens for output. Tokens are selected from the most probable to least probable until the sum of their probabilities equals the top-P value. For example, if tokens A, B, and C have a probability of 0.3, 0.2, and 0.1 and the top-P value is `0.5`, then the model will select either A or B as the next token by using temperature and excludes C as a candidate.

  Specify a lower value for less random responses and a higher value for more
  random responses.
- <var class="edit" scope="TOP_K" translate="no">TOP_K</var>(Optional): Top-K changes how the model selects tokens for output. A top-K of `1` means the next selected token is the most probable among all tokens in the model's vocabulary (also called greedy decoding), while a top-K of `3` means that the next token is selected from among the three most probable tokens by using temperature.

  For each token selection step, the top-K tokens with the highest
  probabilities are sampled. Then tokens are further filtered based on top-P with
  the final token selected using temperature sampling.

  Specify a lower value for less random responses and a higher value for more
  random responses.
- <var class="edit" scope="THINKING_TYPE" translate="no">TYPE</var>: For Claude 3.7 Sonnet and later Claude models, to enable extended thinking mode, specify `enabled`.
- <var class="edit" scope="THINKING_BUDGET" translate="no">BUDGET_TOKENS</var>: If you enable extended thinking, you must specify the number of tokens that the model can use for its internal reasoning as part of the output. Larger budgets can enable more thorough analysis for complex problems and improve response quality. You must specify a value greater than or equal to `1024` but less than `MAX_TOKENS`.


HTTP method and URL:

```
POST https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:streamRawPredict
```


Request JSON body:

```
{
  "anthropic_version": "vertex-2023-10-16",
  "messages": [
   {
    "role": "ROLE",
    "content": "CONTENT"
   }],
  "max_tokens": MAX_TOKENS,
  "stream": STREAM,
  "thinking": {
    "type": "TYPE",
    "budget_tokens": BUDGET_TOKENS
  }
}
```

To send your request, choose one of these options:

#### curl

> [!NOTE]
> **Note:** The following command assumes that you have logged in to the `gcloud` CLI with your user account by running [`gcloud init`](https://docs.cloud.google.com/sdk/gcloud/reference/init) or [`gcloud auth login`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login) , or by using [Cloud Shell](https://docs.cloud.google.com/shell/docs), which automatically logs you into the `gcloud` CLI . You can check the currently active account by running [`gcloud auth list`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list).


Save the request body in a file named `request.json`,
and execute the following command:

```
curl -X POST \
     -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "Content-Type: application/json; charset=utf-8" \
     -d @request.json \
     "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:streamRawPredict"
```

#### PowerShell

> [!NOTE]
> **Note:** The following command assumes that you have logged in to the `gcloud` CLI with your user account by running [`gcloud init`](https://docs.cloud.google.com/sdk/gcloud/reference/init) or [`gcloud auth login`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login) . You can check the currently active account by running [`gcloud auth list`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list).


Save the request body in a file named `request.json`,
and execute the following command:

```
$cred = gcloud auth print-access-token
$headers = @{ "Authorization" = "Bearer $cred" }

Invoke-WebRequest `
    -Method POST `
    -Headers $headers `
    -ContentType: "application/json; charset=utf-8" `
    -InFile request.json `
    -Uri "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:streamRawPredict" | Select-Object -Expand Content
```

You should receive a JSON response similar to the following.

#### Response

```
{
  "id":"msg_012NDLxqh6LsztWCU7zTb14C",
  "type":"message",
  "role":"assistant",
  "content":[{
    "type":"text",
    "text":"Hello! Nice to meet you."
  }],
  "model":"claude-2.1",
  "stop_reason":"end_turn",
  "stop_sequence":null,
  "usage":{
    "input_tokens":11,
    "output_tokens":11
  }
}
```

#### Example curl command

    MODEL_ID="MODEL"
    LOCATION="us-central1"
    PROJECT_ID="PROJECT_ID"

    curl \
    -X POST \
    -H "Authorization: Bearer $(gcloud auth print-access-token)" \
    -H "Content-Type: application/json" \
    https://${LOCATION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${LOCATION}/publishers/anthropic/models/${MODEL_ID}:streamRawPredict -d \
    '{
      "anthropic_version": "vertex-2023-10-16",
      "messages": [{
        "role": "user",
        "content": "Hello!"
      }],
      "max_tokens": 50,
      "stream": true}'

### Tool use (function calling)

The Anthropic Claude models support tools and function calling to enhance a
model's capabilities. For more information, see the
[Tool use overview](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) in the Anthropic documentation. Claude models on Gemini Enterprise Agent Platform support Client tools, but Server tools are not supported.

The following samples demonstrate how to use tools by using an SDK or curl
command. The samples search for nearby restaurants in San Francisco that are
open.

### Python

To learn how to install or update the Vertex AI SDK for Python, see [Install the Vertex AI SDK for Python](https://docs.cloud.google.com/vertex-ai/docs/start/use-vertex-ai-python-sdk).

For more information, see the
[Python API reference documentation](https://docs.cloud.google.com/python/docs/reference/aiplatform/latest).

The following sample uses regional endpoints. To use the multi-region or global endpoint, see [Specify the multi-region endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#multi-region) or [Specify the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).

    # TODO(developer): Vertex AI SDK - uncomment below & run
    # pip3 install --upgrade --user google-cloud-aiplatform
    # gcloud auth application-default login
    # pip3 install -U 'anthropic[vertex]'
    from anthropic import AnthropicVertex

    # TODO(developer): Update and un-comment below line
    # PROJECT_ID = "your-project-id"

    client = AnthropicVertex(project_id=PROJECT_ID, region="us-east5")
    message = client.messages.create(
        model="claude-3-5-sonnet-v2@20241022",
        max_tokens=1024,
        tools=[
            {
                "name": "text_search_places_api",
                "description": "returns information about a set of places based on a string",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "textQuery": {
                            "type": "string",
                            "description": "The text string on which to search",
                        },
                        "priceLevels": {
                            "type": "array",
                            "description": "Price levels to query places, value can be one of [PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE]",
                        },
                        "openNow": {
                            "type": "boolean",
                            "description": "whether those places are open for business.",
                        },
                    },
                    "required": ["textQuery"],
                },
            }
        ],
        messages=[
            {
                "role": "user",
                "content": "What are some affordable and good Italian restaurants open now in San Francisco??",
            }
        ],
    )
    print(message.model_dump_json(indent=2))
    # Example response:
    # {
    #   "id": "msg_vrtx_018pk1ykbbxAYhyWUdP1bJoQ",
    #   "content": [
    #     {
    #       "text": "To answer your question about affordable and good Italian restaurants
    #       that are currently open in San Francisco....
    # ...

### REST

The following sample uses regional endpoints. To use the multi-region or global endpoint, see [Specify the multi-region endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#multi-region) or [Specify the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).


Before using any of the request data,
make the following replacements:

- <var class="edit" scope="LOCATION" translate="no">LOCATION</var>: A [region](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude#regions) that supports Anthropic Claude models. To use the global endpoint, see [Specify
  the global endpoint](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/use-partner-models#global).
- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The [model name](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/claude/use-claude#model-list) to use.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. Claude models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="STREAM" translate="no">STREAM</var>: A boolean that specifies whether the response is streamed or not. Stream your response to reduce the end-use latency perception. Set to `true` to stream the response and `false` to return the response all at once.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_TOKENS" translate="no">MAX_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately 3.5 characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.


HTTP method and URL:

```
POST https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:rawPredict
```


Request JSON body:

```
{
  "anthropic_version": "vertex-2023-10-16",
  "max_tokens": MAX_TOKENS,
  "stream": STREAM,
  "tools": [
    {
      "name": "text_search_places_api",
      "description": "Returns information about a set of places based on a string",
      "input_schema": {
        "type": "object",
        "properties": {
          "textQuery": {
            "type": "string",
            "description": "The text string on which to search"
          },
          "priceLevels": {
            "type": "array",
            "description": "Price levels to query places, value can be one of [PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE]",
          },
          "openNow": {
            "type": "boolean",
            "description": "Describes whether a place is open for business at
            the time of the query."
          },
        },
        "required": ["textQuery"]
      }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": "What are some affordable and good Italian restaurants that are open now in San Francisco??"
    }
  ]
}
```

To send your request, choose one of these options:

#### curl

> [!NOTE]
> **Note:** The following command assumes that you have logged in to the `gcloud` CLI with your user account by running [`gcloud init`](https://docs.cloud.google.com/sdk/gcloud/reference/init) or [`gcloud auth login`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login) , or by using [Cloud Shell](https://docs.cloud.google.com/shell/docs), which automatically logs you into the `gcloud` CLI . You can check the currently active account by running [`gcloud auth list`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list).


Save the request body in a file named `request.json`,
and execute the following command:

```
curl -X POST \
     -H "Authorization: Bearer $(gcloud auth print-access-token)" \
     -H "Content-Type: application/json; charset=utf-8" \
     -d @request.json \
     "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:rawPredict"
```

#### PowerShell

> [!NOTE]
> **Note:** The following command assumes that you have logged in to the `gcloud` CLI with your user account by running [`gcloud init`](https://docs.cloud.google.com/sdk/gcloud/reference/init) or [`gcloud auth login`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/login) . You can check the currently active account by running [`gcloud auth list`](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list).


Save the request body in a file named `request.json`,
and execute the following command:

```
$cred = gcloud auth print-access-token
$headers = @{ "Authorization" = "Bearer $cred" }

Invoke-WebRequest `
    -Method POST `
    -Headers $headers `
    -ContentType: "application/json; charset=utf-8" `
    -InFile request.json `
    -Uri "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/publishers/anthropic/models/MODEL:rawPredict" | Select-Object -Expand Content
```

You should receive a JSON response similar to the following.

#### Response

```
{
  "id": "msg_vrtx_01ErR7VMNQdnvDt3n7Nmc4ER",
  "type": "message",
  "role": "assistant",
  "model": "claude-3-opus-20240229",
  "content": [
    {
      "type": "text",
      "text": "\nTo find affordable and good Italian restaurants that are currently open in San Francisco, the text_search_places_api tool seems most relevant. \n\nThe required textQuery parameter can be inferred as \"Italian restaurants in San Francisco\", since the user specified Italian restaurants and the location of San Francisco.\n\nTwo optional parameters are also relevant:\nopenNow - this should be set to true, since the user specified they want restaurants open now\npriceLevels - to find affordable restaurants, this can be set to [PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE]\n\nWith the textQuery provided and the two optional parameters that can help narrow the results to match the user's criteria, we have enough information to make a good call to the text_search_places_api tool to try to answer the user's request.\n"
    },
    {
      "type": "tool_use",
      "id": "toolu_vrtx_01TAJCTkxe8HhRoaQ69N4ouP",
      "name": "text_search_places_api",
      "input": {
        "textQuery": "Italian restaurants in San Francisco",
        "openNow": true,
        "priceLevels": [
          "PRICE_LEVEL_INEXPENSIVE",
          "PRICE_LEVEL_MODERATE"
        ]
      }
    }
  ],
  "stop_reason": "tool_use",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 727,
    "output_tokens": 308
  }
}
```

<br />

Use Agent Studio on Gemini Enterprise Agent Platform

For some of the Anthropic Claude models, you can use
Agent Studio on Gemini Enterprise Agent Platform to quickly prototype and test generative
AI models in the Google Cloud console. As an example, you can use
Agent Studio on Gemini Enterprise Agent Platform to compare Claude model responses with
other supported models such as Google Gemini.

For more information, see [Quickstart: Send text prompts to Gemini
using Agent Studio on Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/agent-studio/quickstart).