# Security Transparency Report
**Product:** TwinScope v1.1  
**Date:** January 7, 2026

## Executive Summary

At TwinScope, we prioritize the security and integrity of your data. This report outlines the security architecture of TwinScope v1.1, the measures we have implemented to ensure safe operation, and guidance on how to verify the authenticity of our software.

## Key Security Features

### 1. Standardized Installation Process
We have transitioned to a standard **Windows MSI Installer** ecosystem. Unlike previous iterations that utilized custom scripts, TwinScope v1.1 uses industry-standard Microsoft Installer technology.
- **Benefit:** This ensures a clean install/uninstall process that adheres to Windows strict directory standards.
- **Safety:** No temporary scripts or "dropper" mechanisms are used. The installer places files directly into `Program Files` and creates shortcuts using standard Windows APIs.

### 2. Local-Only Processing (Privacy by Design)
TwinScope is designed as a strictly local desktop application.
- **No Cloud Uploads:** Your files are compared and processed entirely within your machine's memory and hard drive.
- **No Telemetry:** We do not collect usage data, file metadata, or personal information.
- **Network Isolation:** The application does not require an internet connection to function, minimizing the attack surface.

### 3. Dependency Security
We strictly manage third-party libraries to prevent supply-chain vulnerabilities.
- **Pinned Dependencies:** All external libraries (e.g., for handling PDF or Excel files) are locked to specific, secure versions.
- **XXE Protection:** We utilize `defusedxml` and hardened configurations to protect against XML External Entity attacks when processing Office documents.

## Authentication & Digital Signatures

### Understanding "Unknown Publisher" Warnings
When installing TwinScope, you may see a Windows SmartScreen warning stating "Unknown Publisher."

**Why this happens:**
TwinScope v1.1 is currently signed with a **Self-Signed Code Signing Certificate**. While this cryptographically seals the application to ensure it hasn't been tampered with since we built it, it does not yet have the global reputation of a certificate issued by a large commercial Certificate Authority (CA).

**Our Commitment:**
We verify every build. The self-signed certificate guarantees that the code you run is exactly the code we compiled.

### How to Verify Authenticity
To ensure you are installing the genuine TwinScope application, please follow the verification steps outlined in our **README**:

1.  **Check the Digital Signature:** Right-click the installer > Properties > Digital Signatures.
2.  **Verify the Signer:** Ensure the signature matches the "TwinScope Team" or the specific release signature provided in our official release notes.
3.  **Trust the Certificate:** You can explicitly trust our signing certificate to bypass future warnings and ensure the operating system validates the software integrity.

## Vulnerability Management

We actively monitor for potential security risks.
- **Path Traversal:** The folder scanning engine includes protection against symbolic link cycles and directory traversal attacks.
- **Input Sanitization:** File parsers are configured to handle malformed data safely without crashing or exposing system memory.

## Contact

If you have questions about this report or believe you have found a security vulnerability, please contact the development team immediately.