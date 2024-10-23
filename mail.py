from abc import ABC, abstractmethod
from exchangelib import Credentials, Account, Configuration, Message, FileAttachment
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

    Attributes:
        uid (str): The unique identifier of the mail.
        subject (str): The subject of the mail.
        sender (str): The email address of the sender.
        recipient (str): The email address of the recipient.
        date (str): The date when the mail was sent.
        body (str): The body content of the mail.
        attachments (List[str]): List of attachment file paths associated with the mail.
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
        """
        Initializes the Mail object.

        Args:
            uid (str): Unique identifier of the email.
            subject (str): Subject of the email.
            sender (str): Sender's email address.
            recipient (str): Recipient's email address.
            date (str): Date when the email was sent.
            body (str): Body content of the email.
            attachments (List[str]): List of attachment file paths.
        """
        self.uid = uid
        self.subject = subject
        self.sender = sender
        self.recipient = recipient
        self.date = date
        self.body = body
        self.attachments = attachments

    def to_dict(self):
        """
        Converts the Mail object to a dictionary format.

        Returns:
            dict: The email data in dictionary form, including UID, subject, sender, recipient, date, body, and attachments.
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
        """
        Save the email metadata to the SQLite database.

        Args:
            conn (sqlite3.Connection): Connection object to the SQLite database.
        """
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

    def in_db(self, conn: sqlite3.Connection) -> bool:
        """
        Check if the email is already processed in the database.

        Args:
            conn (sqlite3.Connection): Connection object to the SQLite database.

        Returns:
            bool: True if the email is already processed, False otherwise.
        """
        return self.already_processed(self.uid, conn)

    @staticmethod
    def already_processed(uid: str, conn: sqlite3.Connection) -> bool:
        """
        Check if an email has already been processed.

        Args:
            uid (str): The UID of the email to check.
            conn (sqlite3.Connection): Connection object to the SQLite database.

        Returns:
            bool: True if the email has already been processed, False otherwise.
        """
        logging.debug(f"Checking if email with UID {uid} has already been processed.")
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_emails WHERE uid = ?", (uid,))
        return cursor.fetchone() is not None


class Mailbox(ABC):
    """
    Abstract class that defines the interface for a mailbox.

    Attributes:
        attachment_dir (str): Directory where email attachments will be saved.
    """

    def __init__(self, export_directory: str = "attachments"):
        """
        Initializes the Mailbox class with an attachment directory.

        Args:
            export_directory (str): Directory to save email attachments.
        """
        self.attachment_dir = export_directory
        if not os.path.exists(self.attachment_dir):
            os.makedirs(self.attachment_dir)
            logging.info(f"Created directory for attachments: {self.attachment_dir}")
        else:
            logging.debug(f"Attachment directory already exists: {self.attachment_dir}")

    @abstractmethod
    def connect(self, email_address: str, password: str):
        """
        Connects to the mailbox server.

        Args:
            email_address (str): Email address used to log into the mailbox.
            password (str): Password for the email account.
        """
        pass

    @abstractmethod
    def select_folder(self, folder: str):
        """
        Selects a folder in the mailbox.

        Args:
            folder (str): Name of the folder to select (e.g., "inbox").
        """
        pass

    @abstractmethod
    def search_emails(self) -> List[str]:
        """
        Searches for emails in the selected folder.

        Returns:
            List[str]: List of email UIDs found in the folder.
        """
        pass

    @abstractmethod
    def get_mail(self, uid: str) -> Optional[Mail]:
        """
        Fetches and returns a Mail object for the given UID.

        Args:
            uid (str): The UID of the email to fetch.

        Returns:
            Optional[Mail]: A Mail object containing email data if found, or None if not.
        """
        pass

    @abstractmethod
    def close(self):
        """
        Closes the connection to the mailbox.
        """
        pass


class IMAPMailbox(Mailbox):
    """
    Implementation of Mailbox using the IMAP protocol.

    Attributes:
        export_directory (str): Directory where email attachments will be saved.
        server (str): IMAP server address.
        port (int): IMAP server port.
        connection (imaplib.IMAP4_SSL): IMAP connection object.
    """

    def __init__(
        self,
        export_directory: str = "attachments",
        server: str = os.environ.get("IMAP_SERVER", "imap.gmail.com"),
        port: int = os.environ.get("IMAP_PORT", 993),
    ):
        """
        Initializes the IMAPMailbox class.

        Args:
            export_directory (str): Directory where email attachments will be saved.
            server (str): IMAP server address.
            port (int): IMAP server port.
        """
        super().__init__(export_directory)
        self.server = server
        self.port = port
        self.connection = None
        logging.debug(f"Using IMAP server: {self.server} on port {self.port}")

    def connect(self, email_address: str, password: str):
        """
        Connects to the IMAP email server.

        Args:
            email_address (str): Email address used to log into the mailbox.
            password (str): Password for the email account.

        Raises:
            SystemExit: If the authentication fails due to invalid credentials.
        """
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
        """
        Selects a folder in the IMAP mailbox.

        Args:
            folder (str): Name of the folder to select (e.g., "inbox").

        Raises:
            Exception: If the folder cannot be selected.
        """
        logging.info(f"Selecting mailbox folder: {folder}")
        result, _ = self.connection.select(folder)
        if result != "OK":
            logging.error(f"Failed to select folder {folder}.")
            raise Exception(f"Failed to select folder {folder}.")

    def search_emails(self) -> List[str]:
        """
        Searches for all emails in the selected folder.

        Returns:
            List[str]: List of email UIDs found in the folder.

        Raises:
            Exception: If searching for emails fails.
        """
        logging.info("Searching for emails in the folder...")
        result, data = self.connection.uid("search", None, "ALL")
        if result != "OK":
            logging.error("Failed to search for emails.")
            return []
        uids = data[0].split()
        logging.info(f"Found {len(uids)} emails.")
        return [uid.decode() for uid in uids]

    def get_mail(self, uid: str) -> Optional[Mail]:
        """
        Fetches an email by its UID from the IMAP mailbox.

        Args:
            uid (str): The UID of the email to fetch.

        Returns:
            Optional[Mail]: A Mail object containing the email's details if found, None otherwise.
        """
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
        """
        Decodes the header value from its encoded form to a readable string.

        Args:
            value (str): The encoded header value.

        Returns:
            str: The decoded header value.
        """
        decoded_value, encoding = decode_header(value)[0]
        if isinstance(decoded_value, bytes):
            return decoded_value.decode(encoding or "utf-8")
        return decoded_value

    def parse_email_date(self, date_str: str) -> str:
        """
        Parses the email's date string into an ISO 8601 format.

        Args:
            date_str (str): The date string from the email.

        Returns:
            str: The parsed date in ISO 8601 format, or "Unknown" if parsing fails.
        """
        for date_format in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"]:
            try:
                email_datetime = datetime.strptime(date_str, date_format)
                return email_datetime.isoformat()
            except ValueError:
                logging.debug(f"Failed to parse date with format: {date_format}")
        logging.error(f"Failed to parse date: {date_str}")
        return "Unknown"

    def get_email_body(self, msg) -> str:
        """
        Extracts the body content from the email message.

        Args:
            msg: The email message object.

        Returns:
            str: The body content of the email as a string.
        """
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
        """
        Extracts and saves the attachments from the email.

        Args:
            msg: The email message object.
            uid (str): The UID of the email.
            subject (str): The subject of the email.
            sender (str): The sender's email address.
            date (str): The date when the email was sent.

        Returns:
            List[str]: List of file paths where attachments have been saved.
        """
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
        """
        Closes the IMAP mailbox connection.
        """
        logging.info("Closing the mailbox connection.")
        if self.connection:
            self.connection.close()
            self.connection.logout()


class ExchangeMailbox(Mailbox):
    """
    Implementation of Mailbox using Exchange server via Exchange Web Services (EWS) using exchangelib.

    Attributes:
        export_directory (str): Directory where email attachments will be saved.
        server (str): Exchange server address.
        account (Account): Exchangelib Account object representing the email account.
    """

    def __init__(
        self,
        export_directory: str = "attachments",
        server: str = os.environ.get("EXCHANGE_SERVER"),
    ):
        """
        Initializes the ExchangeMailbox class.

        Args:
            export_directory (str): Directory to save email attachments.
            server (str): Exchange server address.
        """
        super().__init__(export_directory)
        self.server = server
        self.account = None
        logging.debug(f"Using Exchange server: {self.server}")

    def connect(self, email_address: str, password: str):
        """
        Connects to the Exchange server using the provided email address and password.

        Args:
            email_address (str): Email address used to log into the Exchange server.
            password (str): Password for the email account.

        Raises:
            SystemExit: If the connection to the Exchange server fails due to invalid credentials or configuration.
        """
        logging.info("Connecting to the Exchange server")
        try:
            cred = Credentials(email_address, password)
            config = Configuration(server=self.server, credentials=cred)
            self.account = Account(
                email_address, config=config, autodiscover=False, credentials=cred
            )
            logging.info(f"Connected successfully to Exchange server {self.server}")
        except Exception as e:
            logging.error(f"Failed to connect to Exchange server: {e}")
            raise SystemExit("Invalid credentials, server configuration or ")

    def select_folder(self, folder: str, public: bool = False):
        """
        Selects a folder in the Exchange mailbox (e.g., 'inbox').

        Args:
            folder (str): The name of the folder to select.
            public (bool): Whether to select a public/shared folder. Defaults to False.

        Raises:
            Exception: If the folder cannot be found or selected.
        """
        if public:
            logging.info("Selecting a public/shared folder!")
        logging.info(f"Selecting the mailbox folder: {folder}")

        root = self.account.public_folders_root if public else self.account.inbox
        try:
            self.folder = root / folder
        except Exception as e:
            logging.error(f"Failed to select folder {folder}")
            logging.error(e)
            raise Exception(f"Folder {folder} not found!")
        logging.info(f"Selected folder {folder}")

    def search_emails(self) -> List[str]:
        """
        Searches for all unread email messages in the selected folder.

        Returns:
            List[str]: A list of email UIDs (message IDs) found in the folder.
        """
        logging.info("Search for all email messages in the selected folder")
        emails = list(self.folder.filter(is_read=False).order_by("-datetime_received"))

        uids = [email.message_id for email in emails]

        logging.info(f"Found {len(uids)} emails.")

        return uids

    def get_mail(self, uid: str) -> Optional[Mail]:
        """
        Fetches a specific email by its UID (message_id).

        Args:
            uid (str): The UID of the email to fetch.

        Returns:
            Optional[Mail]: A Mail object containing the email's details if found, or None if not.
        """
        logging.info(f"Fetching email with UID: {uid}")
        try:
            queryset = list(self.folder.filter(message_id=uid))

            if not queryset or len(queryset) == 0:
                logging.warning(f"No email found with UID: {uid}")
                return None

            email = queryset[0]

            if not email:
                logging.warning(f"No email found with UID: {uid}")
                return None

            subject = email.subject
            sender = str(email.sender.email_address)
            recipient = (
                str(email.to_recipients[0].email_address)
                if email.to_recipients
                else None
            )
            date = email.datetime_received.isoformat()
            body = email.body
            attachments = self.get_attachments(email, subject, sender, date)

            email.is_read = True
            email.save()

            return Mail(
                uid=uid,
                subject=subject,
                sender=sender,
                recipient=recipient,
                date=date,
                body=body,
                attachments=attachments,
            )

        except Exception as e:
            logging.error(f"Error fetching email UID {uid}: {e}")
            return None

    def get_attachments(
        self, email: Message, subject: str, sender: str, date: str
    ) -> List[str]:
        """
        Downloads and saves the attachments from the email.

        Args:
            email (Message): The email object containing attachments.
            subject (str): The subject of the email.
            sender (str): The sender's email address.
            date (str): The date when the email was sent.

        Returns:
            List[str]: A list of file paths where the attachments have been saved.
        """
        attachments = []
        for attachment in email.attachments:
            if isinstance(attachment, FileAttachment):
                filename = sanitize_filename(attachment.name)
                email_prefix = sanitize_filename(f"{subject}_{sender}_{date}")
                output_path = os.path.join(
                    self.attachment_dir, f"{email_prefix}_{filename}"
                )
                with open(output_path, "wb") as f:
                    f.write(attachment.content)
                attachments.append(output_path)
                logging.info(f"Attachment saved to {output_path}")
        return attachments

    def close(self):
        """
        Closes the connection to the Exchange server.
        """
        pass
