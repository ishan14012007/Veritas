from datetime import datetime, timezone
import pytest
from app.accord.services.parser import WhatsAppParser


def test_parser_standard_ios_export():
    """Verify parsing of standard iOS WhatsApp export with brackets."""
    sample = """[15/04/2026, 10:15:30] Alice: Hey everyone, total cabin bill is $750.
[15/04/2026, 10:16:00] Bob: Great! I'll pay my share.
[15/04/2026, 10:17:45] Charlie: Count me in too."""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 3
    assert parsed.unique_senders == ["Alice", "Bob", "Charlie"]
    assert parsed.system_message_count == 0

    assert parsed.messages[0].sender_name == "Alice"
    assert parsed.messages[0].message_body == "Hey everyone, total cabin bill is $750."
    assert parsed.messages[0].original_timestamp == datetime(2026, 4, 15, 10, 15, 30, tzinfo=timezone.utc)
    assert parsed.messages[0].order_index == 0


def test_parser_standard_android_export():
    """Verify parsing of standard Android WhatsApp export with hyphen."""
    sample = """15/04/2026, 14:30 - Alice: Here is the grocery receipt
15/04/2026, 14:32 - Bob: Received, thanks!"""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 2
    assert parsed.unique_senders == ["Alice", "Bob"]
    assert parsed.messages[0].sender_name == "Alice"
    assert parsed.messages[0].message_body == "Here is the grocery receipt"
    assert parsed.messages[1].sender_name == "Bob"
    assert parsed.messages[1].order_index == 1


def test_parser_different_timestamp_formats():
    """Verify parsing of various date and time formats (12h, 24h, dots, slashes, dashes)."""
    samples = [
        # 12-hour AM/PM with brackets
        "[4/15/26, 2:30 PM] UserOne: Hello",
        # Dot date separator
        "15.04.2026, 14:30 - UserOne: Hello",
        # ISO format
        "2026-04-15, 14:30:00 - UserOne: Hello",
        # 2-digit year with seconds
        "[15/04/26, 14:30:15] UserOne: Hello",
    ]
    for sample in samples:
        parsed = WhatsAppParser.parse(sample)
        assert parsed.total_messages == 1
        assert parsed.unique_senders == ["UserOne"]
        assert parsed.messages[0].message_body == "Hello"
        assert parsed.messages[0].original_timestamp is not None


def test_parser_multiline_messages():
    """Verify that multiline message lines are appended to the preceding message."""
    sample = """[15/04/2026, 11:00:00] Alice: Here is the itemized list:
- Cabin: $600
- Groceries: $120
- Fuel: $80
[15/04/2026, 11:05:00] Bob: Sounds good to me."""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 2
    alice_msg = parsed.messages[0]
    assert alice_msg.sender_name == "Alice"
    assert "- Cabin: $600" in alice_msg.message_body
    assert "- Groceries: $120" in alice_msg.message_body
    assert "- Fuel: $80" in alice_msg.message_body

    bob_msg = parsed.messages[1]
    assert bob_msg.sender_name == "Bob"
    assert bob_msg.message_body == "Sounds good to me."


def test_parser_messages_with_punctuation_and_special_characters():
    """Verify handling of complex sender names, phone numbers, punctuation and emojis."""
    sample = """[15/04/2026, 12:00:00] +1 (415) 555-0199: Hello! "Can we meet at 3?"
[15/04/2026, 12:01:00] Alice (Trip Lead): Sure, let's meet! 🚗🏕️"""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 2
    assert "+1 (415) 555-0199" in parsed.unique_senders
    assert "Alice (Trip Lead)" in parsed.unique_senders
    assert 'Hello! "Can we meet at 3?"' in parsed.messages[0].message_body
    assert "🚗🏕️" in parsed.messages[1].message_body


def test_parser_system_messages():
    """Verify that group events and encryption notices are identified as system messages."""
    sample = """[15/04/2026, 09:00:00] Messages and calls are end-to-end encrypted.
[15/04/2026, 09:01:00] Alice created group "Weekend Retreat"
[15/04/2026, 09:02:00] Alice added Bob and Charlie
[15/04/2026, 09:05:00] Alice: Welcome everyone!
[15/04/2026, 09:10:00] Bob left"""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 5
    assert parsed.unique_senders == ["Alice"]  # Only Alice sent regular messages
    assert parsed.system_message_count == 4

    assert parsed.messages[0].is_system_message is True
    assert parsed.messages[0].sender_name is None

    assert parsed.messages[3].is_system_message is False
    assert parsed.messages[3].sender_name == "Alice"

    assert parsed.messages[4].is_system_message is True


def test_parser_media_placeholders():
    """Verify that media attachment placeholders are preserved as valid messages."""
    sample = """[15/04/2026, 13:00:00] Bob: <Media omitted>
[15/04/2026, 13:01:00] Charlie: image omitted
[15/04/2026, 13:02:00] Alice: audio omitted"""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 3
    assert parsed.messages[0].message_body == "<Media omitted>"
    assert parsed.messages[1].message_body == "image omitted"
    assert parsed.messages[2].message_body == "audio omitted"


def test_parser_malformed_lines_and_leading_text():
    """Verify that lines preceding any timestamp header are not silently discarded."""
    sample = """This is a pre-header note about expenses.
[15/04/2026, 14:00:00] Alice: Hey
Random line without date in middle of nowhere
[15/04/2026, 14:05:00] Bob: Okay"""
    parsed = WhatsAppParser.parse(sample)

    # First line preserved as initial message
    assert parsed.messages[0].message_body == "This is a pre-header note about expenses."
    assert parsed.messages[0].is_system_message is True

    # Alice's message contains the middle malformed line as continuation
    assert "Random line without date" in parsed.messages[1].message_body

    assert parsed.messages[2].sender_name == "Bob"


def test_parser_plain_text_fallback():
    """Verify that pasted text with 'Sender: Message' lines parses cleanly."""
    sample = """Alice: I paid $400 for hotel
Bob: I will cover $200
Charlie: I will cover $200"""
    parsed = WhatsAppParser.parse(sample)

    assert parsed.total_messages == 3
    assert parsed.unique_senders == ["Alice", "Bob", "Charlie"]
    assert parsed.messages[0].sender_name == "Alice"
    assert parsed.messages[0].message_body == "I paid $400 for hotel"

