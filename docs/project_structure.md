# Project Structure & Developer Integration Guide

This document describes the codebase directory structure, component details, build instructions, and runtime environment setup for the **EMR Integration Gateway** (RESTful API Server).

---

## 1. Directory Tree

The workspace is organized as follows:

```text
c:\rest-api-server\
├── DecryptWorker.cs      # C# source code for the 32-bit decryption worker
├── DecryptWorker.exe     # Compiled 32-bit decryption worker executable
├── config.py             # Centralized settings, credentials, and check-in defaults
├── decryptor.py          # Python IPC thread-safe wrapper for DecryptWorker.exe
├── main.py               # Main FastAPI server with routes and DB logging wrappers
├── docs/                 # Documentation directory
│   ├── database_structure.md   # Auto-generated database tables, types, and schema details
│   ├── project_structure.md    # This directory and build/execution guide
│   └── windows_server_2022_install.md # Production installation guide for Windows Server 2022
└── static/               # Static frontend assets
    └── index.html        # Glassmorphic single-page web UI dashboard
```

---

## 2. Core Components Walkthrough

### 2.1. config.py (Centralized Configuration)
A single configuration file loaded with fallback defaults and environment overrides:
1. **Server Bindings**: Configures application binding IP and Port.
2. **Database Settings**: Configures the Firebird root directory path, database user, and database password.
3. **Clinic Defaults**: Configures fallback codes and names for doctors, rooms, and departments during checks.

### 2.2. main.py (FastAPI Gateway)
The main entry point of the server. It:
1. **Configures the `fdb` Driver**: Configures the Firebird client driver's character set mapping dictionary at startup so that both character set `KSC_5601` (EUC-KR) and raw binary `NONE` columns decode correctly to `'cp949'` (Korean).
2. **Registers DB Logging Wrappers**: Includes `LoggingConnection` and `LoggingCursor` proxy classes. These wrap default database objects to capture, time, and print all database queries and transaction states to the terminal in real-time.
3. **Exposes Integration Endpoints**:
   - `GET /`: Serves the single-page visual dashboard (`static/index.html`).
   - `GET /api/schema`: Dynamically queries the Firebird system tables (`RDB$RELATION_FIELDS`, `RDB$FIELDS`, etc.) across all four databases and returns the exact schema of every user table in JSON.
   - `GET /api/patients`: Lists patients from `MTSDB.PERSON`. Calls the `decryptor` module on-the-fly to decrypt patient resident registration numbers (`PIDNUM`).
   - `GET /api/patients/{pcode}`: Returns patient demographic details and vital check history (`MTSDB.CHECK_VITAL`).
   - `GET /api/waiting`: Queries the database for the active annual waitlist table. By default, it queries the ledger database `MTSMTR` (e.g. `MTR2026`) and generates session-like `resid1` IDs for items. It also supports `MTSWAIT` (live queue) via query params.
   - `POST /api/waiting`: Checks in a patient by creating a ledger entry in `MTSMTR` (with an empty `FIN` column indicating active status).
   - `PUT /api/waiting/{resid1}`: Refactored to update the doctor assignment (`DOC` column) in `MTSMTR` by decoding the session-like `resid1` key.
   - `DELETE /api/waiting/{resid1}`: Operates entirely on `MTSMTR` (bypassing `MTSWAIT`). It decodes `resid1` to retrieve the `pcode` and `visidate` and cancels (deletes) the ledger entry if the treatment is not yet completed (`FIN` is empty).
   - `GET /api/charts/{pcode}`: Loops through all annual clinical chart tables (e.g. `CHT2023`, `CHT2024`, `CHT2025`) in the `MTSCHT` database to reconstruct a patient's historical medical records.
   - `GET /api/visits/{pcode}`: Gathers billing ledger entries, weight, temperature, vaccinations, and treatment notes from the annual ledger tables (e.g. `MTR2025`) in `MTSMTR`.
4. **Launches Uvicorn**: Includes a `__main__` entry to start the application using `uvicorn.run(...)` on `http://127.0.0.1:8000`.

### 2.3. decryptor.py (IPC Decryptor Wrapper)
Acts as a mediator between Python's 64-bit environment and the 32-bit decryption worker.
- Spawns `DecryptWorker.exe` as a persistent subprocess using `subprocess.Popen`.
- Enforces thread safety by using a Python `threading.Lock` mutex, ensuring parallel API requests do not corrupt the standard input/output stream pipeline.
- Handles robust stream parsing: filters out any debug logs (e.g. `DSTK_CRYPT_Decrypt Success`) written directly to standard output by the underlying native C++ DLL (`IndvInfmCrypto.dll`), and only parses protocol control packets starting with `OK:` or `ERROR:`.
- Implements process health monitoring: checks the subprocess state before writing, and automatically revives the worker if it crashes.

### 2.4. DecryptWorker.cs (C# x86 Worker Source)
A C# console application compiled specifically for the 32-bit architecture (`x86`).
- Directs its working directory to `C:\mts3` upon startup to load native assemblies and configuration files from the EMR directory.
- Uses `DllImport` with `StdCall` calling convention to interface with the 32-bit native library `C:\mts3\IndvInfmCrypto.dll`.
- Loads the crypt handle and sets the encryption key password to `icando00~`.
- Enters a high-speed execution loop reading base64-encoded ciphertexts from `stdin`, executing `decodeBase64` and `decryptDataWithKey`, and writing the decrypted resident registration number (RRN) back to `stdout` in the format `OK:<RRN_VALUE>`.

