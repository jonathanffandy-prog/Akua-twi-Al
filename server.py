import os
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

ABENA_BASE = "https://abena.mobobi.com/playground/api/v1"
ABENA_API_KEY = os.getenv("ABENA_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

SYSTEM_PROMPT = """
You are Akua, a friendly Ghanaian AI voice assistant.

Speak naturally in Ghanaian Twi (Akan), and use natural Twi-English
code-switching when appropriate. Do not sound like a textbook,
translation engine, or foreign learner of Twi.

Keep replies conversational, warm, clear and reasonably short.
Use Ghanaian expressions naturally when they fit the situation.

You are an AI assistant, so never falsely claim to be a real human.
Do not invent personal experiences.

If the user speaks English, you may reply in English or naturally mix
English and Twi depending on the conversation.
If the user speaks Twi, prioritize Twi.
"""

FALLBACK_REPLIES = {
    "hello": "Agoo! Me din de Akua. Ɛyɛ me dɛ sɛ yɛbɛkasa. Wo ho te sɛn?",
    "hi": "Agoo! Wo ho te sɛn? Me ne Akua.",
    "how are you": "Me ho yɛ. Wo nso, wo ho te sɛn?",
    "yɛfrɛ wo sɛn": "Wɔfrɛ me Akua. Ɛyɛ me dɛ sɛ yɛahu yɛn ho!",
}


def fallback_reply(message):
    text = message.lower().strip()

    for key, reply in FALLBACK_REPLIES.items():
        if key in text:
            return reply

    return (
        "Aane, mate wo. Ka nea wopɛ sɛ yɛka ho asɛm kyerɛ me, "
        "na mɛyɛ me best aboa wo."
    )


@app.get("/")
def home():
    return send_from_directory(".", "index.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "chat": "openai" if OPENAI_API_KEY else "fallback",
        "asr": "abena",
        "tts": "abena"
    })


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "Please enter a message."}), 400

    if not OPENAI_API_KEY:
        return jsonify({
            "reply": fallback_reply(message),
            "mode": "fallback"
        })

    try:
        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": OPENAI_MODEL,
                "instructions": SYSTEM_PROMPT,
                "input": message
            },
            timeout=60
        )

        response.raise_for_status()
        result = response.json()

        reply = result.get("output_text", "").strip()

        if not reply:
            return jsonify({
                "reply": fallback_reply(message),
                "mode": "fallback"
            })

        return jsonify({
            "reply": reply,
            "mode": "openai"
        })

    except Exception as e:
        print("Chat error:", e)

        return jsonify({
            "reply": fallback_reply(message),
            "mode": "fallback"
        })


@app.post("/api/asr")
def asr():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file received."}), 400

    audio = request.files["audio"]

    try:
        headers = {}
        if ABENA_API_KEY:
            headers["Authorization"] = f"Bearer {ABENA_API_KEY}"

        files = {
            "audio_file": (
                audio.filename or "recording.webm",
                audio.stream,
                audio.mimetype or "audio/webm"
            )
        }

        response = requests.post(
            f"{ABENA_BASE}/asr/transcribe/",
            headers=headers,
            files=files,
            data={"language": "twi-en"},
            timeout=90
        )

        response.raise_for_status()
        result = response.json()

        text = (
            result.get("text")
            or result.get("transcript")
            or result.get("transcription")
            or ""
        ).strip()

        if not text:
            return jsonify({"error": "I couldn't understand the recording."}), 422

        return jsonify({"text": text})

    except Exception as e:
        print("ASR error:", e)
        return jsonify({
            "error": "Voice recognition is temporarily unavailable."
        }), 502


@app.post("/api/tts")
def tts():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()

    if not text:
        return jsonify({"error": "No text supplied."}), 400

    try:
        headers = {}
        if ABENA_API_KEY:
            headers["Authorization"] = f"Bearer {ABENA_API_KEY}"

        response = requests.post(
            f"{ABENA_BASE}/tts/synthesize/",
            headers=headers,
            json={
                "text": text,
                "voice_id": "abena_twi_high",
                "speed": 0.92
            },
            timeout=90
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type",
            "audio/mpeg"
        )

        from flask import Response

        return Response(
            response.content,
            status=200,
            mimetype=content_type.split(";")[0]
        )

    except Exception as e:
        print("TTS error:", e)
        return jsonify({
            "error": "Voice generation is temporarily unavailable."
        }), 502


@app.errorhandler(413)
def too_large(error):
    return jsonify({
        "error": "That recording is too large. Please record a shorter message."
    }), 413


if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
