import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { api } from "../api";
import { VoiceAssistant } from "./VoiceAssistant";

vi.mock("../api", () => ({ api: { voiceCommand: vi.fn() } }));

type MockRecognitionResult = { isFinal: boolean; 0: { transcript: string } };

class MockRecognition {
  static instances: MockRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = false;
  onresult: ((event: { resultIndex: number; results: ArrayLike<MockRecognitionResult> }) => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  onend: (() => void) | null = null;
  started = false;
  abortCount = 0;

  constructor() {
    MockRecognition.instances.push(this);
  }

  start() {
    this.started = true;
  }

  stop() {}

  abort() {
    this.abortCount += 1;
  }

  say(text: string) {
    this.onresult?.({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: text } }] });
  }
}

class MockUtterance {
  lang = "";
  voice: SpeechSynthesisVoice | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error: string }) => void) | null = null;
  constructor(readonly text: string) {}
}

const getUserMedia = vi.fn();
const spoken: MockUtterance[] = [];
const mockSpeech = { getVoices: () => [], cancel: vi.fn(), speak: (utterance: MockUtterance) => spoken.push(utterance) };

function mountAssistant() {
  return render(<BrowserRouter><VoiceAssistant /></BrowserRouter>);
}

function successfulResponse(request: { request_id: string }) {
  return Promise.resolve({ request_id: request.request_id, action: "wardrobe_search", message: "I found two confirmed shirts.", data: {} });
}

describe("VoiceAssistant", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockRecognition.instances = [];
    spoken.length = 0;
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: MockRecognition });
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
    getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] });
    Object.defineProperty(window, "speechSynthesis", { configurable: true, value: mockSpeech });
    Object.defineProperty(window, "SpeechSynthesisUtterance", { configurable: true, value: MockUtterance });
    vi.mocked(api.voiceCommand).mockImplementation(async (request) => successfulResponse(request));
  });

  it("starts on tap, handles successive commands, and does not listen during assistant speech", async () => {
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(MockRecognition.instances[0].started).toBe(true);
    expect(spoken).toHaveLength(0);

    act(() => MockRecognition.instances[0].say("Show my shirts"));
    await waitFor(() => expect(api.voiceCommand).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Responding"));
    expect(MockRecognition.instances[0].abortCount).toBe(1);
    expect(spoken).toHaveLength(1);
    act(() => spoken[0].onend?.());
    await waitFor(() => expect(MockRecognition.instances).toHaveLength(2));
    expect(screen.getByRole("status")).toHaveTextContent("I'm listening");
    expect(api.voiceCommand).toHaveBeenCalledTimes(1);

    act(() => MockRecognition.instances[1].say("Show blue shirts"));
    await waitFor(() => expect(api.voiceCommand).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.voiceCommand).mock.calls[0][0].request_id).not.toBe(vi.mocked(api.voiceCommand).mock.calls[1][0].request_id);
  });

  it("pauses, resumes with permission, and releases recognition when stopped", async () => {
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(screen.getByRole("status")).toHaveTextContent("Assistant paused");
    expect(MockRecognition.instances[0].abortCount).toBe(1);

    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(MockRecognition.instances).toHaveLength(2));
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Stop Assistant" }));
    expect(screen.getByRole("status")).toHaveTextContent("Tap to start");
    expect(MockRecognition.instances[1].abortCount).toBe(1);
  });

  it("releases the permission probe stream after recognition starts", async () => {
    const trackStop = vi.fn();
    getUserMedia.mockResolvedValueOnce({ getTracks: () => [{ stop: trackStop }] });
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));

    expect(trackStop).toHaveBeenCalledTimes(1);
  });

  it("recovers from a browser no-speech timeout without ending the session", async () => {
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));

    act(() => MockRecognition.instances[0].onerror?.({ error: "no-speech" }));
    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting");
    act(() => MockRecognition.instances[0].onend?.());

    await waitFor(() => expect(MockRecognition.instances).toHaveLength(2));
    expect(screen.getByRole("status")).toHaveTextContent("I'm listening");
    expect(screen.getByRole("button", { name: "Stop Assistant" })).toBeInTheDocument();
  });

  it("ignores a stale speech callback after the session is paused", async () => {
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    act(() => MockRecognition.instances[0].say("Show my shirts"));
    await waitFor(() => expect(spoken).toHaveLength(1));

    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    act(() => spoken[0].onend?.());
    expect(screen.getByRole("status")).toHaveTextContent("Assistant paused");
  });

  it("handles spoken pause and stop locally without sending them to the AI", async () => {
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    act(() => MockRecognition.instances[0].say("assistant pause chey"));
    expect(screen.getByRole("status")).toHaveTextContent("Assistant paused");
    expect(api.voiceCommand).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => expect(MockRecognition.instances).toHaveLength(2));
    act(() => MockRecognition.instances[1].say("stop assistant"));
    expect(screen.getByRole("status")).toHaveTextContent("Tap to start");
    expect(api.voiceCommand).not.toHaveBeenCalled();
  });

  it("stops microphone capture when the assistant leaves the page", async () => {
    const mounted = mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    mounted.unmount();
    expect(MockRecognition.instances[0].abortCount).toBe(1);
    expect(mockSpeech.cancel).toHaveBeenCalled();
  });

  it("reports denied permission and retries the microphone request", async () => {
    getUserMedia.mockRejectedValueOnce(new DOMException("Permission denied", "NotAllowedError"));
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    expect(await screen.findByText(/Microphone permission was denied/)).toBeInTheDocument();
    getUserMedia.mockResolvedValueOnce({ getTracks: () => [{ stop: vi.fn() }] });
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
  });

  it("offers text fallback when recognition is unsupported", async () => {
    Object.defineProperty(window, "SpeechRecognition", { configurable: true, value: undefined });
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    expect(await screen.findByText(/not supported in this browser/)).toBeInTheDocument();
    expect(getUserMedia).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Type a StyleMate command"), { target: { value: "Show my shirts" } });
    fireEvent.click(screen.getByRole("button", { name: "Send command" }));
    await waitFor(() => expect(api.voiceCommand).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("I found two confirmed shirts.")).toBeInTheDocument();
  });

  it("shows network errors and retries with the same idempotency key", async () => {
    vi.mocked(api.voiceCommand)
      .mockRejectedValueOnce(new Error("Network error"))
      .mockImplementationOnce(async (request) => successfulResponse(request));
    mountAssistant();
    fireEvent.click(screen.getByRole("button", { name: "Start Voice Assistant" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("I'm listening"));
    act(() => MockRecognition.instances[0].say("Save this outfit"));
    expect(await screen.findByText("Network error")).toBeInTheDocument();
    const firstRequestId = vi.mocked(api.voiceCommand).mock.calls[0][0].request_id;
    fireEvent.click(screen.getByRole("button", { name: "Retry command" }));
    await waitFor(() => expect(api.voiceCommand).toHaveBeenCalledTimes(2));
    expect(vi.mocked(api.voiceCommand).mock.calls[1][0].request_id).toBe(firstRequestId);
    expect(await screen.findByText("I found two confirmed shirts.")).toBeInTheDocument();
  });
});
