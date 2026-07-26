"""Fixed-voice multilingual narration for the curated final-demo page."""

import os
from pathlib import Path

from fastapi import HTTPException, status

from backend.shared.artifact_paths import atomic_write_bytes

from .audio import AudioError, synthesize
from .config import AUDIO_DIR


FINAL_DEMO_STORIES = {
    "student-en": {
        "title": "The Notice Board",
        "language": "en",
        "perspective": "A student organiser",
        "voice_id": "s3TPKV1kjDlVtZbl4Ksh",
        "text": "After Suryanagar's re-examination, Mira raised a notice: publish the process, protect every student, and let daylight answer the questions.",
    },
    "guardian-hi": {
        "title": "अधूरी खबर", "language": "hi", "perspective": "A parent waiting for clarity",
        "voice_id": "FmBhnvP58BK0vz65OOj7",
        "text": "सूर्यनगर में रवि ने बेटी से कहा: हमें तुरंत फैसला नहीं चाहिए, बस साफ जांच और हर मेहनती छात्र के लिए न्याय चाहिए।",
    },
    "reporter-ta": {
        "title": "கேள்விகளின் வரைபடம்", "language": "ta", "perspective": "A local reporter",
        "voice_id": "eh0hAHy3N3C9DE0uyHHD",
        "text": "சூரியநகரில் காவ்யா ஆதாரம், கேள்வி, தீராத உண்மை எனப் பிரித்தார். அவரது செய்தி தீர்ப்பு அல்ல; ஒரு தெளிவான வரைபடம்.",
    },
    "official-bn": {
        "title": "আলোর ঘর", "language": "bn", "perspective": "An examination official",
        "voice_id": "70QpbCWFDvTpWo8ZKOUb",
        "text": "সূর্যনগরে অনিরুদ্ধ জানতেন আশ্বাস যথেষ্ট নয়। স্বচ্ছতা মানে প্রক্রিয়াটি দেখা যায়, আর তদন্ত তার কাজ করতে পারে।",
    },
}

# The final-demo Tamil narration is intentionally a complete, fictional
# perspective. It keeps the real case's uncertainty as uncertainty and is
# paced for a short demo listen rather than a one-line TTS smoke test.
FINAL_DEMO_STORIES["reporter-ta"]["text"] = (
    "சூரியநகரில் மறுதேர்வு அறிவிப்பு வந்த காலையில், காவ்யா அலுவலகத்துக்கு முன்பே "
    "வந்து அமர்ந்தாள். அவள் எழுத வேண்டியது ஒரு தீர்ப்பு அல்ல; கேள்விகளின் வரைபடம். "
    "ஒரு மாணவி தனது அனுமதி அட்டையை கைப்பையில் எத்தனை முறை பார்த்தாள். ஒரு தந்தை "
    "மீண்டும் பயணம் செய்ய வேண்டிய செலவை எண்ணினார். பள்ளி வாசலில் நின்ற ஆசிரியர், "
    "வதந்தியை விட அதிகாரப்பூர்வ அறிவிப்பை முதலில் படிக்கச் சொன்னார்.\n\n"
    "காவ்யாவின் குறிப்பேட்டில் மூன்று வரிசைகள் இருந்தன: உறுதிப்படுத்தப்பட்ட தகவல், "
    "விசாரணையில் உள்ள கேள்வி, இன்னும் நிரூபிக்கப்படாத கூற்று. அந்த மூன்றையும் கலக்காமல் "
    "வைத்தால் தான் வாசகர்கள் தங்களுக்கான முடிவை எடுக்க முடியும் என்று அவள் நம்பினாள். "
    "யாரோ ஒருவர் பகிர்ந்த ஒரு படத்தை மட்டும் பார்த்து பயப்பட வேண்டாம்; அதே நேரத்தில் "
    "பயந்தவர்களின் குரலை புறக்கணிக்கவும் கூடாது.\n\n"
    "மறுதேர்வு நாளில் மழை பெய்யவில்லை. இருந்தும் பேருந்து நிறுத்தத்தில் குடைகள் திறந்தே "
    "இருந்தன; வெயிலுக்காக அல்ல, அறியாத நாளுக்காக. காவ்யா தனது பதிவியில் எழுதினாள்: "
    "நம்பிக்கை என்பது கேள்விகள் இல்லாத நிலை அல்ல. கேள்விகளுக்கு பதில் வரும் வழி திறந்த "
    "இருப்பதே நம்பிக்கை.\n\n"
    "மாலை, அவள் செய்தியை அனுப்பும் முன் ஒரு முறை மீண்டும் வாசித்தாள். மாணவர்களின் "
    "உழைப்பை கதையின் மையத்தில் வைத்தாள். விசாரணைக்கு அதன் நேரத்தை கொடுத்தாள். "
    "உறுதி செய்யப்படாததை உறுதியாக எழுதவில்லை. பின்னர் தொலைபேசியை மேசையில் வைத்து, "
    "நகரம் அமைதியாக தனது அடுத்த பதிலை எதிர்பார்க்கட்டும் என்று நினைத்தாள்."
)

