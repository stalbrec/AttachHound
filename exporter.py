import imaplib
import email
from email.header import decode_header
import argparse
import os
import logging
import json
from datetime import datetime
import re
import time
import sqlite3
from typing import List

# Get IMAP server and port from environment variables or use defaults
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = os.environ.get("IMAP_PORT", 993)


def init_db(db_name: str = "processed_emails.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_emails (
            uid TEXT PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            recipient TEXT,
            date TEXT,
            body TEXT,
            attachments TEXT
        )
    """)
    conn.commit()
    return conn


def email_already_processed(cursor: sqlite3.Cursor, email_uid: str):
    cursor.execute("SELECT 1 FROM processed_emails WHERE uid = ?", (email_uid,))
    return cursor.fetchone() is not None


def save_email_metadata(
    conn: sqlite3.Connection,
    email_uid: str,
    subject: str,
    sender: str,
    recipient: str,
    date: str,
    body: str,
    attachments: List[str],
):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO processed_emails (uid, subject, sender, recipient, date, body, attachments)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (email_uid, subject, sender, recipient, date, body, json.dumps(attachments)),
    )
    conn.commit()


def connect_to_email(email_address: str, password: str):
    logging.info("Connecting to the email server...")
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(email_address, password)
        logging.info(f"Connected successfully to {IMAP_SERVER}")
        return mail
    except imaplib.IMAP4.error as e:
        logging.error(f"Authentication failed: {e}")
        raise SystemExit(
            "Invalid credentials. Please check your email and password or consider using an app-specific password if you have 2FA enabled."
        )


def sanitize_filename(filename: str):
    """
    Sanitize the filename to make it safe for filesystem use.
    Replace special characters with underscores.
    """
    return re.sub(r"[^\w\-_\. ]", "_", filename)


def download_attachments(
    mail: imaplib.IMAP4_SSL,
    conn: sqlite3.Connection,
    folder: str = "inbox",
    attachment_dir: str = "attachments",
):
    """
    Download attachments from emails in the specified folder.
    Save the attachments to the specified directory.
    """

    logging.info(f"Selecting mailbox folder: {folder}")
    result, _ = mail.select(folder)
    skipped_emails = 0

    if result != "OK":
        logging.error("Failed to select mailbox.")
        return

    logging.info("Searching for emails in the selected folder...")
    result, data = mail.uid("search", None, "ALL")

    if result != "OK":
        logging.error("Failed to search for emails.")
        return

    uids = data[0].split()
    logging.info(f"Found {len(uids)} emails in the folder.")

    cursor = conn.cursor()

    for uid in uids:
        uid = uid.decode()
        if email_already_processed(cursor, uid):
            logging.debug(f"Email with UID {uid} has already been processed. Skipping.")
            skipped_emails += 1
            continue

        logging.info(f"Processing email with UID: {uid}")
        result, data = mail.uid("fetch", uid, "(RFC822)")

        if result != "OK":
            logging.error(f"Failed to fetch email with UID: {uid}")
            continue

        for response_part in data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                # Decode email headers
                email_subject = decode_header(msg["subject"])[0][0]
                if isinstance(email_subject, bytes):
                    email_subject = email_subject.decode()
                email_from = msg.get("From")
                email_to = msg.get("To")

                email_date = msg.get("Date")

                for date_format in [
                    "%a, %d %b %Y %H:%M:%S %z",
                    "%a, %d %b %Y %H:%M:%S %Z",
                ]:
                    try:
                        email_datetime = datetime.strptime(email_date, date_format)
                        break  # If parsing is successful, exit the loop
                    except ValueError:
                        logging.debug(
                            f"Failed to parse date with format: {date_format}"
                        )
                        continue  # If parsing fails, try the next format
                else:
                    # Raise an error only if no formats match
                    raise RuntimeError(f"Failed to parse date: {email_date}")

                # Convert to ISO 8601 format
                email_isodate = email_datetime.isoformat()

                email_body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if (
                            content_type == "text/plain"
                            and part.get("Content-Disposition") is None
                        ):
                            email_body = part.get_payload(
                                decode=True
                            ).decode()  # Extract email body (plain text)
                            break
                else:
                    email_body = msg.get_payload(decode=True).decode()

                # List to store attachment file paths
                attachments_list = []

                # Iterate over parts of the email for attachments
                for part in msg.walk():
                    if part.get_content_maintype() == "multipart":
                        continue
                    if part.get("Content-Disposition") is None:
                        continue

                    # Process attachment
                    filename = part.get_filename()
                    if filename is not None:
                        filename = decode_header(filename)[0][0]
                        if isinstance(filename, bytes):
                            filename = filename.decode()

                        sanitized_filename = sanitize_filename(filename)
                        logging.info(f"Found attachment: {sanitized_filename}")
                        # Create a directory for this email
                        email_prefix = sanitize_filename(
                            f"{email_subject}_{email_from}_{email_isodate}"
                        )
                        email_prefix_path = os.path.join(attachment_dir, email_prefix)

                        output_path = f"{email_prefix_path}_{sanitized_filename}"

                        output_path = output_path.replace(" ", "_")

                        with open(output_path, "wb") as file:
                            file.write(part.get_payload(decode=True))

                        logging.info(f"Attachment saved to {output_path}")
                        attachments_list.append(output_path)

                # Save email metadata and attachments to SQLite
                save_email_metadata(
                    conn,
                    uid,
                    email_subject,
                    email_from,
                    email_to,
                    email_isodate,
                    email_body,
                    attachments_list,
                )
                logging.info(f"Email with UID {uid} metadata saved to database.")
    logging.info(f"Processed {len(uids) - skipped_emails} emails.")
    logging.info(f"Skipped {skipped_emails} emails.")

def main():
    parser = argparse.ArgumentParser(
        description="Download attachments from Mailbox (IMAP) and store metadata in SQLite"
    )
    parser.add_argument(
        "--email",
        help="Email address",
        required=False,
        default=os.environ.get("EMAIL_ADDRESS"),
    )
    parser.add_argument(
        "--password",
        help="Email password",
        required=False,
        default=os.environ.get("EMAIL_PASSWORD"),
    )
    parser.add_argument(
        "--interval",
        help="Check interval in seconds",
        required=False,
        default=os.environ.get("CHECK_INTERVAL", 60),
    )
    parser.add_argument(
        "--db",
        help="Path to SQLite database for storing processed email UIDs and metadata",
        required=False,
        default="/data/processed_emails.db",
    )
    parser.add_argument(
        "--inbox",
        help="Name of folder on imap server, where mails are to be fetched from",
        default="inbox",
    )
    parser.add_argument(
        "--attachment-dir",
        help="Path to directory for storing the downloaded attachments",
        default="/data/attachments",
    )

    args = parser.parse_args()

    if not args.email or not args.password:
        logging.error("Email or password not provided.")
        raise SystemExit(
            "Please provide an email and password either via command line or environment variables."
        )

    # Setup logging configuration
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    logging.info("Starting the email attachment downloader script.")
    logging.info(f"Using IMAP server: {IMAP_SERVER}")
    logging.info(f"Using IMAP port: {IMAP_PORT}")
    logging.info(f"Checking for new emails every {args.interval} seconds.")
    logging.info(f"Provided email address: {args.email}")
    logging.info(f"Using SQLite database for metadata: {args.db}")
    logging.info(f"Storing attachments at {args.attachment_dir}")

    logging.info("Making sure all necessary directories exist...")

    # Create the directory for attachments
    if not os.path.exists(args.attachment_dir):
        os.makedirs(args.attachment_dir)
        logging.info(f"Created directory: {args.attachment_dir}")
    # Create the directory for the SQLite database
    if not os.path.exists(os.path.dirname(args.db)):
        os.makedirs(os.path.dirname(args.db))
        logging.info(f"Created directory: {os.path.dirname(args.db)}")

    # Initialize the SQLite database
    conn = init_db(args.db)

    while True:
        try:
            # Connect to the email server and download attachments
            mail = connect_to_email(args.email, args.password)
            download_attachments(
                mail, conn, folder=args.inbox, attachment_dir=args.attachment_dir
            )
            logging.info("Script finished successfully.")
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        finally:
            # Close the mailbox
            mail.close()
            # Logout from the server
            mail.logout()
            logging.info("Disconnected from the email server.")
            logging.info(f"Waiting for {args.interval} before the next run...")
            time.sleep(int(args.interval))


if __name__ == "__main__":
    main()
