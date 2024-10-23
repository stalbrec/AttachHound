import argparse
import os
import logging
import time
import sqlite3
from mail import Mailbox, IMAPMailbox, Mail


def init_db(db_name: str = "processed_emails.db") -> sqlite3.Connection:
    """
    Initialize the SQLite database for storing processed emails.

    This function creates a new SQLite database or connects to an existing one.
    It also creates a table named 'processed_emails' if it does not already exist.

    Args:
        db_name (str): The name of the database file. Defaults to "processed_emails.db".

    Returns:
        sqlite3.Connection: A connection object to the SQLite database.
    """
    logging.debug(f"Initializing the database: {db_name}")
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
    logging.info(f"Database {db_name} initialized successfully.")
    return conn


def download_attachments(
    mailbox: Mailbox,
    conn: sqlite3.Connection,
    folder: str = "inbox",
    attachment_dir: str = "attachments",
):
    """
    Download attachments from emails in the specified folder.

    This function connects to the specified email folder, iterates through the emails,
    and downloads any attachments found. The attachments are saved to the specified directory.

    Args:
        mail (Mailbox): a Mailbox object with valid connection.
        conn (sqlite3.Connection): The SQLite database connection object.
        folder (str): The email folder to search for attachments. Defaults to "inbox".
        attachment_dir (str): The directory to save the attachments. Defaults to "attachments".

    Returns:
        None
    """
    mailbox.select_folder(folder)
    uids = mailbox.search_emails()
    skipped_emails = 0

    for uid in uids:
        if Mail.already_processed(uid, conn):
            logging.debug(f"Email with UID {uid} has already been processed. Skipping.")
            skipped_emails += 1
            continue
        mail = mailbox.get_mail(uid)
        if not mail:
            continue
        mail.to_sqlite_db(conn)

    logging.info(f"Processed {len(uids) - skipped_emails} emails.")
    logging.info(f"Skipped {skipped_emails} emails already processed.")


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
        default=".attachhound/processed_emails.db",
    )
    parser.add_argument(
        "--inbox",
        help="Name of folder on IMAP server, where mails are to be fetched from",
        default="inbox",
    )
    parser.add_argument(
        "--attachment-dir",
        help="Path to directory for storing the downloaded attachments",
        default=".attachhound/attachments",
    )

    args = parser.parse_args()

    if not args.email or not args.password:
        logging.error("Email or password not provided.")
        raise SystemExit(
            "Please provide an email and password either via command line or environment variables."
        )

    # Setup logging configuration
    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    logging.info("Starting the email attachment downloader script.")
    logging.info(f"Checking for new emails every {args.interval} seconds.")
    logging.info(f"Using email address: {args.email}")
    logging.debug(
        f"Database path: {args.db}, Attachment directory: {args.attachment_dir}"
    )

    logging.info("Ensuring necessary directories exist...")

    # Create the directory for attachments if it doesn't exist
    if not os.path.exists(args.attachment_dir):
        os.makedirs(args.attachment_dir)
        logging.info(f"Created directory for attachments: {args.attachment_dir}")
    else:
        logging.debug(f"Attachment directory already exists: {args.attachment_dir}")

    # Create the directory for the SQLite database if it doesn't exist
    db_dir = os.path.dirname(args.db)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Created directory for SQLite database: {db_dir}")
    else:
        logging.debug(f"SQLite database directory already exists: {db_dir}")

    # Initialize the SQLite database
    conn = init_db(args.db)
    logging.info(f"SQLite database initialized at {args.db}")

    while True:
        try:
            # Connect to the email server and download attachments
            mailbox = IMAPMailbox(export_directory=args.attachment_dir)
            mailbox.connect(args.email, args.password)
            logging.info("Connected to the email server successfully.")

            download_attachments(
                mailbox, conn, folder=args.inbox, attachment_dir=args.attachment_dir
            )
            logging.info("Attachment download and metadata storage completed.")
        except Exception as e:
            logging.error(f"An error occurred during the process: {e}")
        finally:
            mailbox.close()
            logging.info("Disconnected from the email server.")

            logging.info(f"Waiting for {args.interval} seconds before the next run...")
            time.sleep(int(args.interval))


if __name__ == "__main__":
    main()
