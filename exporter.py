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

# Get IMAP server and port from environment variables or use defaults
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
IMAP_PORT = os.environ.get("IMAP_PORT", 993)


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
    mail, folder: str = "inbox", attachment_dir: str = "attachments"
):
    """
    Download attachments from emails in the specified folder.
    Save the attachments to the specified directory.
    """

    # Create a directory for attachments
    if not os.path.exists(attachment_dir):
        os.makedirs(attachment_dir)
        logging.info(f"Created directory: {attachment_dir}")

    logging.info(f"Selecting mailbox folder: {folder}")
    result, _ = mail.select(folder)

    if result != "OK":
        logging.error("Failed to select mailbox.")
        return

    logging.info("Searching for emails in the selected folder...")
    result, data = mail.search(None, "ALL")

    if result != "OK":
        logging.error("Failed to search for emails.")
        return

    ids = data[0].split()
    logging.info(f"Found {len(ids)} emails in the folder.")
    metadata_list = []

    for i in ids:
        logging.info(f"Processing email with ID: {i.decode()}")
        result, data = mail.fetch(i, "(RFC822)")

        if result != "OK":
            logging.error(f"Failed to fetch email with ID: {i.decode()}")
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
                        logging.debug(f"Failed to parse date with format: {date_format}")
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

                email_metadata = {
                    "subject": email_subject,
                    "from": email_from,
                    "to": email_to,
                    "date": email_isodate,
                    "body": email_body,
                    "attachments": [],
                }
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
                        email_metadata["attachments"].append(output_path)

                if len(email_metadata["attachments"]) > 0:
                    # Add the email metadata to the list
                    metadata_list.append(email_metadata)
                    logging.info("Email metadata added to the list.")

    # Save all metadata at once to a single JSON file
    metadata_file = "email_metadata_all.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata_list, f, indent=4)
    logging.info(f"All email metadata saved to {metadata_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Download attachments from Gmail and store metadata in JSON"
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
        "--interval", help="Check interval in seconds", required=False, default=os.environ.get("CHECK_INTERVAL", 60)
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

    while True:
        try:
            # Connect to the email server and download attachments
            mail = connect_to_email(args.email, args.password)
            download_attachments(mail)
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
