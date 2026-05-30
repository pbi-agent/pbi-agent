import { afterEach, describe, expect, it, vi } from "vitest";
import { createWavRecorder } from "./audioRecorder";

const originalCreateObjectURL = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const originalRevokeObjectURL = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");

class FakeAudioNode {
  readonly connect = vi.fn((destination: AudioNode) => destination);
  readonly disconnect = vi.fn();
}

class FakeGainNode extends FakeAudioNode {
  readonly gain = { value: 1 };
}

class FakeScriptProcessorNode extends FakeAudioNode {
  onaudioprocess: ((event: AudioProcessingEvent) => void) | null = null;
}

class FakeMessagePort {
  onmessage: ((event: MessageEvent<Float32Array>) => void) | null = null;
  readonly close = vi.fn();
}

class FakeAudioWorkletNode extends FakeAudioNode {
  static instances: FakeAudioWorkletNode[] = [];

  readonly fakePort = new FakeMessagePort();
  readonly port = this.fakePort as unknown as MessagePort;

  constructor(
    readonly context: BaseAudioContext,
    readonly processorName: string,
    readonly options?: AudioWorkletNodeOptions,
  ) {
    super();
    FakeAudioWorkletNode.instances.push(this);
  }
}

class FakeAudioContext {
  static instances: FakeAudioContext[] = [];
  static includeAudioWorklet = true;

  readonly sampleRate = 16_000;
  state: AudioContextState = "running";
  readonly destination = new FakeAudioNode() as unknown as AudioDestinationNode;
  readonly mediaSource = new FakeAudioNode();
  readonly gainNode = new FakeGainNode();
  readonly scriptProcessor = new FakeScriptProcessorNode();
  readonly addModule = vi.fn<(moduleUrl: string) => Promise<void>>((moduleUrl) => {
    void moduleUrl;
    return Promise.resolve();
  });
  readonly audioWorklet?: AudioWorklet;
  readonly createMediaStreamSource = vi.fn((stream: MediaStream) => {
    void stream;
    return this.mediaSource as unknown as MediaStreamAudioSourceNode;
  });
  readonly createGain = vi.fn(() => this.gainNode as unknown as GainNode);
  readonly createScriptProcessor = vi.fn(
    (
      bufferSize?: number,
      numberOfInputChannels?: number,
      numberOfOutputChannels?: number,
    ) => {
      void bufferSize;
      void numberOfInputChannels;
      void numberOfOutputChannels;
      return this.scriptProcessor as unknown as ScriptProcessorNode;
    },
  );
  readonly close = vi.fn(() => {
    this.state = "closed";
    return Promise.resolve();
  });
  readonly resume = vi.fn(() => {
    this.state = "running";
    return Promise.resolve();
  });

  constructor() {
    if (FakeAudioContext.includeAudioWorklet) {
      this.audioWorklet = {
        addModule: this.addModule,
      } as unknown as AudioWorklet;
    }
    FakeAudioContext.instances.push(this);
  }
}

function installBrowserMocks({ audioWorklet = true } = {}) {
  FakeAudioContext.instances = [];
  FakeAudioContext.includeAudioWorklet = audioWorklet;
  FakeAudioWorkletNode.instances = [];

  const track = { stop: vi.fn() };
  const stream = {
    getTracks: vi.fn(() => [track]),
  } as unknown as MediaStream;
  const getUserMedia = vi.fn(() => Promise.resolve(stream));
  const createObjectURL = vi.fn((blob: Blob) => {
    void blob;
    return "blob:pbi-agent-worklet";
  });
  const revokeObjectURL = vi.fn();

  vi.stubGlobal("navigator", {
    mediaDevices: { getUserMedia },
  });
  vi.stubGlobal("AudioContext", FakeAudioContext);
  vi.stubGlobal("AudioWorkletNode", FakeAudioWorkletNode);
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: createObjectURL,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: revokeObjectURL,
  });

  return { createObjectURL, getUserMedia, revokeObjectURL, track };
}

function ascii(view: DataView, offset: number, length: number): string {
  let value = "";
  for (let index = 0; index < length; index += 1) {
    value += String.fromCharCode(view.getUint8(offset + index));
  }
  return value;
}

async function blobArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === "function") {
    return blob.arrayBuffer();
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => {
      reject(new Error(reader.error?.message ?? "Could not read WAV blob."));
    };
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) {
        resolve(reader.result);
      } else {
        reject(new Error("Expected FileReader to return an ArrayBuffer."));
      }
    };
    reader.readAsArrayBuffer(blob);
  });
}

async function wavView(file: File): Promise<DataView> {
  return new DataView(await blobArrayBuffer(file));
}

describe("audioRecorder", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    if (originalCreateObjectURL) {
      Object.defineProperty(URL, "createObjectURL", originalCreateObjectURL);
    } else {
      Reflect.deleteProperty(URL, "createObjectURL");
    }
    if (originalRevokeObjectURL) {
      Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectURL);
    } else {
      Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("records microphone chunks with AudioWorklet", async () => {
    const { createObjectURL, revokeObjectURL, track } = installBrowserMocks();

    const recorder = await createWavRecorder({ fileName: "dictation.wav" });
    const context = FakeAudioContext.instances[0];
    const worklet = FakeAudioWorkletNode.instances[0];

    expect(context?.addModule).toHaveBeenCalledWith("blob:pbi-agent-worklet");
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:pbi-agent-worklet");
    expect(context?.createScriptProcessor).not.toHaveBeenCalled();
    expect(worklet?.processorName).toBe("pbi-agent-dictation-recorder");

    worklet?.fakePort.onmessage?.({
      data: new Float32Array([0, 1, -1]),
    } as MessageEvent<Float32Array>);

    const file = await recorder.stop();
    const view = await wavView(file);

    expect(file.name).toBe("dictation.wav");
    expect(file.type).toBe("audio/wav");
    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(ascii(view, 8, 4)).toBe("WAVE");
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(40, true)).toBe(6);
    expect(view.getInt16(44, true)).toBe(0);
    expect(view.getInt16(46, true)).toBe(32_767);
    expect(view.getInt16(48, true)).toBe(-32_768);
    expect(worklet?.fakePort.close).toHaveBeenCalledTimes(1);
    expect(worklet?.disconnect).toHaveBeenCalledTimes(1);
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(context?.close).toHaveBeenCalledTimes(1);
  });

  it("falls back to ScriptProcessor only when AudioWorklet is unavailable", async () => {
    const { track } = installBrowserMocks({ audioWorklet: false });

    const recorder = await createWavRecorder({
      bufferSize: 256,
      fileName: "fallback.wav",
    });
    const context = FakeAudioContext.instances[0];
    const processor = context?.scriptProcessor;

    expect(FakeAudioWorkletNode.instances).toHaveLength(0);
    expect(context?.createScriptProcessor).toHaveBeenCalledWith(256, 1, 1);

    processor?.onaudioprocess?.({
      inputBuffer: {
        getChannelData: () => new Float32Array([0.5]),
      },
    } as unknown as AudioProcessingEvent);

    const file = await recorder.stop();
    const view = await wavView(file);

    expect(file.name).toBe("fallback.wav");
    expect(view.getUint32(40, true)).toBe(2);
    expect(view.getInt16(44, true)).toBe(16_383);
    expect(processor?.onaudioprocess).toBeNull();
    expect(track.stop).toHaveBeenCalledTimes(1);
  });
});