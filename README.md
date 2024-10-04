# AttachHound
small python app to collect attachments from mails

## Runnig the app
Use prebuilt image from github container registry:
```bash
docker run -d --env-file .env ghcr.io/stalbrec/attachhound:<tag>
```
So far the only available tags are:
| **tag** | **description** |
|---|---|
| `main-amd64` | main branch for amd64 architecture |
| `main-arm64` | main branch for arm64 architecture |

or build the image yourself
```bash
git clone https://github.com/stalbrec/attachhound.git && cd attachhound
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