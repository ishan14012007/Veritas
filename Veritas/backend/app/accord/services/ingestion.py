import uuid
from typing import Optional, Tuple
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.accord.models.conversation import Conversation
from app.accord.models.message import Message
from app.accord.models.participant import Participant
from app.accord.services.parser import WhatsAppParser, ParsedConversation

# Configurable size limits
MAX_PASTED_TEXT_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_UPLOAD_FILE_BYTES = 5 * 1024 * 1024  # 5 MB


class IngestionService:
    """Orchestrates parsing, participant deduplication, and database persistence
    for ACCORD conversations.
    """

    @classmethod
    def _validate_content_bytes(cls, content_bytes: bytes, max_bytes: int, label: str) -> str:
        """Validate size, encoding, and non-emptiness of text content."""
        if not content_bytes or not content_bytes.strip():
            raise HTTPException(
                status_code=422,
                detail=f"{label} cannot be empty or contain only whitespace.",
            )

        if len(content_bytes) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{label} exceeds maximum allowed size of {max_bytes // (1024 * 1024)} MB.",
            )

        # Validate that the bytes are decodable as text and not binary
        if b"\x00" in content_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid file format: Binary files are not permitted. Please upload a plain-text WhatsApp export (.txt).",
            )

        # Try standard encodings
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                decoded = content_bytes.decode(encoding)
                if not decoded.strip():
                    raise HTTPException(
                        status_code=422,
                        detail=f"{label} contains only whitespace.",
                    )
                return decoded
            except UnicodeDecodeError:
                continue

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to decode text file. Ensure the file is encoded in UTF-8.",
        )

    @classmethod
    async def process_and_persist(
        cls,
        db: AsyncSession,
        owner_id: uuid.UUID,
        raw_text: str,
        source_type: str,
        title: Optional[str] = None,
        original_filename: Optional[str] = None,
    ) -> Conversation:
        """Parse raw text, identify participants, create messages, and commit transaction."""
        # Parse transcript
        parsed: ParsedConversation = WhatsAppParser.parse(raw_text)

        if not parsed.messages:
            raise HTTPException(
                status_code=422,
                detail="Unable to extract any messages from the provided text.",
            )

        # Determine sensible default title if not provided
        if not title or not title.strip():
            if original_filename:
                # Strip extension from filename
                title = original_filename.rsplit(".", 1)[0][:100]
            elif parsed.unique_senders:
                title = f"Chat with {', '.join(parsed.unique_senders[:3])}"[:100]
            else:
                title = "Imported Conversation"

        # 1. Create Conversation record
        conversation = Conversation(
            owner_id=owner_id,
            title=title.strip(),
            source_type=source_type,
            original_filename=original_filename,
            raw_transcript=raw_text,
            processing_status="COMPLETED",
        )
        db.add(conversation)
        await db.flush()  # Populates conversation.id

        # 2. Identify unique participants and deduplicate
        sender_to_participant_id = {}
        for sender in parsed.unique_senders:
            clean_sender = sender.strip()
            sender_ident = clean_sender.lower()

            participant = Participant(
                conversation_id=conversation.id,
                display_name=clean_sender,
                sender_identifier=sender_ident,
            )
            db.add(participant)
            await db.flush()
            sender_to_participant_id[clean_sender] = participant.id

        # 3. Create Messages preserving order_index
        for parsed_msg in parsed.messages:
            participant_id = None
            if parsed_msg.sender_name:
                participant_id = sender_to_participant_id.get(parsed_msg.sender_name.strip())

            msg = Message(
                conversation_id=conversation.id,
                participant_id=participant_id,
                sender_name=parsed_msg.sender_name.strip() if parsed_msg.sender_name else None,
                message_body=parsed_msg.message_body,
                original_timestamp=parsed_msg.original_timestamp,
                order_index=parsed_msg.order_index,
                is_system_message=parsed_msg.is_system_message,
            )
            db.add(msg)

        await db.commit()
        await db.refresh(conversation)
        return conversation

    @classmethod
    async def ingest_pasted_text(
        cls,
        db: AsyncSession,
        owner_id: uuid.UUID,
        content: str,
        title: Optional[str] = None,
    ) -> Conversation:
        """Ingest pasted conversation text."""
        content_bytes = content.encode("utf-8")
        clean_text = cls._validate_content_bytes(content_bytes, MAX_PASTED_TEXT_BYTES, "Pasted conversation text")
        return await cls.process_and_persist(
            db=db,
            owner_id=owner_id,
            raw_text=clean_text,
            source_type="PASTED_TEXT",
            title=title,
            original_filename=None,
        )

    @classmethod
    async def ingest_whatsapp_file(
        cls,
        db: AsyncSession,
        owner_id: uuid.UUID,
        file: UploadFile,
        title: Optional[str] = None,
    ) -> Conversation:
        """Ingest uploaded WhatsApp .txt export file."""
        if not file.filename or not file.filename.lower().endswith(".txt"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only plain-text WhatsApp export files (.txt) are accepted.",
            )

        content_bytes = await file.read()
        clean_text = cls._validate_content_bytes(content_bytes, MAX_UPLOAD_FILE_BYTES, "Uploaded WhatsApp file")

        # Sanitize original filename (prevent path traversal)
        safe_filename = file.filename.replace("/", "_").replace("\\", "_")

        return await cls.process_and_persist(
            db=db,
            owner_id=owner_id,
            raw_text=clean_text,
            source_type="WHATSAPP_EXPORT",
            title=title,
            original_filename=safe_filename,
        )
