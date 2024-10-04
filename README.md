# AttachHound
small python app to collect attachments from mails

## Runnig the app
```bash
docker build -t attachhound .
docker run -d --env-file .env attachhound
```

### Environment variables
Content of the .env file
```bash
MAIL_SERVER=imap.gmail.com # (default) or any other mail server
MAIL_PORT=993  # (default) or any other port
EMAIL_ADDRESS=<your e-mail address>
EMAIL_PASSWORD=<your e-mail password>
CHECK_INTERVAL=60   # in seconds
```