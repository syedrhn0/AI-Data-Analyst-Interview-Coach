import html
import io
import os
import re
import tempfile
import threading
import wave

import pyttsx3
import speech_recognition as sr
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ----------------------------- CONFIGURATION -----------------------------
APP_NAME = "AI Data Analyst Interview Coach"
LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b")
TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
DEFAULT_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "autumn").lower()

VOICE_OPTIONS = {
    "Orpheus - Autumn": "autumn",
    "Orpheus - Diana": "diana",
    "Orpheus - Hannah": "hannah",
    "Orpheus - Austin": "austin",
    "Orpheus - Daniel": "daniel",
    "Orpheus - Troy": "troy",
    "Local voice (pyttsx3)": "local",
}
VOICE_LABEL_BY_VALUE = {value: label for label, value in VOICE_OPTIONS.items()}

SUBJECTS = [
    "SQL", "Python", "Pandas & NumPy", "Statistics", "Power BI", "Excel",
    "Machine Learning", "Data Analysis & Business Cases", "HR & Behavioural",
    "Mixed Interview",
]
DIFFICULTIES = ["Beginner", "Intermediate", "Advanced"]

SUBJECT_GUIDANCE = {
    "SQL": "Assess SQL knowledge through a balanced mix of theory and practical reasoning. Include concepts such as keys, NULL, filtering, joins, grouping, subqueries, CTEs, window functions, indexes, and query logic. Ask business scenarios such as finding duplicate records, identifying each customer's latest order, comparing monthly sales, or ranking products. Ask what SQL feature or approach the candidate would use and why. Occasionally ask the candidate to explain the logic of a short query, but do not make the interview a sequence of full query-writing exercises.",
    "Python": "Assess Python through a balanced mix of theory and practical reasoning. Cover data types, mutability, strings, lists, tuples, dictionaries, sets, functions, loops, comprehensions, exceptions, OOP basics, and common data-analysis workflows. Use scenarios such as cleaning inconsistent values, counting categories, removing duplicates, choosing a data structure, or processing a large file. Ask which Python feature or approach the candidate would use and why. Do not demand long code to be typed or spoken character by character.",
    "Pandas & NumPy": "Cover Series, DataFrames, indexing, filtering, missing values, grouping, merging, reshaping, NumPy arrays, vectorized operations, and practical data-cleaning scenarios. Ask the candidate to explain the approach and relevant functions.",
    "Statistics": "Cover descriptive statistics, probability, distributions, sampling, confidence intervals, hypothesis testing, correlation, regression basics, and how statistical thinking supports business decisions.",
    "Power BI": "Cover Power Query, data modelling, relationships, DAX, measures, calculated columns, visuals, filters, dashboard design, and realistic reporting scenarios.",
    "Excel": "Cover formulas, lookup functions, conditional functions, text/date functions, PivotTables, charts, data cleaning, and practical analysis scenarios.",
    "Machine Learning": "Cover supervised and unsupervised learning, regression, classification, clustering, overfitting, feature engineering, model selection, and evaluation metrics at a Data Analyst interview level.",
    "Data Analysis & Business Cases": "Cover data cleaning, KPI selection, trend analysis, root-cause analysis, business questions, insight generation, and practical recommendations.",
    "HR & Behavioural": "Cover self-introduction, career motivation, teamwork, problem-solving, handling mistakes, communication, and workplace situations. Ask realistic behavioural questions and use follow-ups to understand the candidate's actual contribution.",
    "Mixed Interview": "Mix relevant Data Analyst interview questions across SQL, Python, Excel, statistics, Power BI, business analysis, and basic machine learning. Vary question styles rather than focusing on one topic or question type.",
}

