# Multilingual Profile Page 🌐

## Overview
We are building a **Multilingual profile page** so that users worldwide can present themselves in their own language and script. The page must be encoding-safe end to end (UTF-8), handle right-to-left scripts, and render emoji correctly.

## Requirements

- **表示名は任意のスクリプトで入力できること。** The display name field must accept any Unicode script — Latin, 日本語 (Japanese), Deutsch mit Umlauten (Fußgänger, Straße), and العربية (Arabic). No characters may be stripped or mangled on save or render. 📊

- **Rechts-nach-links-Unterstützung für Arabisch.** When the profile language is Arabic (مرحبا بك في ملفك الشخصي), the layout, text alignment, and cursor behavior must switch to right-to-left (RTL). Mixed LTR/RTL content in a single line must render with correct bidirectional ordering.

- **Emoji dürfen in der Biografie verwendet werden.** The bio field must fully support emoji, including multi-codepoint sequences and ZWJ sequences (🔐, 📊, ✅, 👩‍💻, 🇯🇵). Emoji must persist round-trip and never corrupt into mojibake.

- **Unicode-safe truncation.** When a display name or bio exceeds its maximum length, truncation must operate on grapheme clusters, never on raw bytes or half a surrogate pair. Truncating "こんにちは世界" or "👩‍💻👩‍💻" must never split a character or emoji sequence in the middle. Append an ellipsis (…) after safe truncation. ✅

## Notes
All storage, transport, and rendering layers must declare and honor UTF-8. 🔐
