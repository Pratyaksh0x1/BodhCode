"""Language catalogue and validation utilities for user preferred language."""

from pydantic import BaseModel, ConfigDict


class Language(BaseModel):
    """Supported language descriptor."""

    model_config = ConfigDict(frozen=True)

    code: str
    english_name: str
    native_name: str
    rtl: bool = False


# Canonical list of supported languages (ordered by English name for UI scannability)
SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    Language(code="ar", english_name="Arabic", native_name="العربية", rtl=True),
    Language(code="bn", english_name="Bengali", native_name="বাংলা", rtl=False),
    Language(code="zh", english_name="Chinese", native_name="中文", rtl=False),
    Language(code="cs", english_name="Czech", native_name="Čeština", rtl=False),
    Language(code="nl", english_name="Dutch", native_name="Nederlands", rtl=False),
    Language(code="en", english_name="English", native_name="English", rtl=False),
    Language(code="fa", english_name="Persian", native_name="فارسی", rtl=True),
    Language(code="fr", english_name="French", native_name="Français", rtl=False),
    Language(code="de", english_name="German", native_name="Deutsch", rtl=False),
    Language(code="el", english_name="Greek", native_name="Ελληνικά", rtl=False),
    Language(code="he", english_name="Hebrew", native_name="עברית", rtl=True),
    Language(code="hi", english_name="Hindi", native_name="हिन्दी", rtl=False),
    Language(code="hu", english_name="Hungarian", native_name="Magyar", rtl=False),
    Language(code="id", english_name="Indonesian", native_name="Bahasa Indonesia", rtl=False),
    Language(code="it", english_name="Italian", native_name="Italiano", rtl=False),
    Language(code="ja", english_name="Japanese", native_name="日本語", rtl=False),
    Language(code="ko", english_name="Korean", native_name="한국어", rtl=False),
    Language(code="mr", english_name="Marathi", native_name="मराठी", rtl=False),
    Language(code="pl", english_name="Polish", native_name="Polski", rtl=False),
    Language(code="pt", english_name="Portuguese", native_name="Português", rtl=False),
    Language(code="ro", english_name="Romanian", native_name="Română", rtl=False),
    Language(code="ru", english_name="Russian", native_name="Русский", rtl=False),
    Language(code="es", english_name="Spanish", native_name="Español", rtl=False),
    Language(code="sv", english_name="Swedish", native_name="Svenska", rtl=False),
    Language(code="ta", english_name="Tamil", native_name="தமிழ்", rtl=False),
    Language(code="te", english_name="Telugu", native_name="తెలుగు", rtl=False),
    Language(code="th", english_name="Thai", native_name="ไทย", rtl=False),
    Language(code="tr", english_name="Turkish", native_name="Türkçe", rtl=False),
    Language(code="uk", english_name="Ukrainian", native_name="Українська", rtl=False),
    Language(code="ur", english_name="Urdu", native_name="اردو", rtl=True),
    Language(code="vi", english_name="Vietnamese", native_name="Tiếng Việt", rtl=False),
)

_LANG_MAP: dict[str, Language] = {lang.code: lang for lang in SUPPORTED_LANGUAGES}


def is_supported(code: str) -> bool:
    """Check if an ISO 639-1 language code is supported."""
    return code.lower().strip() in _LANG_MAP


def get_language(code: str) -> Language | None:
    """Retrieve Language metadata by ISO 639-1 code."""
    return _LANG_MAP.get(code.lower().strip())
