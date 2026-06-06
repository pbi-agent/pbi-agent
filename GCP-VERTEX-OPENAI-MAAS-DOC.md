Many open models on Gemini Enterprise Agent Platform offer fully managed and serverless
models as APIs using the Gemini Enterprise Agent Platform
[Chat Completions API](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/projects.locations.endpoints.chat/completions).
For these models, there's no need to provision or manage infrastructure.

You can stream your responses to reduce the end-user latency perception. A
streamed response uses *server-sent events* (SSE) to incrementally stream the
response.

This page shows how to make streaming and non-streaming calls to open models
that support the OpenAI chat completions API. For Llama-specific considerations,
see [Request Llama predictions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/llama/use-llama).

## Before you begin

To use open models with Gemini Enterprise Agent Platform, you must perform the
following steps. The Agent Platform API
(`aiplatform.googleapis.com`) must be enabled to use
Gemini Enterprise Agent Platform. If you already have an existing project with the
Agent Platform API enabled, you can use that project instead of creating a
new project.

1. Go to the Model Garden model card for the model you want to use, then click **Enable** to enable the model for use in your project.

   [Go to Model Garden](https://console.cloud.google.com/agent-platform/model-garden)

## Make a streaming call to an open model

The following sample makes a streaming call to an open model:

### Python


Before trying this sample, follow the Python setup instructions in the
[Agent Platform quickstart using
client libraries](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/start/client-libraries).


To authenticate to Agent Platform, set up Application Default Credentials.
For more information, see

[Set up authentication for a local development environment](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

Before running this sample, make sure to set the `OPENAI_BASE_URL` environment variable.
For more information, see [Authentication and credentials](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/openai/auth-and-credentials).

```python
from openai import OpenAI
client = OpenAI()

stream = client.chat.completions.create(
    model="MODEL",
    messages=[{"role": "ROLE", "content": "CONTENT"}],
    max_tokens=MAX_OUTPUT_TOKENS,
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The model name you want to use, for example `deepseek-ai/deepseek-v3.1-maas`.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. The models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_OUTPUT_TOKENS" translate="no">MAX_OUTPUT_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately four characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.

### REST


After you set up your environment, you can use REST to test a text prompt. The
following sample sends a request to the publisher model endpoint.


Before using any of the request data,
make the following replacements:

- <var class="edit" scope="LOCATION" translate="no">LOCATION</var>: A region that supports open models.
- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The model name you want to use, for example `deepseek-ai/deepseek-v2`.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. The models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_OUTPUT_TOKENS" translate="no">MAX_OUTPUT_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately four characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.
- <var class="edit" scope="STREAM" translate="no">STREAM</var>: A boolean that specifies whether the response is streamed or not. Stream your response to reduce the end-use latency perception. Set to `true` to stream the response and `false` to return the response all at once.


HTTP method and URL:

```
POST https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions
```


Request JSON body:

```
{
  "model": "MODEL",
  "messages": [
    {
      "role": "ROLE",
      "content": "CONTENT"
    }
  ],
  "max_tokens": MAX_OUTPUT_TOKENS,
  "stream": true
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
     "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions"
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
    -Uri "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions" | Select-Object -Expand Content
```

You should receive a JSON response similar to the following.

#### Response

```
data: {
  "choices": [
    {
      "delta": {
        "content": "CONTENT",
        "role": "assistant"
      },
      "index": 0,
      "logprobs": null
    }
  ],
  "created": 1234567890,
  "id": "2025-06-11|10:00:00.292195-07|9.7.144.202|-123456789",
  "model": "MODEL",
  "object": "chat.completion.chunk",
  "system_fingerprint": ""
}

data: {
  "choices": [
    {
      "delta": {
        "content": "CONTENT",
        "role": "assistant"
      },
      "finish_reason": "stop",
      "index": 0,
      "logprobs": null
    }
  ],
  "created": 1234567890,
  "id": "2025-06-11|10:00:00.292195-07|9.7.144.202|-123456789",
  "model": "MODEL",
  "object": "chat.completion.chunk",
  "system_fingerprint": "",
  "usage": {
    "completion_tokens": 131,
    "prompt_tokens": 14,
    "total_tokens": 145
  }
}

data: [DONE]
```

<br />

## Make a non-streaming call to an open model

The following sample makes a non-streaming call to an open model:

### Python


Before trying this sample, follow the Python setup instructions in the
[Agent Platform quickstart using
client libraries](https://docs.cloud.google.com/gemini-enterprise-agent-platform/machine-learning/start/client-libraries).


To authenticate to Agent Platform, set up Application Default Credentials.
For more information, see

[Set up authentication for a local development environment](https://docs.cloud.google.com/docs/authentication/set-up-adc-local-dev-environment).

Before running this sample, make sure to set the `OPENAI_BASE_URL` environment variable.
For more information, see [Authentication and credentials](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/migrate/openai/auth-and-credentials).

```python
from openai import OpenAI
client = OpenAI()

completion = client.chat.completions.create(
    model="MODEL",
    messages=[{"role": "ROLE", "content": "CONTENT"}],
    max_tokens=MAX_OUTPUT_TOKENS,
    stream=False,
)
print(completion.choices[0].message)
```

- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The model name you want to use, for example `deepseek-ai/deepseek-v3.1-maas`.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. The models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_OUTPUT_TOKENS" translate="no">MAX_OUTPUT_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately four characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.

### REST


After you set up your environment, you can use REST to test a text prompt. The
following sample sends a request to the publisher model endpoint.


Before using any of the request data,
make the following replacements:

- <var class="edit" scope="LOCATION" translate="no">LOCATION</var>: A region that supports open models.
- <var class="edit" scope="MODEL" translate="no">MODEL</var>: The model name you want to use, for example `deepseek-ai/deepseek-v2`.
- <var class="edit" scope="ROLE" translate="no">ROLE</var>: The role associated with a message. You can specify a `user` or an `assistant`. The first message must use the `user` role. The models operate with alternating `user` and `assistant` turns. If the final message uses the `assistant` role, then the response content continues immediately from the content in that message. You can use this to constrain part of the model's response.
- <var class="edit" scope="CONTENT" translate="no">CONTENT</var>: The content, such as text, of the `user` or `assistant` message.
- <var class="edit" scope="MAX_OUTPUT_TOKENS" translate="no">MAX_OUTPUT_TOKENS</var>: Maximum number of tokens that can be generated in the response. A token is approximately four characters. 100 tokens correspond to roughly 60-80 words.

  Specify a lower value for shorter responses and a higher value for potentially longer
  responses.
- <var class="edit" scope="STREAM" translate="no">STREAM</var>: A boolean that specifies whether the response is streamed or not. Stream your response to reduce the end-use latency perception. Set to `true` to stream the response and `false` to return the response all at once.


HTTP method and URL:

```
POST https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions
```


Request JSON body:

```
{
  "model": "MODEL",
  "messages": [
    {
      "role": "ROLE",
      "content": "CONTENT"
    }
  ],
  "max_tokens": MAX_OUTPUT_TOKENS,
  "stream": false
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
     "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions"
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
    -Uri "https://LOCATION-aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/LOCATION/endpoints/openapi/chat/completions" | Select-Object -Expand Content
```

You should receive a JSON response similar to the following.

#### Response

```
{
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "logprobs": null,
      "message": {
        "content": "CONTENT",
        "role": "assistant"
      }
    }
  ],
  "created": 1234567890,
  "id": "2025-06-11|10:00:00.292195-07|9.7.144.202|-123456789",
  "model": "MODEL",
  "object": "chat.completion",
  "system_fingerprint": "",
  "usage": {
    "completion_tokens": 367,
    "prompt_tokens": 14,
    "total_tokens": 381
  }
}
```

<br />

## Regional and global endpoints

For regional endpoints, requests are served from your specified region. In cases
where you have data residency requirements or if a model doesn't support the
global endpoint, use the regional endpoints.

When you use the global endpoint, Google can process and serve your requests
from any region that is supported by the model that you are using. This might
result in higher latency in some cases. The global endpoint helps improve
overall availability and helps reduce errors.

There is no price difference with the regional endpoints when you use the global
endpoint. However, the global endpoint quotas and supported model capabilities
can differ from the regional endpoints. For more information, view the related
third-party model page.

### Specify the global endpoint

To use the global endpoint, set the region to `global`.

For example, the request URL for a curl command uses the following format:
`https://aiplatform.googleapis.com/v1/projects/PROJECT_ID/locations/global/endpoints/openapi`

For the Agent Platform SDK, a regional endpoint is the default. Set the
region to `GLOBAL` to use the global endpoint.

### Restrict global API endpoint usage

To help enforce the use of regional endpoints, use the
`constraints/gcp.restrictEndpointUsage` organization policy constraint to block
requests to the global API endpoint. For more information, see
[Restrict endpoint usage](https://docs.cloud.google.com/docs/security/compliance/restrict-endpoint-usage).

## What's next

- Learn how to use [Function calling](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/capabilities/function-calling).
- Learn about [Structured output](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/capabilities/structured-output).
- Learn about [Batch predictions](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/maas/capabilities/batch-prediction).