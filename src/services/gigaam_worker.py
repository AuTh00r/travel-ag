"""Private JSON-lines worker; only this isolated process imports ASR/PyAV."""

import hashlib
import json
import re
import sys
from pathlib import Path

SAMPLE_RATE = 16000
MAX_SECONDS = 180
MODEL_HASHES = {
    "config.json": "0641fcf73f4af791c73f05083e38a658ff5dcbee3534a0c61396c10f4b97f0fe",
    "v3_e2e_rnnt_encoder.onnx": "cd60b3764a832e8560ae6d3ad0b10adc1a42ffae412b9476f25620aae4f4a508",
    "v3_e2e_rnnt_decoder.onnx": "7b0a16d67fd2cb37061decc93c69e364a9ab27afee3c57495d55b1c974cf7231",
    "v3_e2e_rnnt_joint.onnx": "602ff7017a93311aad34df1437c8d7f49911353c13d6eae7a6ee7b041339465c",
    "v3_e2e_rnnt_vocab.txt": "39abae20e692998290c574e606f11a9edef2902a1995463fcff63d1490cf22b7",
}


class WorkerError(Exception):
    pass


def load_model(directory):
    import onnx_asr
    import onnxruntime as ort

    for name, expected in MODEL_HASHES.items():
        path = Path(directory) / name
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise WorkerError("voice_model")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    return onnx_asr.load_model("gigaam-v3-e2e-rnnt", path=str(directory), quantization=None,
        sess_options=options, providers=["CPUExecutionProvider"],
        preprocessor_config={"use_numpy_preprocessors": True, "max_concurrent_workers": 1})


def decode(path, remaining):
    import av
    import numpy as np

    path = Path(path)
    if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise WorkerError("voice_format")
    with path.open("rb") as source:
        header = source.read(16)
    allowed = (header[4:8] == b"ftyp" or header.startswith((b"OggS", b"ID3", b"fLaC"))
               or (header.startswith(b"RIFF") and header[8:12] == b"WAVE")
               or (len(header) > 1 and header[0] == 255 and header[1] & 224 == 224))
    if not allowed:
        raise WorkerError("voice_format")
    samples, count = [], 0
    with av.open(str(path), options={"protocol_whitelist": "file"}) as container:
        if container.streams.video or len(container.streams.audio) != 1:
            raise WorkerError("voice_format")
        stream = container.streams.audio[0]
        stream.codec_context.thread_count = 2
        if stream.duration and stream.time_base and float(stream.duration * stream.time_base) > remaining + 0.1:
            raise WorkerError("voice_duration")
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)

        def collect(frames):
            nonlocal count
            for frame in frames:
                value = frame.to_ndarray().reshape(-1).astype(np.float32, copy=False)
                count += len(value)
                if count > int(remaining * SAMPLE_RATE):
                    raise WorkerError("voice_duration")
                samples.append(value)

        for frame in container.decode(stream):
            collect(resampler.resample(frame))
        collect(resampler.resample(None))
    if not count:
        raise WorkerError("voice_empty")
    return np.concatenate(samples)


def chunks(audio):
    """Cover the entire signal, preferring quiet cuts, with half-second overlap."""
    import numpy as np

    position, length = 0, len(audio)
    while length - position > 25 * SAMPLE_RATE:
        candidates = range(position + 17 * SAMPLE_RATE, position + 23 * SAMPLE_RATE, SAMPLE_RATE // 4)
        boundary = min(candidates, key=lambda index: float(np.mean(np.square(
            audio[index:index + SAMPLE_RATE // 4]))))
        yield audio[position:boundary + SAMPLE_RATE // 4]
        position = boundary - SAMPLE_RATE // 4
    if position < length:
        yield audio[position:]


def join_transcripts(previous, current):
    left, right = previous.split(), current.split()
    def normalized(word):
        return re.sub(r"\W", "", word.casefold())
    for count in range(min(12, len(left), len(right)), 0, -1):
        a, b = [normalized(word) for word in left[-count:]], [normalized(word) for word in right[:count]]
        if a == b and all(a) and (count >= 2 or len(a[0]) >= 5):
            right = right[count:]
            break
    return " ".join([*left, *right])


def recognize_paths(model, paths):
    import numpy as np

    if not isinstance(paths, list) or not 1 <= len(paths) <= 3 or not all(isinstance(path, str) for path in paths):
        raise WorkerError("voice_format")
    texts, duration = [], 0
    for path in paths:
        audio = decode(path, MAX_SECONDS - duration)
        duration += len(audio) / SAMPLE_RATE
        text = ""
        for chunk in chunks(audio):
            if float(np.sqrt(np.mean(np.square(chunk)))) < 0.0001:
                continue
            result = model.recognize(chunk, sample_rate=SAMPLE_RATE)
            if not isinstance(result, str):
                raise WorkerError("voice_decode")
            text = join_transcripts(text, result)
        if not text.strip():
            raise WorkerError("voice_empty")
        texts.append(text)
    return {"texts": texts, "duration": round(duration, 3)}


def emit(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)


def main():
    # Third-party progress/output cannot enter the protocol or application logs.
    protocol = sys.stdout
    sys.stdout = sys.stderr
    try:
        model = load_model(sys.argv[1])
    except Exception:
        sys.stdout = protocol
        emit({"error": "voice_model"})
        return 1
    sys.stdout = protocol
    emit({"ready": 1})
    while True:
        line = sys.stdin.buffer.readline(65537)
        if not line:
            return 0
        if len(line) > 65536 or not line.endswith(b"\n"):
            return 1
        try:
            request = json.loads(line)
            sys.stdout = sys.stderr
            reply = recognize_paths(model, request["paths"])
        except WorkerError as error:
            reply = {"error": str(error)}
        except Exception:
            reply = {"error": "voice_decode"}
        finally:
            sys.stdout = protocol
        emit(reply)


if __name__ == "__main__":
    raise SystemExit(main())