### 2.5. static/index.html (Visual EMR Dashboard)
A single-page application using modern dark-mode aesthetics:
- **Responsive Layout**: Designed with HTML5 and CSS Grid/Flexbox.
- **Glassmorphism Styling**: Uses semi-transparent dark panels, vibrant turquoise accents, and sleek borders.
- **Interactive Schema Explorer**: Displays the hierarchical schema metadata (databases, tables, columns, types) returned by `/api/schema` in an expandable tree.
- **Real-time Integration Panels**: Displays the active waiting queue list, searchable patient ledger, clinical history timelines, vitals tracking, and decrypted RRN fields (featuring secure mask/reveal locks).

---

## 3. Worker Compilation Guide

### 3.1. Why compilation is required
The EMR decryption DLL `IndvInfmCrypto.dll` is compiled as a **32-bit (x86)** binary. In Windows, a **64-bit** process (like standard 64-bit Python) cannot load a 32-bit DLL directly (it triggers a `BadImageFormatException` or DLL load failure). 

To solve this without modifying Python's environment, we compile `DecryptWorker.cs` as a **32-bit** application. This 32-bit executable can successfully load the 32-bit DLL and communicate back to the 64-bit Python script via standard input/output streams (IPC).

### 3.2. How to compile
You can compile the worker using the built-in Microsoft C# Compiler (`csc.exe`) included with the .NET Framework on Windows.

1. **Locate the compiler**: The compiler is typically found in the Windows .NET Framework folder, for example:
   ```text
   C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe
   ```
   *(Note: Make sure to use the **Framework** folder, which is 32-bit, rather than Framework64)*.

2. **Execute compile command**: Run the following command in PowerShell or Command Prompt from the `c:\rest-api-server` directory:
   ```powershell
   C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe /platform:x86 /out:DecryptWorker.exe DecryptWorker.cs
   ```
   *The `/platform:x86` flag is critical as it forces the executable to run as a 32-bit process.*

---

## 4. REST API Execution and Deployment Guide

> [!TIP]
> For production deployment on Windows Server 2022 as a persistent background service (using NSSM), see the dedicated [Windows Server 2022 Production Installation Guide](file:///c:/rest-api-server/docs/windows_server_2022_install.md).

### 4.1. Prerequisites
- **Python**: Python 3.8 or higher.
- **Firebird SQL Server**: Firebird server must be running and network-accessible.
- **Firebird Client Library**: The native client library (`fbclient.dll` on Windows / `libfbclient.so` on Linux) must be present on the REST API server machine for connection establishment.
- **EMR Installation**: The clinic program must be located at the configured path containing `IndvInfmCrypto.dll` and the database files inside the designated Firebird directory.

### 4.2. Setup Python Environment
Create a virtual environment and install the required dependencies:

```powershell
# 1. Navigate to the project directory
cd c:\rest-api-server

# 2. Create virtual environment
python -m venv venv

# 3. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install fastapi uvicorn fdb pydantic
```

### 4.3. Starting the Server
Run the FastAPI application:

```powershell
python main.py
```

Upon startup:
- The server will establish IPC communication with `DecryptWorker.exe`.
- The logging framework will print initialization logs and confirm that the decryption worker is active.
- Access the web dashboard by opening `http://127.0.0.1:8000/` in your browser.
- Interactive API documentation will be available at `http://127.0.0.1:8000/docs` (Swagger UI).

### 4.4. Inspecting Transaction Logs
All queries and API requests are logged directly to standard output. Example log trail:

```text
2026-05-22 13:54:18,098 [INFO] emr_api: [DB TRANSACTION] [MTSWAIT] Connection opened & transaction started
2026-05-22 13:54:18,098 [INFO] emr_api: [DB QUERY] [MTSWAIT] SQL: SELECT RDB$RELATION_NAME FROM RDB$RELATIONS WHERE RDB$SYSTEM_FLAG = 0
2026-05-22 13:54:18,100 [INFO] emr_api: [DB TRANSACTION] [MTSWAIT] Closing connection...
2026-05-22 13:54:18,101 [INFO] emr_api: [DB TRANSACTION SUCCESS] [MTSWAIT] Connection closed (took 0.73ms)
2026-05-22 13:54:18,129 [WARNING] decryptor: DecryptWorker native print: DSTK_CRYPT_Decrypt Success
INFO:     127.0.0.1:58103 - "GET /api/waiting HTTP/1.1" 200 OK
```

---

## 5. Database Connections & Configurations

### 5.1. Database Targets
The server connects to the configured Firebird databases:

| Database Name | File Path | Scope |
| :--- | :--- | :--- |
| `MTSDB` | `[DB_DIR]/MTSDB.FDB` | Central register (Patients, Vitals registry) |
| `MTSCHT` | `[DB_DIR]/MTSCHT.FDB` | Annual charts (Symptoms, Diagnoses, Doctors) |
| `MTSWAIT` | `[DB_DIR]/MTSWAIT.FDB` | Clinic waitlists (Active queues, if used) |
| `MTSMTR` | `[DB_DIR]/MTSMTR.FDB` | Annual visit ledgers (Fees, Vitals, Vaccinations) |

### 5.2. Connection Settings & Remote Support
The connection settings are defined in [config.py](file:///c:/rest-api-server/config.py):
- **DB_HOST**: IP address of the database server (supports remote configurations like `192.168.0.12`). Defaults to `127.0.0.1`.
- **DB_DIR**: Folder directory holding the `.FDB` files on the database server.
- **DB_PORT**: Firebird port (default `3050`).
- **DB_USER** / **DB_PASSWORD**: Firebird DBA credentials (default `SYSDBA` / `masterkey`).

The REST API server bypasses local database file existence checks when `DB_HOST` is remote, allowing seamless network communication.
