# Windows Server 2022 Production Installation Guide

This guide describes how to install, configure, and deploy the **EMR Integration Gateway** (REST API and Kiosk UI) on **Windows Server 2022** as a persistent, auto-restarting background Windows Service.

---

## 1. Prerequisites

### 1.1. Python Installation
1. Download the official **Python 3.10+ (64-bit)** installer for Windows.
2. Run the installer as Administrator.
3. > [!IMPORTANT]
   > Make sure to check **"Add Python to PATH"** and **"Install launcher for all users"** at the bottom of the installer window.
4. Select **Customize installation** and verify `pip` is checked. Finish the installation.

### 1.2. Firebird Client Configuration
The REST API requires the Firebird Client DLL (`fbclient.dll`) to interact with the databases.
- If the database is hosted locally, ensure Firebird is installed and running.
- Copy `fbclient.dll` (matching your architecture) to either:
  - `C:\Windows\System32\` (Global system path) <매우 중요>
  - Or directly in the root of the server directory: `C:\rest-api-server\`

### 1.3. .NET Framework (C# Compiler)
The 32-bit decryption worker (`DecryptWorker.exe`) must be compiled on the server using Microsoft's C# Compiler (`csc.exe`), which is bundled with the .NET Framework:
- Verify that `C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe` exists.
- *(Note: Ensure you are using the `Framework` folder, which is 32-bit, and NOT `Framework64`)*.

---

## 2. Compile Decryption Worker

1. Open PowerShell as Administrator.
2. Navigate to the project directory:
   ```powershell
   cd C:\rest-api-server
   ```
3. Compile the C# file forcing the x86 32-bit platform:
   ```powershell
   C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe /platform:x86 /out:DecryptWorker.exe DecryptWorker.cs
   ```
4. Verify that `DecryptWorker.exe` has been generated in the root directory.

---

## 3. Python Virtual Environment & Dependencies

1. Navigate to the project directory:
   ```powershell
   cd C:\rest-api-server
   ```
2. Create a isolated virtual environment:
   ```powershell
   python -m venv venv
   ```
3. Activate the virtual environment:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```
4. Install the required Python dependencies:
   ```powershell
   pip install fastapi uvicorn fdb pydantic
   ```

---

## 4. Port & Database Configurations

Open [config.py](file:///c:/rest-api-server/config.py) to review or customize the bindings:
- **`PORT`**: Rest API port (Default: `8000`).
- **`FRONTEND_PORT`**: Self check-in kiosk UI port (Default: `3007`).
- **`DB_HOST`**: Set to the Firebird server IP address (e.g. `192.168.0.12`).
- **`DB_DIR`**: Set to the path on the host DB server where database files (`.FDB`) reside.

Alternatively, you can set system environment variables to override default values:
```powershell
[System.Environment]::SetEnvironmentVariable('EMR_GATEWAY_HOST', '0.0.0.0', 'Machine')
[System.Environment]::SetEnvironmentVariable('EMR_GATEWAY_PORT', '8000', 'Machine')
[System.Environment]::SetEnvironmentVariable('EMR_FRONTEND_PORT', '3007', 'Machine')
```

---

## 5. Installing as a Windows Service (NSSM)

To ensure the server runs persistently in the background without requiring a user session to remain logged in, we configure it as a Windows Service using **NSSM (Non-Sucking Service Manager)**.

### 5.1. Download NSSM
1. Download NSSM from [https://nssm.cc/download](https://nssm.cc/download) (Version 2.24 or later recommended).
2. Extract the ZIP package and copy `nssm.exe` from the `win64` folder into `C:\rest-api-server\`.

### 5.2. Create log directory
Create a directory to store the service console logs:
```powershell
mkdir C:\rest-api-server\logs
```

### 5.3. Register the Service
Run the NSSM GUI installer from PowerShell as Administrator:
```powershell
C:\rest-api-server\nssm.exe install EMRGateway
```

In the NSSM GUI window, configure the following:

- **Application Tab**:
  - **Path**: `C:\rest-api-server\venv\Scripts\python.exe` (Select the python executable inside the virtual environment)
  - **Startup directory**: `C:\rest-api-server`
  - **Arguments**: `main.py`

- **Details Tab**:
  - **Display name**: `EMR Gateway Service`
  - **Description**: `REST API and Kiosk UI mediator gateway for local Firebird EMR databases.`
  - **Startup type**: `Automatic`

- **I/O Tab (Logging)**:
  - **Input (stdin)**: *(Leave blank)*
  - **Output (stdout)**: `C:\rest-api-server\logs\service.log`
  - **Error (stderr)**: `C:\rest-api-server\logs\service.log`

- **File Rotation Tab**:
  - Check **"Rotate files"**
  - Set **Restrict rotation to files larger than** `10485760` bytes (10 MB) to prevent log files from growing indefinitely.

Click **Install service**.

### 5.4. Start the Service
Start the newly created service from PowerShell:
```powershell
C:\rest-api-server\nssm.exe start EMRGateway
```

Verify the status is running:
```powershell
Get-Service EMRGateway
```

---

## 6. Windows Firewall Configuration

By default, Windows Server block incoming network requests. To allow other client computers, kiosk terminals, or tablets in the local clinic network to access the services, you must open ports `8000` and `3007`.

Run the following commands in PowerShell as Administrator:

```powershell
# Open inbound port 8000 for REST API
New-NetFirewallRule -DisplayName "EMR Gateway REST API (Port 8000)" `
    -Direction Inbound `
    -LocalPort 8000 `
    -Protocol TCP `
    -Action Allow

# Open inbound port 3007 for Kiosk Check-In UI
New-NetFirewallRule -DisplayName "EMR Gateway Kiosk UI (Port 3007)" `
    -Direction Inbound `
    -LocalPort 3007 `
    -Protocol TCP `
    -Action Allow
```

---

## 7. Service Management and Maintenance

- **Restart Service**:
  ```powershell
  Restart-Service EMRGateway
  ```
- **Stop Service**:
  ```powershell
  Stop-Service EMRGateway
  ```
- **Edit Service Configuration**:
  ```powershell
  C:\rest-api-server\nssm.exe edit EMRGateway
  ```
- **View Active Logs**:
  ```powershell
  Get-Content C:\rest-api-server\logs\service.log -Wait -Tail 50
  ```
