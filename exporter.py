import argparse
import os
import logging
import time
import sqlite3
from mail import Mailbox, IMAPMailbox, ExchangeMailbox, Mail
import importlib


def get_attachment_handler_class(handler_str):
    mod = importlib.import_module(".".join(handler_str.split(".")[:-1]))
    cl = getattr(mod, handler_str.split(".")[-1])
    return cl


class Config:
    def __init__(self, config_dict):
        for k, v in config_dict.items():
            if isinstance(v, dict):
                setattr(self, k, Config(v))
            else:
                setattr(self, k, v)


def init_db(db_name: str = "processed_emails.db") -> sqlite3.Connection:
    """
    Initializes the SQLite database for storing processed emails.

    This function creates a new SQLite database or connects to an existing one.
    It also creates a table named 'processed_emails' if it does not already exist.

    Args:
        db_name (str): The name of the SQLite database file. Defaults to "processed_emails.db".

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
    filters: dict = {},
    delete_mails: bool = False,
    public_folder: bool = False,
):
    """
    Downloads attachments from emails in the specified folder.

    This function connects to the specified email folder, iterates through the emails,
    and downloads any attachments found. The attachments are saved to the specified directory,
    and metadata is stored in the SQLite database.

    Args:
        mailbox (Mailbox): A Mailbox object that is connected to the email server.
        conn (sqlite3.Connection): The SQLite database connection object.
        folder (str): The name of the email folder to search for attachments. Defaults to "inbox".
        attachment_dir (str): The directory where the downloaded attachments will be saved. Defaults to "attachments".

    Returns:
        None
    """
    mailbox.select_folder(folder, public_folder)
    uids = mailbox.search_emails(filters)
    mailbox.delete_emails = delete_mails
    skipped_emails = 0

    for uid in uids:
        if Mail.already_processed(uid, conn):
            logging.debug(f"Email with UID {uid} has already been processed. Skipping.")
            skipped_emails += 1
            continue
        try:
            mail = mailbox.get_mail(uid)
            if not mail:
                continue
            mail.to_sqlite_db(conn)
        except Exception as e:
            logging.error(f"Error while getting mail and downloading attachment (UID {uid})")
            raise e
        finally:
            if delete_mails:
                mailbox.trash_mail(uid)

    logging.info(f"Processed {len(uids) - skipped_emails} emails.")
    logging.info(f"Skipped {skipped_emails} emails already processed.")


def main():
    parser = argparse.ArgumentParser(
        description="Download attachments from Mailbox (IMAP or Exchange) and store metadata in SQLite."
    )
    parser.add_argument("--config", help="path to configuration file (YAML format)")
    parser.add_argument(
        "--mailbox-type",
        choices=["IMAP", "Exchange"],
        help="Type of mailbox to connect to (IMAP or Exchange). Default is 'IMAP'.",
    )
    parser.add_argument(
        "--email",
        help="Email address to connect to the mailbox. Can also be provided via the EMAIL_ADDRESS environment variable.",
    )
    parser.add_argument(
        "--password",
        help="Password for the email account. Can also be provided via the EMAIL_PASSWORD environment variable.",
    )
    parser.add_argument(
        "--interval",
        help="Check interval in seconds to look for new emails. Default is 60 seconds.",
    )
    parser.add_argument(
        "--db",
        help="Path to SQLite database for storing processed email UIDs and metadata. Default is '.attachhound/processed_emails.db'.",
    )
    parser.add_argument(
        "--folder",
        help="Name of the folder on the server from which emails will be fetched. Default is 'inbox'.",
    )
    parser.add_argument(
        "--public-folder",
        help="If specified, connects to a public/shared folder (on Exchange server only).",
        action="store_true",
    )
    parser.add_argument(
        "--delete", "-D",
        help="If specified, mails that are saved to disk will be deleted on the server.",
        action="store_true",
    )
    parser.add_argument(
        "--attachment-dir",
        help="Directory where downloaded attachments will be stored. Default is '.attachhound/attachments'.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v,-vv,-vvv)",
    )

    args = parser.parse_args()

    # Setup logging configuration
    logging_levels = [
        logging.WARNING,
        logging.INFO,
        logging.DEBUG,
    ]
    logging_level = logging_levels[min(args.verbose, len(logging_levels) - 1)]
    logging.basicConfig(
        level=logging_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    config_dict = {
        "mailbox": {
            "type": "IMAP",
            "server": "imap.google.com",
            "port": 993,
            "email": None,
            "password": None,
            "folder": "inbox",
            "public": False,
        },
        "interval": 60,
        "module": "mail.SimpleExporter",
        "directory": ".attachhound/attachments",
        "database": ".attachhound/processed_emails.db",
    }

    def deep_update(d1, d2):
        for k, v in d2.items():
            if isinstance(v, dict) and k in d1 and isinstance(d1[k], dict):
                deep_update(d1[k], v)
            else:
                d1[k] = v
        return d1

    if args.config is not None:
        import yaml

        config_updates = yaml.safe_load(open(args.config, "r"))
        config_dict = deep_update(config_dict, config_updates)
    if "mailbox" in config_dict:
        if "filters" not in config_dict["mailbox"]:
            config_dict["mailbox"]["filters"] = {}

    for arg, keys in {
        "mailbox_type": "mailbox:type",
        "email": "mailbox:email",
        "password": "mailbox:password",
        "folder": "mailbox:folder",
        "public_folder": "mailbox:public",
        "delete": "mailbox:delete",
        "interval": "interval",
        "attachment_dir": "directory",
        "db": "database",
    }.items():
        current = config_dict
        value = getattr(args, arg)
        skip = False
        for bool_flag in ["public", "delete"]:
            if bool_flag in arg and bool_flag in config_updates.get("mailbox", {}):
                skip = True
        if value is None or skip:
            continue
        key_list = [keys] if ":" not in keys else keys.split(":")
        for k in key_list[:-1]:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[key_list[-1]] = value
    config = Config(config_dict)

    if not config.mailbox.email or not config.mailbox.password:
        logging.error("Email or password not provided.")
        raise SystemExit(
            "Please provide an email and password either via command line or environment variables."
        )

    logging.info("Starting the email attachment downloader script.")
    logging.info(f"Checking for new emails every {config.interval} seconds.")
    logging.info(f"Using email address: {config.mailbox.email}")
    logging.debug(
        f"Database path: {config.database}, Attachment directory: {config.directory}"
    )
    logging.info("Ensuring necessary directories exist...")

    # Create the directory for attachments if it doesn't exist
    if not os.path.exists(config.directory):
        os.makedirs(config.directory)
        logging.info(f"Created directory for attachments: {config.directory}")
    else:
        logging.debug(f"Attachment directory already exists: {config.directory}")

    # Create the directory for the SQLite database if it doesn't exist
    db_dir = os.path.dirname(config.database)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Created directory for SQLite database: {db_dir}")
    else:
        logging.debug(f"SQLite database directory already exists: {db_dir}")

    # Initialize the SQLite database
    conn = init_db(config.database)
    logging.info(f"SQLite database initialized at {config.database}")

    while True:
        try:
            # Connect to the email server and download attachments
            mailbox_class = {"IMAP": IMAPMailbox, "Exchange": ExchangeMailbox}[
                config.mailbox.type
            ]
            mailbox = mailbox_class(
                server=config.mailbox.server,
                export_directory=config.directory,
                attachment_handler=get_attachment_handler_class(config.module),
            )
            mailbox.connect(config.mailbox.email, config.mailbox.password)
            logging.info("Connected to the email server successfully.")

            download_attachments(
                mailbox,
                conn,
                folder=config.mailbox.folder,
                filters=config.mailbox.filters.__dict__,
                delete_mails=config.mailbox.delete,
                public_folder=config.mailbox.public,
            )
            logging.info("Attachment download and metadata storage completed.")
        except Exception as e:
            logging.error(f"An error occurred during the process: {e}")
        finally:
            mailbox.close()
            logging.info("Disconnected from the email server.")

            logging.info(
                f"Waiting for {config.interval} seconds before the next run..."
            )
            time.sleep(int(config.interval))


if __name__ == "__main__":
    main()