INTERVIEW_RULES = """
You are a skilled, experienced Data Analyst interviewer. Conduct a realistic spoken interview, not a classroom lesson and not a chatbot conversation.

YOUR INTERVIEWER PERSONA AND DELIVERY:
- Sound like a real, confident, professional interviewer: attentive, calm, interested, and conversational.
- Use natural spoken English, contractions where appropriate, and varied sentence rhythm.
- Show genuine interest in answers. Use brief, varied acknowledgements when suitable, such as "All right", "That's a useful point", "I see what you mean", or "Let's explore that a little further". Do not repeat the same acknowledgement every turn.
- Ask follow-up questions that respond to what the candidate actually said. Occasionally challenge an assumption politely, as a real interviewer would.
- Be encouraging but not overly cheerful. Be serious when assessing technical accuracy. Do not sound robotic, overly formal, or like you are reading a textbook.
- Keep spoken turns concise and easy to follow. Usually use 1-3 short sentences, then ask ONE clear question.
- Do not use emojis, markdown tables, headings, bullet lists, stage directions, or emotion labels in normal interview turns. The response will be spoken aloud, so write only words that should be said.
- Do not introduce yourself with a personal name. Say you are the interviewer.

INTERVIEW FLOW:
- Ask one question at a time and wait for the candidate's answer.
- Start with a brief welcome and the first question.
- Listen to the meaning of the answer. Briefly acknowledge it, then ask a relevant follow-up or move to the next question.
- If an answer is vague, ask for a specific example or clarification.
- If it is partly correct or incorrect, explain the key issue briefly without embarrassing the candidate, then continue.
- Do not reveal the ideal answer before the candidate has tried.
- Adapt the difficulty to the selected level and demonstrated understanding.
- Do not ask a follow-up every single time. Keep the interview moving naturally.
- Do not repeat a question already asked in this interview.

QUESTION STYLE AND BALANCE:
- Use a balanced mix of conceptual/theory questions, practical business scenarios, and questions about how the candidate would solve a problem.
- Aim for roughly one-third theory/concept questions, one-third practical scenarios, and one-third questions about applying or explaining a technique. Adjust naturally to the subject.
- For SQL and Python, include BOTH theory and practical questions. Do not turn either subject into a coding test made entirely of coding exercises.
- This is an ORAL interview. Do not ask the candidate to write a long SQL query or full Python program from memory. Instead, describe a realistic situation and ask what approach, SQL clause, function, data structure, or concept they would use and why. Let them explain the steps verbally.
- You may occasionally ask the candidate to interpret a short query/code idea or describe a small piece of logic, but do not require exact syntax or character-by-character code.
- Example SQL scenario style: "You have an orders table and need to find each customer's most recent order. What approach would you take, and which SQL feature could help?"
- Example Python scenario style: "You receive a list of repeated customer IDs and need the unique IDs. Which Python data structure would you consider, and what trade-off would you keep in mind?"
- Do not use these examples verbatim unless appropriate; create varied questions at the selected difficulty.

SUBJECT FOCUS:
{subject_guidance}

SELECTED SUBJECT: {subject}
SELECTED DIFFICULTY: {difficulty}

The candidate is practising for a real Data Analyst interview. Keep the conversation useful, realistic, respectful, and focused on their actual understanding.
"""

END_PHRASES = [
    "i am done", "i'm done", "im done", "give me summary", "give me the summary",
    "give my summary", "give me feedback", "end interview", "finish interview",
    "i am finished", "i'm finished", "im finished", "that's all", "that is all",
    "we can end", "let's stop here", "lets stop here",
]


