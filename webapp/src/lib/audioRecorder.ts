export type WavRecorder = {
  stop: () => Promise<File>;
  cancel: () => Promise<void>;
  /**
   * Returns the current byte frequency spectrum (0-255 per bin) of the live
   * microphone input, for monitoring/visualization. Returns an empty array
   * once the recorder has stopped or been cancelled.
   */
  getFrequencyData: () => Uint8Array;
};

export type CreateWavRecorderOptions = {
  fileName?: string;
  bufferSize?: number;
  /** FFT size for the live frequency monitor. Must be a power of two. */
  fftSize?: number;
};

type WebkitAudioWindow = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

const DEFAULT_BUFFER_SIZE = 4096;
const DEFAULT_FFT_SIZE = 256;
const WORKLET_PROCESSOR_NAME = "pbi-agent-dictation-recorder";
const WORKLET_PROCESSOR_SOURCE = `
class PbiAgentDictationRecorderProcessor extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const input = inputs[0];
    const output = outputs[0];
    const inputChannel = input && input[0];
    const outputChannel = output && output[0];

    if (inputChannel && inputChannel.length > 0) {
      const chunk = new Float32Array(inputChannel.length);
      chunk.set(inputChannel);
      this.port.postMessage(chunk, [chunk.buffer]);
      if (outputChannel) outputChannel.set(inputChannel);
    } else if (outputChannel) {
      outputChannel.fill(0);
    }

    return true;
  }
}

registerProcessor("${WORKLET_PROCESSOR_NAME}", PbiAgentDictationRecorderProcessor);
`;

type RecorderAudioNode = {
  node: AudioNode;
  cleanup: () => void;
};

function getAudioContextConstructor(): typeof AudioContext {
  const AudioContextConstructor =
    window.AudioContext ?? (window as WebkitAudioWindow).webkitAudioContext;
  if (!AudioContextConstructor) {
    throw new Error("Audio recording is not available in this browser.");
  }
  return AudioContextConstructor;
}

function stopStreamTracks(stream: MediaStream): void {
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

function disconnectNode(node: AudioNode): void {
  try {
    node.disconnect();
  } catch {
    // The node may already be disconnected during browser cleanup.
  }
}

function mergeAudioChunks(chunks: Float32Array[]): Float32Array {
  const totalLength = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Float32Array(totalLength);
  let offset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, offset);
    offset += chunk.length;
  }
  return merged;
}

function writeAscii(view: DataView, offset: number, value: string): void {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

export function encodeMonoPcm16Wav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const dataLength = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataLength);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataLength, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample));
    const pcm = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    view.setInt16(offset, pcm, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

async function createAudioWorkletRecorderNode(
  audioContext: AudioContext,
  chunks: Float32Array[],
): Promise<RecorderAudioNode> {
  const moduleUrl = URL.createObjectURL(
    new Blob([WORKLET_PROCESSOR_SOURCE], { type: "text/javascript" }),
  );
  try {
    await audioContext.audioWorklet.addModule(moduleUrl);
  } finally {
    URL.revokeObjectURL(moduleUrl);
  }

  const node = new AudioWorkletNode(audioContext, WORKLET_PROCESSOR_NAME, {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    outputChannelCount: [1],
  });

  node.port.onmessage = (event: MessageEvent<Float32Array>) => {
    const chunk = event.data;
    if (chunk instanceof Float32Array) {
      chunks.push(chunk);
    }
  };

  return {
    node,
    cleanup: () => {
      node.port.onmessage = null;
      node.port.close();
    },
  };
}

function createScriptProcessorRecorderNode(
  audioContext: AudioContext,
  chunks: Float32Array[],
  bufferSize: number,
): RecorderAudioNode {
  const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
  processor.onaudioprocess = (event) => {
    chunks.push(new Float32Array(event.inputBuffer.getChannelData(0)));
  };
  return {
    node: processor,
    cleanup: () => {
      processor.onaudioprocess = null;
    },
  };
}

async function createRecorderNode(
  audioContext: AudioContext,
  chunks: Float32Array[],
  bufferSize: number,
): Promise<RecorderAudioNode> {
  if (audioContext.audioWorklet && typeof AudioWorkletNode !== "undefined") {
    return createAudioWorkletRecorderNode(audioContext, chunks);
  }
  return createScriptProcessorRecorderNode(audioContext, chunks, bufferSize);
}

export async function createWavRecorder(
  options: CreateWavRecorderOptions = {},
): Promise<WavRecorder> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone recording is not available in this browser.");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const AudioContextConstructor = getAudioContextConstructor();
  const audioContext = new AudioContextConstructor();
  const chunks: Float32Array[] = [];
  const bufferSize = options.bufferSize ?? DEFAULT_BUFFER_SIZE;
  let recorder: RecorderAudioNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let sink: GainNode | null = null;
  let analyser: AnalyserNode | null = null;
  let frequencyData = new Uint8Array(0);
  let closed = false;

  try {
    recorder = await createRecorderNode(audioContext, chunks, bufferSize);
    source = audioContext.createMediaStreamSource(stream);
    sink = audioContext.createGain();
    sink.gain.value = 0;
    analyser = audioContext.createAnalyser();
    analyser.fftSize = options.fftSize ?? DEFAULT_FFT_SIZE;
    analyser.smoothingTimeConstant = 0.8;
    frequencyData = new Uint8Array(analyser.frequencyBinCount);

    source.connect(recorder.node);
    source.connect(analyser);
    recorder.node.connect(sink);
    sink.connect(audioContext.destination);

    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }
  } catch (error) {
    recorder?.cleanup();
    if (source) disconnectNode(source);
    if (recorder) disconnectNode(recorder.node);
    if (analyser) disconnectNode(analyser);
    if (sink) disconnectNode(sink);
    stopStreamTracks(stream);
    if (audioContext.state !== "closed") {
      await audioContext.close().catch(() => undefined);
    }
    throw error;
  }

  const liveAnalyser = analyser;

  async function cleanup(): Promise<void> {
    recorder?.cleanup();
    if (source) disconnectNode(source);
    if (recorder) disconnectNode(recorder.node);
    if (analyser) disconnectNode(analyser);
    if (sink) disconnectNode(sink);
    stopStreamTracks(stream);
    if (audioContext.state !== "closed") {
      await audioContext.close().catch(() => undefined);
    }
  }

  return {
    getFrequencyData: () => {
      if (closed) return new Uint8Array(0);
      liveAnalyser.getByteFrequencyData(frequencyData);
      return frequencyData;
    },
    stop: async () => {
      if (closed) {
        throw new Error("Dictation recording has already stopped.");
      }
      closed = true;
      await cleanup();
      const wav = encodeMonoPcm16Wav(mergeAudioChunks(chunks), audioContext.sampleRate);
      return new File(
        [wav],
        options.fileName ?? `dictation-${Date.now()}.wav`,
        { type: "audio/wav" },
      );
    },
    cancel: async () => {
      if (closed) return;
      closed = true;
      chunks.length = 0;
      await cleanup();
    },
  };
}