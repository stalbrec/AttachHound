from abc import ABC, abstractmethod
from typing import List, Optional
import logging
import os
import imaplib
import email
from email.header import decode_header
import json
import sqlite3
from datetime import datetime
from utils import sanitize_filename

class Mail:
    """
    Represents a processed mail object with necessary attributes.
    """

    def __init__(
        self,
        uid: str,
        subject: str,
        sender: str,
        recipient: str,
        date: str,
        body: str,
        attachments: List[str],
    ):
        self.uid = uid
        self.subject = subject
        self.sender = sender
        self.recipient = recipient
        self.date = date
        self.body = body
        self.attachments = attachments

    def to_dict(self):
        """
        Converts the Mail object to a dictionary for easy storage.
        """
        return {
            "uid": self.uid,
            "subject": self.subject,
            "sender": self.sender,
            "recipient": self.recipient,
            "date": self.date,
            "body": self.body,
            "attachments": json.dumps(self.attachments),
        }

    def to_sqlite_db(self, conn: sqlite3.Connection):
        logging.info(f"Saving metadata for email UID {self.uid}")
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO processed_emails (uid, subject, sender, recipient, date, body, attachments)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self.uid,
                self.subject,
                self.sender,
                self.recipient,
                self.date,
                self.body,
                json.dumps(self.attachments),
            ),
        )
        conn.commit()
        logging.debug(f"Metadata for email UID {self.uid} saved to database.")

    def in_db(self, conn: sqlite3.Connection):
        return self.already_processed(self.uid, conn)

    @staticmethod
    def already_processed(uid: str, conn: sqlite3.Connection):
        """
        Check if email has already been processed.

        This function queries the 'processed_emails' table to check if an email
        with the mails' UID exists.

        Args:
            uid (str): The UID of the email to check
            conn (sqlite3.Connection): A connection object to the db.

        Returns:
            bool: True if the email has already been processed, False otherwise.
        """
        logging.debug(f"Checking if email with UID {uid} has already been processed.")
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_emails WHERE uid = ?", (uid,))
        return cursor.fetchone() is not None


class Mailbox(ABC):
    """
    Abstract class to define the interface for a mailbox.
    """

    def __init__(self, export_directory: str = "attachments"):
        self.attachment_dir = export_directory
        if not os.path.exists(self.attachment_dir):
            os.makedirs(self.attachment_dir)
            logging.info(f"Created directory for attachments: {self.attachment_dir}")
        else:
            logging.debug(f"Attachment directory already exists: {self.attachment_dir}")

    @abstractmethod
    def connect(self, email_address: str, password: str):
        pass

    @abstractmethod
    def select_folder(self, folder: str):
        pass

    @abstractmethod
    def search_emails(self) -> List[str]:
        pass

    @abstractmethod
    def get_mail(self, uid: str) -> Optional[Mail]:
        """
        Fetch and return a Mail object for the given UID.
        """
        pass

    @abstractmethod
    def close(self):
        pass


class IMAPMailbox(Mailbox):
    """
    Implementation of Mailbox using IMAP protocol.
    """

    def __init__(
        self,
        export_directory: str = "attachments",
        server: str = os.environ.get("IMAP_SERVER", "imap.gmail.com"),
        port: int = os.environ.get("IMAP_PORT", 993),
    ):
        super().__init__(export_directory)
        self.server = server
        self.port = port
        self.connection = None
        logging.debug(f"Using IMAP server: {self.server} on port {self.port}")

    def connect(self, email_address: str, password: str):
        logging.info("Connecting to the IMAP email server...")
        try:
            self.connection = imaplib.IMAP4_SSL(self.server, self.port)
            self.connection.login(email_address, password)
            logging.info(f"Connected successfully to {self.server}")
        except imaplib.IMAP4.error as e:
            logging.error(f"Authentication failed: {e}")
            raise SystemExit(
                "Invalid credentials. Please check your email and password."
            )

    def select_folder(self, folder: str):
        logging.info(f"Selecting mailbox folder: {folder}")
        result, _ = self.connection.select(folder)
        if result != "OK":
            logging.error(f"Failed to select folder {folder}.")
            raise Exception(f"Failed to select folder {folder}.")

    def search_emails(self) -> List[str]:
        logging.info("Searching for emails in the folder...")
        result, data = self.connection.uid("search", None, "ALL")
        if result != "OK":
            logging.error("Failed to search for emails.")
            return []
        uids = data[0].split()
        logging.info(f"Found {len(uids)} emails.")
        return [uid.decode() for uid in uids]

    def get_mail(self, uid: str) -> Optional[Mail]:
        logging.info(f"Fetching email with UID: {uid}")
        result, data = self.connection.uid("fetch", uid, "(RFC822)")
        if result != "OK":
            logging.warning(f"Failed to fetch email with UID: {uid}. Skipping.")
            return None

        for response_part in data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                subject = self.decode_header_value(msg["subject"])
                sender = msg.get("From")
                recipient = msg.get("To")
                date_str = msg.get("Date")
                date = self.parse_email_date(date_str)
                body = self.get_email_body(msg)
                attachments = self.get_attachments(msg, uid, subject, sender, date)

                return Mail(
                    uid=uid,
                    subject=subject,
                    sender=sender,
                    recipient=recipient,
                    date=date,
                    body=body,
                    attachments=attachments,
                )

    def decode_header_value(self, value: str) -> str:
        decoded_value, encoding = decode_header(value)[0]
        if isinstance(decoded_value, bytes):
            return decoded_value.decode(encoding or "utf-8")
        return decoded_value

    def parse_email_date(self, date_str: str) -> str:
        for date_format in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"]:
            try:
                email_datetime = datetime.strptime(date_str, date_format)
                return email_datetime.isoformat()
            except ValueError:
                logging.debug(f"Failed to parse date with format: {date_format}")
        logging.error(f"Failed to parse date: {date_str}")
        return "Unknown"

    def get_email_body(self, msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if (
                    part.get_content_type() == "text/plain"
                    and part.get("Content-Disposition") is None
                ):
                    return part.get_payload(decode=True).decode()
        else:
            return msg.get_payload(decode=True).decode()
        return ""

    def get_attachments(
        self, msg, uid: str, subject: str, sender: str, date: str
    ) -> List[str]:
        attachments = []
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            filename = part.get_filename()
            if filename:
                filename = self.decode_header_value(filename)
                sanitized_filename = sanitize_filename(filename)
                email_prefix = sanitize_filename(f"{subject}_{sender}_{date}")
                output_path = f"{self.attachment_dir}/{email_prefix}_{sanitized_filename}".replace(
                    " ", "_"
                )
                with open(output_path, "wb") as file:
                    file.write(part.get_payload(decode=True))
                attachments.append(output_path)
                logging.info(f"Attachment saved to {output_path}")
        return attachments

    def close(self):
        logging.info("Closing the mailbox connection.")
        if self.connection:
            self.connection.close()
            self.connection.logout()