# ----------------------------- VOICE FUNCTIONS -----------------------------
class LocalMicrophoneRecorder:
    """Capture audio from the computer microphone until the user presses Stop."""
    def __init__(self):
        self.stop_event = threading.Event()
        self.frames = []
        self.thread = None
        self.is_recording = False
        self.error = None
        self.sample_rate = None
        self.sample_width = None
        self._lock = threading.Lock()

    def start(self):
        if self.is_recording:
            return
        self.stop_event.clear()
        self.frames = []
        self.error = None
        self.is_recording = True
        self.thread = threading.Thread(target=self._capture, daemon=True)
        self.thread.start()

    def _capture(self):
        try:
            with sr.Microphone() as source:
                self.sample_rate = source.SAMPLE_RATE
                self.sample_width = source.SAMPLE_WIDTH
                # No phrase timeout or silence-based submission: capture continues
                # until the user explicitly presses Stop Recording.
                while not self.stop_event.is_set():
                    frame = source.stream.read(source.CHUNK)
                    with self._lock:
                        self.frames.append(frame)
        except Exception as exc:
            self.error = f"Microphone problem: {exc}"
        finally:
            self.is_recording = False

    def stop_and_transcribe(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.thread and self.thread.is_alive():
            return "Error: The microphone did not stop. Please try again."
        if self.error:
            return f"Error: {self.error}"
        with self._lock:
            raw_audio = b"".join(self.frames)
        if not raw_audio:
            return "Error: No audio was recorded. Please try again."
        try:
            recognizer = sr.Recognizer()
            audio = sr.AudioData(raw_audio, self.sample_rate, self.sample_width)
            return recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return "Error: I could not understand the audio clearly. Please record again."
        except sr.RequestError as exc:
            return f"Error: Speech recognition service is unavailable: {exc}"
        except Exception as exc:
            return f"Error: Could not process the recording: {exc}"


def split_text_into_chunks(text, max_chars=200):
    """Split text into readable TTS chunks, never exceeding the provider limit."""
    text = " ".join((text or "").split())
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current = ""

    def add_piece(piece):
        nonlocal current
        if not piece:
            return
        candidate = f"{current} {piece}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = piece

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            add_piece(sentence)
            continue

        # A long sentence is split at word boundaries, preserving readable phrases.
        words = sentence.split()
        piece = ""
        for word in words:
            if len(word) > max_chars:
                if piece:
                    add_piece(piece)
                    piece = ""
                for offset in range(0, len(word), max_chars):
                    add_piece(word[offset:offset + max_chars])
                continue
            candidate = f"{piece} {word}".strip()
            if len(candidate) <= max_chars:
                piece = candidate
            else:
                if piece:
                    add_piece(piece)
                piece = word
        if piece:
            add_piece(piece)

    if current:
        chunks.append(current)
    return chunks


def combine_wav_chunks(audio_chunks):
    """Join PCM WAV chunks into one WAV file for continuous playback."""
    if not audio_chunks:
        return None
    if len(audio_chunks) == 1:
        return audio_chunks[0]

    output = io.BytesIO()
    with wave.open(io.BytesIO(audio_chunks[0]), "rb") as first:
        params = first.getparams()
        frames = [first.readframes(first.getnframes())]
    for chunk in audio_chunks[1:]:
        with wave.open(io.BytesIO(chunk), "rb") as part:
            part_params = part.getparams()
            if (part_params.nchannels, part_params.sampwidth, part_params.framerate,
                part_params.comptype, part_params.compname) != (
                params.nchannels, params.sampwidth, params.framerate,
                params.comptype, params.compname
            ):
                raise ValueError("Groq returned audio chunks with incompatible WAV formats.")
            frames.append(part.readframes(part.getnframes()))
    with wave.open(output, "wb") as combined:
        combined.setnchannels(params.nchannels)
        combined.setsampwidth(params.sampwidth)
        combined.setframerate(params.framerate)
        combined.setcomptype(params.comptype, params.compname)
        for frame_data in frames:
            combined.writeframes(frame_data)
    return output.getvalue()


def make_tts_audio(text, selected_voice):
    """Generate spoken audio using the selected Orpheus voice or local fallback."""
    api_key = os.getenv("GROQ_API_KEY", "")
    st.session_state.tts_error = None

    if selected_voice != "local" and api_key and api_key != "your_groq_api_key_here":
        try:
            client = Groq(api_key=api_key)
            chunks = split_text_into_chunks(text, max_chars=200)
            generated_chunks = []
            for chunk in chunks:
                response = client.audio.speech.create(
                    model=TTS_MODEL,
                    voice=selected_voice,
                    input=chunk,
                    response_format="wav",
                )
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as audio_file:
                    output_path = audio_file.name
                try:
                    response.write_to_file(output_path)
                    with open(output_path, "rb") as audio_file:
                        generated_chunks.append(audio_file.read())
                finally:
                    if os.path.exists(output_path):
                        os.remove(output_path)
            return combine_wav_chunks(generated_chunks)
        except Exception as error:
            st.session_state.tts_error = (
                f"The selected Groq voice could not be generated. The app is trying the local voice instead. Details: {error}"
            )
    elif selected_voice != "local":
        st.session_state.tts_error = "GROQ_API_KEY is missing. The app is trying the local voice instead."

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as audio_file:
            output_path = audio_file.name
        engine = pyttsx3.init()
        engine.setProperty("rate", 158)
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        engine.stop()
        try:
            with open(output_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
        finally:
            if os.path.exists(output_path):
                os.remove(output_path)
        return audio_bytes
    except Exception as error:
        st.session_state.tts_error = f"Local text-to-speech also failed: {error}"
        return None


def on_voice_change():
    """Persist the selected voice and regenerate the latest spoken response."""
    selected_label = st.session_state.get("voice_choice")
    if selected_label not in VOICE_OPTIONS:
        return
    st.session_state.tts_voice = VOICE_OPTIONS[selected_label]
    last_text = st.session_state.get("last_spoken_text")
    if last_text:
        st.session_state.last_audio = make_tts_audio(last_text, st.session_state.tts_voice)


# ----------------------------- LLM FUNCTIONS -----------------------------
def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key == "your_groq_api_key_here":
        raise ValueError("Add your Groq API key to the .env file before starting an interview.")
    return Groq(api_key=api_key)


def generate_reply(messages, max_tokens=450, temperature=0.7):
    client = get_groq_client()
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()


def build_interview_system_prompt(subject, difficulty):
    return INTERVIEW_RULES.format(
        subject=subject,
        difficulty=difficulty,
        subject_guidance=SUBJECT_GUIDANCE[subject],
    )


def create_audio_for_reply(reply):
    st.session_state.last_spoken_text = reply
    st.session_state.last_audio = make_tts_audio(reply, st.session_state.tts_voice)


def start_interview():
    system_prompt = build_interview_system_prompt(
        st.session_state.subject, st.session_state.difficulty
    )
    st.session_state.messages = [{"role": "system", "content": system_prompt}]
    st.session_state.messages.append({
        "role": "user",
        "content": (
            f"Start a {st.session_state.difficulty.lower()} level interview for {st.session_state.subject}. "
            f"The candidate's name is {st.session_state.candidate_name}. "
            "Welcome them naturally and ask the first interview question. Ask only one question."
        ),
    })
    reply = generate_reply(st.session_state.messages)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.history.append({"role": "assistant", "text": reply})
    st.session_state.current_coach_text = reply
    st.session_state.started = True
    create_audio_for_reply(reply)


def evaluate_interview():
    """Generate a natural spoken debrief, not a written report or table."""
    candidate_answers = [turn for turn in st.session_state.history if turn["role"] == "user"]
    evaluation_prompt = """
The candidate has ended the interview. Give them a concise, useful VERBAL debrief based only on the answers they actually gave.

IMPORTANT OUTPUT RULES:
- Write this as something a human interviewer would naturally say aloud directly to the candidate.
- Do NOT use a table, markdown, headings, numbered sections, bullet points, labels, or a formal report layout.
- Use 2 or 3 short natural paragraphs. Aim for about 100-150 spoken words.
- Start with a brief overall impression. Then explain the strongest area and the most important area to improve, using specific evidence from their answers.
- Include an overall score out of 10 and, where there was enough evidence, briefly mention technical knowledge and communication scores out of 10 in natural spoken sentences. Do not force precise scores if there were too few answers; say that there was not enough evidence.
- Give two or three concrete topics or skills to revise and one practical next step.
- Be honest and specific. Do not praise weak answers, invent facts, or claim the candidate demonstrated something they did not demonstrate.
- Keep the tone professional, constructive, and human. This feedback will be converted to speech, so write only words that should be spoken.
"""
    if not candidate_answers:
        evaluation_prompt += "\nThe candidate did not provide any interview answers. Explain politely that there is not enough evidence to assess their skills and suggest completing an interview with spoken answers. Do not invent scores."
    evaluation_messages = st.session_state.messages + [
        {"role": "user", "content": evaluation_prompt}
    ]
    return generate_reply(evaluation_messages, max_tokens=450, temperature=0.4)


def finish_interview():
    """End the interview and immediately generate and speak the feedback."""
    if st.session_state.feedback:
        st.session_state.ended = True
        return
    st.session_state.ended = True
    feedback = evaluate_interview()
    st.session_state.feedback = feedback
    st.session_state.current_coach_text = feedback
    st.session_state.history.append({"role": "assistant", "text": feedback})
    create_audio_for_reply(feedback)


def is_end_command(transcript):
    normalized = " ".join(transcript.lower().replace("’", "'").split())
    return any(phrase in normalized for phrase in END_PHRASES)


# ----------------------------- SESSION HELPERS -----------------------------
def reset_state():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ----------------------------- STREAMLIT APP -----------------------------
st.set_page_config(page_title=APP_NAME, page_icon="🎙️", layout="wide")

DEFAULT_VOICE_LABEL = VOICE_LABEL_BY_VALUE.get(DEFAULT_TTS_VOICE, "Orpheus - Autumn")
DEFAULTS = {
    "candidate_name": "",
    "subject": "SQL",
    "difficulty": "Intermediate",
    "tts_voice": VOICE_OPTIONS[DEFAULT_VOICE_LABEL],
    "voice_choice": DEFAULT_VOICE_LABEL,
    "started": False,
    "ended": False,
    "messages": [],
    "history": [],
    "current_user_text": "",
    "current_coach_text": "",
    "last_spoken_text": "",
    "last_audio": None,
    "tts_error": None,
    "error": None,
    "feedback": None,
    "recorder": None,
    "pending_transcript": "",
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Keep Streamlit's native default light theme. Custom CSS is limited to spacing
# and layout; text colours are inherited from the active Streamlit theme so that
# headings, captions, labels, chat messages, and sidebar text remain readable.
st.markdown("""
<style>
    .block-container {max-width: 1050px; padding-top: 2rem;}
    .main-subtitle {margin-top: -12px; margin-bottom: 24px;}
    .chat-box {border: 1px solid rgba(128,128,128,.25); border-radius: 14px; padding: 16px; margin: 10px 0;}
    .chat-label {font-weight: 700; margin-bottom: 6px;}
    .footer {font-size: .78rem; text-align: center; margin-top: 35px;}
</style>
""", unsafe_allow_html=True)

st.title("🎙️ AI Data Analyst Interview Coach")
st.markdown(
    "<div class='main-subtitle'>Practise realistic Data Analyst interviews with a voice-based AI interviewer.</div>",
    unsafe_allow_html=True,
)

# Sidebar: voice and session details. Audio playback controls handle stopping audio;
# there is intentionally no separate mute toggle.
with st.sidebar:
    st.header("Interview settings")
    st.selectbox(
        "Interviewer voice",
        list(VOICE_OPTIONS.keys()),
        key="voice_choice",
        on_change=on_voice_change,
        help="Changing the voice regenerates the latest interviewer response and applies to future responses.",
    )
    if st.session_state.started:
        st.divider()
        st.write(f"**Candidate:** {st.session_state.candidate_name}")
        st.write(f"**Subject:** {st.session_state.subject}")
        st.write(f"**Difficulty:** {st.session_state.difficulty}")
        if not st.session_state.ended:
            if st.button("End interview and get feedback", use_container_width=True):
                try:
                    with st.spinner("The interviewer is reviewing your answers..."):
                        finish_interview()
                    st.rerun()
                except Exception as error:
                    st.session_state.error = f"The interview ended, but feedback could not be generated: {error}"
                    st.rerun()
        if st.button("Start a new interview", use_container_width=True):
            reset_state()

# Interview setup
if not st.session_state.started:
    st.subheader("Set up your interview")
    st.write("Choose a subject and difficulty. The AI interviewer will ask the first question when you start.")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.candidate_name = st.text_input(
            "Your name (optional)", value=st.session_state.candidate_name,
            placeholder="Enter your name",
        )
        st.session_state.subject = st.selectbox(
            "Select interview subject", SUBJECTS, index=SUBJECTS.index(st.session_state.subject)
        )
    with col2:
        st.session_state.difficulty = st.selectbox(
            "Select difficulty", DIFFICULTIES, index=DIFFICULTIES.index(st.session_state.difficulty)
        )
        st.info(f"**Focus:** {SUBJECT_GUIDANCE[st.session_state.subject]}")

    if st.button("Start interview", type="primary", icon="🎤", use_container_width=True):
        try:
            with st.spinner("Your interviewer is preparing the first question..."):
                st.session_state.candidate_name = st.session_state.candidate_name.strip() or "Candidate"
                st.session_state.tts_voice = VOICE_OPTIONS[st.session_state.voice_choice]
                start_interview()
            st.rerun()
        except Exception as error:
            st.session_state.error = f"Could not start the interview: {error}"

    if st.session_state.error:
        st.error(st.session_state.error)
        st.session_state.error = None

else:
    st.subheader("Interview completed" if st.session_state.ended else "Interview in progress")
    st.caption(f"{st.session_state.subject} · {st.session_state.difficulty} level")

    for turn in st.session_state.history:
        speaker = "You" if turn["role"] == "user" else "AI Interviewer"
        safe_text = html.escape(turn["text"])
        st.markdown(
            f"<div class='chat-box'><div class='chat-label'>{speaker}</div>{safe_text}</div>",
            unsafe_allow_html=True,
        )

    if st.session_state.last_audio:
        st.audio(st.session_state.last_audio, format="audio/wav", autoplay=True)

    if st.session_state.tts_error:
        st.warning(st.session_state.tts_error)
        st.session_state.tts_error = None

    if st.session_state.error:
        st.error(st.session_state.error)
        st.session_state.error = None

    if not st.session_state.ended:
        st.markdown("### Your answer")
        st.caption(
            "Use your computer's microphone. Recording continues through pauses and stops only when you press Stop Recording. Your answer is not sent until you press Submit Answer."
        )
        if st.session_state.recorder is None:
            st.session_state.recorder = LocalMicrophoneRecorder()

        recorder = st.session_state.recorder
        if recorder.error and not recorder.is_recording:
            st.error(f"Could not access the microphone: {recorder.error}")
        if recorder.is_recording:
            st.warning("Recording is in progress. Speak your answer, then press Stop Recording.")
            if st.button("Stop Recording", type="secondary", use_container_width=True):
                with st.spinner("Stopping recording and converting your speech to text..."):
                    transcript = recorder.stop_and_transcribe()
                st.session_state.pending_transcript = "" if transcript.startswith("Error:") else transcript
                if transcript.startswith("Error:"):
                    st.session_state.error = transcript
                st.rerun()
        elif not st.session_state.pending_transcript:
            if st.button("Start Recording", type="primary", use_container_width=True):
                recorder.start()
                st.rerun()
        else:
            st.success("Recording stopped. Review the transcript before submitting.")
            st.text_area(
                "Recognized answer",
                value=st.session_state.pending_transcript,
                height=120,
                disabled=True,
            )
            col_submit, col_retry = st.columns(2)
            with col_submit:
                submit_answer = st.button("Submit Answer", type="primary", use_container_width=True)
            with col_retry:
                retry_recording = st.button("Record Again", use_container_width=True)

            if retry_recording:
                st.session_state.pending_transcript = ""
                st.session_state.recorder = LocalMicrophoneRecorder()
                st.rerun()

            if submit_answer:
                transcript = st.session_state.pending_transcript.strip()
                st.session_state.pending_transcript = ""
                if not transcript:
                    st.session_state.error = "The transcript is empty. Please record your answer again."
                elif is_end_command(transcript):
                    try:
                        with st.spinner("The interviewer is reviewing your answers and preparing feedback..."):
                            finish_interview()
                    except Exception as error:
                        st.session_state.error = f"The interview ended, but feedback could not be generated: {error}"
                else:
                    st.session_state.current_user_text = transcript
                    st.session_state.messages.append({"role": "user", "content": transcript})
                    st.session_state.history.append({"role": "user", "text": transcript})
                    try:
                        with st.spinner("The interviewer is considering your answer..."):
                            reply = generate_reply(st.session_state.messages)
                        st.session_state.current_coach_text = reply
                        st.session_state.messages.append({"role": "assistant", "content": reply})
                        st.session_state.history.append({"role": "assistant", "text": reply})
                        create_audio_for_reply(reply)
                    except Exception as error:
                        st.session_state.error = f"The interviewer could not respond: {error}"
                st.session_state.recorder = LocalMicrophoneRecorder()
                st.rerun()

    else:
        st.success("Interview completed. Your feedback is below and is also available as spoken audio.")
        if st.session_state.feedback:
            st.markdown("### Interviewer feedback")
            st.write(st.session_state.feedback)
        else:
            st.warning("Feedback was not generated. You can try again.")
            if st.button("Generate spoken feedback", type="primary", use_container_width=True):
                try:
                    with st.spinner("Reviewing your answers..."):
                        finish_interview()
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not generate feedback: {error}")

st.markdown(
    "<div class='footer'>AI Data Analyst Interview Coach · Voice-based interview practice</div>",
    unsafe_allow_html=True,
)
