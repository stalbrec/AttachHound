# AttachHound

**AttachHound** is a lightweight, easy-to-use Python application designed to streamline the collection of email attachments. It connects to your mailbox using either **IMAP** or **EWS**, retrieves emails, downloads their attachments, and stores the email metadata (like subject, sender, date, and attachment details) in an SQLite database. AttachHound is perfect for automating tasks that require tracking and managing email attachments.

---

### 🚀 **Key Features**:
- 📥 **Automated Attachment Collection**: Connects to your mailbox (IMAP or Exchange) and fetches attachments on a recurring schedule.
- 💾 **Metadata Storage**: Saves email metadata to an SQLite database for easy reference and auditing.
- ⚙️ **Customizable**: Easily configurable with environment variables or command-line arguments.
- 📨 **Supports IMAP and Exchange**: Works with both IMAP and Exchange (via EWS), allowing for flexible email server integration.
- 📂 **Folder Support**: Allows fetching emails from specific folders and supports public/shared folders in Exchange.

---

## 📦 **Running the App**

### **Option 1: Use Prebuilt Docker Image**
You can run AttachHound using a prebuilt Docker image from the GitHub Container Registry:

```bash
docker run -d --env-file .env -v <local_path>:/app/data ghcr.io/stalbrec/attachhound:<tag>
```

**Note**: The attachments and database will be saved to `/app/data` inside the container. To persist data across container runs, you should mount a local path to `/app/data` using the `-v` option as shown above.

Available tags:
| **Tag**       | **Description**                 |
|---------------|---------------------------------|
| `main-amd64`  | Main branch for amd64 architecture |
| `main-arm64`  | Main branch for arm64 architecture |

### **Option 2: Build the Image Yourself**
Alternatively, you can build the Docker image from source:

```bash
git clone https://github.com/stalbrec/attachhound.git && cd attachhound
docker build -t attachhound .
docker run -d --env-file .env -v <local_path>:/app/data attachhound
```

### **Option 3: manual install**
Last but not least, you can install the requirements with your favorite install of python3 (tested with python 3.11):

```
pip install -r requirements.txt
```

```
python exporter.py --config <your-config>.yml
```

---

## ⚙️ **Configuration**

### Environment Variables

For basic configuration of AttachHound, create a `.env` file with the following content:

```bash
MAIL_SERVER=imap.gmail.com       # (default) or any other mail server
MAIL_PORT=993                    # (default) or any other port
EMAIL_ADDRESS=<your e-mail address>
EMAIL_PASSWORD=<your e-mail password>
CHECK_INTERVAL=60                # in seconds
```

### Configuration YAML (recommended)
For a more detailed configuration more settings are available to the user via the config YAML.
To run with just extend the docker command, e.g.:
```
docker run -d -v .attachhound:/app/data ghcr.io/stalbrec/attachhound:main-amd64 python exporter.py --config /app/data/myconfig.yml
```

With `.attachhound/myconfig.yml` looking something like this:

```yaml
mailbox:
  server: imap.gmail.com
  email: foo@gmail.com
  password: "<gmail app password>"
interval: 5
directory: /app/data/out
database: /app/data/processed.db
```

All available settings are:

```yaml 
mailbox:
    type: <"Exchange" | "IMAP">
    server: <your mail server>
    email: <your email address>
    password: <your email password>
    folder: <some mailbox dir>
    delete: <false | true> # Here you can decide whether the processed mails should be removed from the server
    filters: 
        is_read: <true | true>
        max_age_days: <int>
        before: <date str (%d.%m.%Y assumed!)>
    public: <false | true> # public folder (only for EWS)
module: <exporter module> # modify how your mails should be handled once downloaded (default is 'simple-exporter')
directory: <some output directory>
database: <path-to-sql-db>
interval: 60
```
---

With this setup, AttachHound will periodically check your email, download attachments, and store all relevant metadata for future use.

---
