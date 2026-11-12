import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple


@dataclass
class ParsedMessage:
    order_index: int
    sender_name: Optional[str]
    message_body: str
    original_timestamp: Optional[datetime]
    is_system_message: bool


@dataclass
class ParsedConversation:
    messages: List[ParsedMessage]
    unique_senders: List[str]
    total_messages: int
    system_message_count: int


# Known WhatsApp system notification markers when formatted as "timestamp - text" without colon
SYSTEM_NOTIFICATION_PATTERNS = [
    r"messages and calls are end-to-end encrypted",
    r"created group",
    r"changed the subject to",
    r"changed this group's icon",
    r"added",
    r"removed",
    r"left",
    r"security code changed",
    r"changed their phone number",
    r"you're now an admin",
    r"disappearing messages",
]


class WhatsAppParser:
    """Independent parsing engine for exported WhatsApp transcripts and formatted conversations."""

    # Regex 1: iOS bracketed format: [DD/MM/YY, HH:MM:SS] Sender: Message OR [DD/MM/YY, HH:MM:SS] System Message
    # Handles brackets, commas, periods, slashes, dashes in dates, and 12h/24h timestamps
    IOS_PATTERN = re.compile(
        r"^\[(?P<date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),?\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f\xa0]?[apAP][mM])?)\]\s+(?:(?P<sender>[^:]+?):\s+)?(?P<body>.*)$"
    )

    # Regex 2: Android hyphen format: DD/MM/YYYY, HH:MM - Sender: Message OR DD/MM/YYYY, HH:MM - System Message
    ANDROID_PATTERN = re.compile(
        r"^(?P<date>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}),?\s+(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:[\s\u202f\xa0]?[apAP][mM])?)\s+-\s+(?:(?P<sender>[^:]+?):\s+)?(?P<body>.*)$"
    )

    # Regex 3: Plain line format: "Sender: Message" without timestamp
    SENDER_COLON_PATTERN = re.compile(
        r"^(?P<sender>[A-Za-z0-9_+\-(). ]{1,50}):\s+(?P<body>.+)$"
    )

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Strip invisible unicode markers (e.g. LTR mark \u200e, narrow NBSP \u202f)."""
        if not text:
            return ""
        # Remove LTR / RTL direction marks
        text = text.replace("\u200e", "").replace("\u200f", "")
        # Normalize narrow no-break space and non-breaking space
        text = text.replace("\u202f", " ").replace("\xa0", " ")
        return text

    @classmethod
    def parse_datetime(cls, date_str: str, time_str: str) -> Optional[datetime]:
        """Attempt to parse date and time strings into a timezone-aware UTC datetime."""
        clean_d = date_str.strip()
        clean_t = time_str.strip().upper()
        # Normalize multiple spaces
        full_dt_str = f"{clean_d} {clean_t}"

        formats = [
            # Day first, 4-digit year, 24-hour
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d-%m-%Y %H:%M:%S",
            "%d-%m-%Y %H:%M",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            # Day first, 2-digit year, 24-hour
            "%d/%m/%y %H:%M:%S",
            "%d/%m/%y %H:%M",
            "%d-%m-%y %H:%M:%S",
            "%d-%m-%y %H:%M",
            "%d.%m.%y %H:%M:%S",
            "%d.%m.%y %H:%M",
            # Month first (US format), 4-digit year
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            # Month first (US format), 2-digit year
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%y %H:%M",
            # 12-hour AM/PM formats
            "%d/%m/%Y %I:%M:%S %p",
            "%d/%m/%Y %I:%M %p",
            "%d/%m/%y %I:%M:%S %p",
            "%d/%m/%y %I:%M %p",
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%y %I:%M:%S %p",
            "%m/%d/%y %I:%M %p",
            # ISO formats
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(full_dt_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None

    @classmethod
    def is_known_system_text(cls, text: str) -> bool:
        """Check if message body matches common WhatsApp system notifications."""
        lower_body = text.lower()
        return any(re.search(pat, lower_body) for pat in SYSTEM_NOTIFICATION_PATTERNS)

    @classmethod
    def parse(cls, raw_transcript: str) -> ParsedConversation:
        """Parse raw WhatsApp export transcript or pasted conversation.
        Handles multiline messages, system messages, media markers, and malformed lines.
        Never silently discards content.
        """
        cleaned_transcript = cls.clean_text(raw_transcript)
        lines = cleaned_transcript.splitlines()

        # If transcript contains no WhatsApp timestamp headers, delegate to plain text parser
        has_whatsapp_header = any(
            cls.IOS_PATTERN.match(l.strip()) or cls.ANDROID_PATTERN.match(l.strip())
            for l in lines
            if l.strip()
        )
        if not has_whatsapp_header:
            return cls.parse_plain_text(cleaned_transcript)

        parsed_messages: List[ParsedMessage] = []
        unique_senders: Set[str] = set()
        system_count = 0
        order_index = 0

        current_msg: Optional[ParsedMessage] = None

        for raw_line in lines:
            line = raw_line.rstrip("\r\n")

            # Check if this line starts a new message (iOS format or Android format)
            match_ios = cls.IOS_PATTERN.match(line)
            match_android = cls.ANDROID_PATTERN.match(line)
            match = match_ios or match_android

            if match:
                # Flush existing message if any
                if current_msg is not None:
                    parsed_messages.append(current_msg)

                date_part = match.group("date")
                time_part = match.group("time")
                sender_part = match.group("sender")
                body_part = match.group("body")

                parsed_dt = cls.parse_datetime(date_part, time_part)

                # Determine if it is a system message
                # A message without sender_part or matching system notification patterns is a system message
                if not sender_part or cls.is_known_system_text(body_part):
                    # If sender was somehow captured as part of system text (e.g. "Alice added Bob")
                    # but there was no colon separating sender and message
                    final_body = f"{sender_part}: {body_part}" if sender_part and body_part else (sender_part or body_part)
                    is_system = True
                    sender_name = None
                    system_count += 1
                else:
                    is_system = False
                    sender_name = sender_part.strip()
                    unique_senders.add(sender_name)
                    final_body = body_part

                current_msg = ParsedMessage(
                    order_index=order_index,
                    sender_name=sender_name,
                    message_body=final_body,
                    original_timestamp=parsed_dt,
                    is_system_message=is_system,
                )
                order_index += 1

            elif current_msg is not None:
                # Multiline continuation: append line to existing message body
                current_msg.message_body += f"\n{line}"

            else:
                # Lines appearing before any matched timestamp header
                # Do NOT silently discard: capture as an initial system message
                if line.strip():
                    current_msg = ParsedMessage(
                        order_index=order_index,
                        sender_name=None,
                        message_body=line,
                        original_timestamp=None,
                        is_system_message=True,
                    )
                    order_index += 1
                    system_count += 1

        # Flush final message
        if current_msg is not None:
            parsed_messages.append(current_msg)

        # If no WhatsApp headers were matched at all, fallback to plain text parsing
        if not parsed_messages and cleaned_transcript.strip():
            return cls.parse_plain_text(cleaned_transcript)

        return ParsedConversation(
            messages=parsed_messages,
            unique_senders=sorted(list(unique_senders)),
            total_messages=len(parsed_messages),
            system_message_count=system_count,
        )

    @classmethod
    def parse_plain_text(cls, raw_text: str) -> ParsedConversation:
        """Fallback parser for plain pasted text without timestamps (e.g. 'Alice: Hello\nBob: Hi')."""
        lines = cls.clean_text(raw_text).splitlines()
        parsed_messages: List[ParsedMessage] = []
        unique_senders: Set[str] = set()
        system_count = 0
        order_index = 0

        current_msg: Optional[ParsedMessage] = None

        for raw_line in lines:
            line = raw_line.rstrip("\r\n")
            if not line.strip() and current_msg is None:
                continue

            match = cls.SENDER_COLON_PATTERN.match(line.strip())
            if match:
                if current_msg is not None:
                    parsed_messages.append(current_msg)

                sender_name = match.group("sender").strip()
                body = match.group("body").strip()
                unique_senders.add(sender_name)

                current_msg = ParsedMessage(
                    order_index=order_index,
                    sender_name=sender_name,
                    message_body=body,
                    original_timestamp=None,
                    is_system_message=False,
                )
                order_index += 1
            elif current_msg is not None:
                current_msg.message_body += f"\n{line}"
            else:
                # Line without sender prefix
                if line.strip():
                    current_msg = ParsedMessage(
                        order_index=order_index,
                        sender_name=None,
                        message_body=line,
                        original_timestamp=None,
                        is_system_message=True,
                    )
                    order_index += 1
                    system_count += 1

        if current_msg is not None:
            parsed_messages.append(current_msg)

        return ParsedConversation(
            messages=parsed_messages,
            unique_senders=sorted(list(unique_senders)),
            total_messages=len(parsed_messages),
            system_message_count=system_count,
        )
