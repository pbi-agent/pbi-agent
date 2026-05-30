---
title: 'Speech-to-text'
description: 'Configure speech-to-text providers and use dictation in the pbi-agent web UI.'
---

# Speech-to-text (STT)

Speech-to-text powers voice dictation in the web UI composer. When enabled, the
browser records your microphone, sends a WAV file to the local pbi-agent web
server, and pbi-agent forwards normalized audio to the selected STT provider.
The returned transcript is inserted into the composer so you can edit it before
sending.

## Supported providers

STT uses saved **Providers**. OpenAI, xAI, and Google providers can be used for
both model profiles and dictation; Deepgram and ElevenLabs are STT-only provider
kinds.

| Provider kind | Use | Default key environment variable | Notes |
| --- | --- | --- | --- |
| `openai` | Model profiles and STT | `OPENAI_API_KEY` | Uses OpenAI audio transcriptions with `gpt-4o-transcribe`. If no saved key or provider-specific env var is configured, STT can also use `PBI_AGENT_API_KEY`. |
| `xai` | Model profiles and STT | `XAI_API_KEY` | Uses the xAI STT endpoint. |
| `google` | Model profiles and STT | `GEMINI_API_KEY` | Uses Gemini audio understanding with `gemini-3.5-flash` and inline WAV audio. |
| `deepgram` | STT only | `DEEPGRAM_API_KEY` | Uses Deepgram Listen with `nova-3` and smart formatting. |
| `elevenlabs` | STT only | `ELEVENLABS_API_KEY` | Uses ElevenLabs Scribe v2. pbi-agent converts prepared WAV audio to raw 16 kHz mono PCM before upload. |

All STT uploads are normalized by pbi-agent to 16 kHz mono WAV before provider
dispatch. If a provider returns an empty transcript, the composer shows “No
speech was detected” instead of treating it as a failure.

## Configure STT in the web UI

1. Open **Settings**.
2. In **Providers**, add a provider with an STT-capable kind:
   **OpenAI API**, **xAI**, **Google**, **Deepgram**, or **ElevenLabs**.
3. Add credentials either as a saved API key or as an environment-variable
   reference such as `OPENAI_API_KEY`, `XAI_API_KEY`, `GEMINI_API_KEY`,
   `DEEPGRAM_API_KEY`, or `ELEVENLABS_API_KEY`.
4. Open **Speech-to-text** in Settings.
5. Choose the provider from **Active default**.

The selected provider is stored in local config under `~/.pbi-agent/` and is
used for future dictation requests.

## Create STT providers from the CLI

You can create saved provider records from the CLI, then choose the speech
provider in **Settings → Speech-to-text**.

```bash
pbi-agent config providers create \
  --id openai-stt \
  --name "OpenAI STT" \
  --kind openai \
  --api-key-env OPENAI_API_KEY

pbi-agent config providers create \
  --id google-stt \
  --name "Google STT" \
  --kind google \
  --api-key-env GEMINI_API_KEY

pbi-agent config providers create \
  --id deepgram-stt \
  --name "Deepgram STT" \
  --kind deepgram \
  --api-key-env DEEPGRAM_API_KEY

pbi-agent
```

Deepgram and ElevenLabs providers cannot be used by model profiles because they
are speech-only. Use a separate model-capable provider and model profile for
normal agent turns.

## Use dictation

1. Open a session.
2. Make sure the composer is empty and not in shell-command mode.
3. Click the microphone button, or press <kbd>Ctrl</kbd>+<kbd>Space</kbd>.
4. Allow microphone access in your browser when prompted.
5. Speak while the waveform is visible.
6. Click the microphone button again, or press <kbd>Ctrl</kbd>+<kbd>Space</kbd>
   again, to stop recording.
7. Wait for transcription, edit the inserted text if needed, then send the
   message.

Dictation is disabled while a turn is processing, when credentials are missing,
when no STT provider is selected, or when the composer already contains text.

## Local transcription API

The web backend exposes the endpoint used by the composer:

```http
POST /api/stt/transcribe
Content-Type: multipart/form-data
```

Send exactly one `file` part containing WAV audio. The response body is:

```json
{ "text": "transcribed text" }
```

Configuration or provider errors are returned as HTTP errors; empty provider
transcripts return `200` with an empty `text` field.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Microphone button is disabled | Select an STT provider in **Settings → Speech-to-text**, add credentials, and start from an empty composer. |
| “Microphone permission was denied” | Allow microphone access for the pbi-agent page in your browser. |
| “No microphone was found” | Check the operating-system input device and browser site permissions. |
| “No speech was detected” | Try again with a clearer input signal or longer recording. |
| Provider/auth error | Confirm the saved provider has an API key, the referenced env var is set before starting `pbi-agent`, and the provider account has STT access. |
| Browser reports recording unavailable | Use a browser with `getUserMedia` and Web Audio support. Localhost is supported by modern browsers for microphone capture. |

## Privacy note

Microphone audio is recorded in the browser and sent to your local pbi-agent web
server first. To produce a transcript, pbi-agent then sends the prepared audio to
the selected external STT provider. Choose a provider and retention policy that
match your data requirements.

## Related pages

- [Web UI](/web-ui)
- [Providers](/providers)
- [Environment Variables](/environment)