FINAL_DEMO_STORIES["official-bn"]["text"] = (
    "সুর্যনগরের পরীক্ষা দপ্তরে অনিরুদ্ধ প্রতিদিন সবার আগে আলো জ্বালাতেন। "
    "সেই সকালে তিনি জানালার পাশে দাঁড়িয়ে দেখলেন, বাইরে অপেক্ষা করছে ছাত্রছাত্রী, "
    "অভিভাবক, আর তাদের সঙ্গে অসংখ্য প্রশ্ন। পুনঃপরীক্ষার খবর কারও মুখে স্বস্তি, "
    "কারও মুখে আবার নতুন ক্লান্তি হয়ে এসেছে।\n\n"
    "অনিরুদ্ধের কাজ ছিল নিয়ম মেনে দরজা খোলা, কাগজ গোনা, সময় লেখা। কিন্তু তিনি জানতেন, "
    "একটি নিয়মের পেছনে মানুষের বহু বছরের প্রস্তুতি থাকে। তাই কাউন্টারের সামনে দাঁড়ানো "
    "প্রতিটি মানুষকে তিনি একই কথা বলতেন: সরকারি তথ্য দেখুন, সন্দেহ থাকলে জানান, আর "
    "শোনা কথাকে সত্য ধরে নেবেন না। এই কথাগুলো সহজ ছিল, কিন্তু উদ্বেগের দিনে সহজ কথাই "
    "সবচেয়ে কঠিন হয়ে ওঠে।\n\n"
    "দুপুরে একটি মেয়ে এসে বলল, অনলাইনে নাকি আবার নতুন খবর ছড়িয়েছে। অনিরুদ্ধ তাকে "
    "স্ক্রিনের দিকে নয়, নোটিস বোর্ডের দিকে নিয়ে গেলেন। সেখানে যা নিশ্চিত, তা লেখা আছে; "
    "যা তদন্তে আছে, তার পাশে তদন্তের কথাও লেখা আছে। মেয়েটি কিছুক্ষণ চুপ করে রইল, "
    "তারপর বলল, সব উত্তর আজ না পেলেও অন্তত কোন প্রশ্নটি খোলা আছে তা জানা গেল।\n\n"
    "সন্ধ্যায় অফিস ফাঁকা হলে অনিরুদ্ধ শেষবারের মতো তালা পরীক্ষা করলেন। তাঁর মনে হলো, "
    "স্বচ্ছতা মানে শুধু আশ্বাস নয়; মানুষ যেন প্রক্রিয়াটি দেখতে পারে, প্রশ্ন করতে পারে, "
    "আর উত্তর না পাওয়া পর্যন্ত অপেক্ষাটাও সম্মানের সঙ্গে কাটাতে পারে। বাইরে শহরের আলো "
    "জ্বলছিল। অনিরুদ্ধ ভাবলেন, আস্থা হয়তো একদিনে ফেরে না। তবু প্রতিটি পরিষ্কার নোটিস, "
    "প্রতিটি খোলা দরজা, তাকে ফেরার একটি পথ দেখায়।"
)

# Each final-demo language may use a separately supplied ElevenLabs account.
# The default key remains the fallback so local development keeps working.
FINAL_DEMO_API_KEY_ENV = {
    "student-en": "ELEVENLABS_FINAL_DEMO_ENGLISH_API_KEY",
    "guardian-hi": "ELEVENLABS_FINAL_DEMO_HINDI_API_KEY",
    "reporter-ta": "ELEVENLABS_FINAL_DEMO_TAMIL_API_KEY",
    "official-bn": "ELEVENLABS_FINAL_DEMO_BENGALI_API_KEY",
}

# These four demo narrations are pre-rendered and supplied for the live pitch.
# Keeping their human-readable names lets the UI serve them without issuing a
# fresh provider call or spending TTS quota.
FINAL_DEMO_AUDIO_FILENAMES = {
    "student-en": "english.mp3",
    "guardian-hi": "hindi.mp3",
    "reporter-ta": "tamil.mp3",
    "official-bn": "bengali.mp3",
}


def _story(story_id: str) -> dict[str, str]:
    story = FINAL_DEMO_STORIES.get(story_id)
    if story is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown final-demo story")
    return story


def _path(story_id: str) -> Path:
    return AUDIO_DIR / "final-demo" / FINAL_DEMO_AUDIO_FILENAMES[story_id]


def generate_final_demo_audio(story_id: str, force: bool = False) -> dict[str, str]:
    story = _story(story_id)
    path = _path(story_id)
    if not path.is_file() or force:
        try:
            api_key = os.getenv(FINAL_DEMO_API_KEY_ENV[story_id])
            atomic_write_bytes(path, synthesize(story["language"], story["text"], story["voice_id"], api_key=api_key))
        except AudioError:
            raise
    return {"story_id": story_id, "title": story["title"], "language": story["language"], "path": str(path)}


def final_demo_story(story_id: str) -> dict[str, str]:
    return _story(story_id)


def final_demo_audio_path(story_id: str) -> Path:
    path = _path(story_id)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Final-demo narration has not been generated yet")
    return path
