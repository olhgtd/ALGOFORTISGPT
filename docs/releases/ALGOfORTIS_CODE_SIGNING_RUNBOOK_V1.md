# AlgoFortis V1 — Windows Code-Signing Runbook

**PRODUCT:** AlgoFortis  
**RELEASE TARGET:** External Beta / Production V1  
**DOCUMENT VERSION:** 1.0.0  
**LAST UPDATED:** 2026-09-15  
**STATUS:** OWNER ACTION REQUIRED — PENDING CERTIFICATE ACQUISITION  

---

> [!IMPORTANT]
> **OWNER ACTION REQUIRED:**  
> Acquire a trusted Windows Authenticode Code-Signing Certificate (EV Hardware Token, HSM, or Cloud HSM such as Azure Trusted Signing / DigiCert ONE). Current release binaries are functional but unsigned.

---

## 1. Binaries Requiring Code-Signing

AlgoFortis relies on a two-phase signing sequence. The third-party Microsoft WebView2 libraries (`Microsoft.Web.WebView2.Core.dll`, `Microsoft.Web.WebView2.WinForms.dll`, `WebView2Loader.dll`) are already validly signed by Microsoft Corporation and must **not** be re-signed.

The following first-party binaries must be signed:

| Binary Relative Path | Description | Signing Stage |
| :--- | :--- | :--- |
| `build\stage\AlgoFortis.exe` | Native desktop launcher & window coordinator | **Stage 1:** Immediately after C# compilation, before Inno Setup packaging |
| `build\installer\AlgoFortis-Setup.exe` | Inno Setup Windows installer bundle | **Stage 2:** Immediately after Inno Setup compiler generation |

---

## 2. Certificate Requirements

1. **Certificate Type:** Windows Authenticode X.509 Code-Signing Certificate.
2. **Validation Level:** **Extended Validation (EV)** is strongly recommended.
   - *EV Certificate:* Provides immediate or accelerated Microsoft Defender SmartScreen reputation.
   - *Standard OV Certificate:* Functional, but users will encounter Defender SmartScreen "Windows protected your PC" warnings until sufficient global download volume and reputation accumulate.
3. **Key Storage Standard:** CA/Browser Forum rules require code-signing private keys to be stored on FIPS 140-2 Level 2 (or higher) cryptographic hardware:
   - Physical USB Token (e.g., SafeNet eToken 5110 FIPS, YubiKey FIPS).
   - Cloud Key Management Service / HSM (e.g., Azure Trusted Signing, DigiCert KeyLocker, Sectigo Keyfactor, AWS CloudHSM).
4. **Signature Algorithm:** RSA (minimum 3072-bit or 4096-bit key length) or ECC (NIST P-256 / P-384), signed with SHA-256 (`SHA256withRSA`).

---

## 3. Secure Private-Key Handling Rules

1. **Zero Secret Storage in Repository:** Private keys, PFX files, token passwords, or cloud client secrets must **never** be committed to git or stored in the repository.
2. **Dedicated Build Environment:** Signing operations must occur on a secure, hardened administrator workstation or via a dedicated CI/CD runner equipped with access to the hardware token or cloud HSM.
3. **No Unattended Tokens:** Physical USB tokens must be disconnected when signing is not actively taking place.
4. **Access Control:** Only the designated Super Owner (`OWNER-001`) or authorized release engineer may authorize signing requests.

---

## 4. Signing Sequence & Commands

Signing must strictly occur in the following two-step order because `AlgoFortis.exe` is packaged inside `AlgoFortis-Setup.exe`.

### Step 1: Compile and Stage Application
```powershell
powershell.exe -ExecutionPolicy Bypass -File "build\tools\stage_app.ps1"
```

### Step 2: Sign Staged Launcher (`AlgoFortis.exe`)
Using `signtool.exe` from the Windows SDK:

```powershell
# Using USB Token / Installed Hardware Certificate:
signtool.exe sign /v `
  /n "AlgoFortis" `
  /fd SHA256 `
  /tr http://timestamp.digicert.com `
  /td SHA256 `
  "build\stage\AlgoFortis.exe"

# Alternatively, using Azure Trusted Signing:
# Invoke-TrustedSigning -Endpoint ... -File "build\stage\AlgoFortis.exe"
```

Verify signature immediately:
```powershell
Get-AuthenticodeSignature "build\stage\AlgoFortis.exe" | Format-List
```
Ensure `Status : Valid`.

### Step 3: Build Installer
Compile `build\installer\AlgoFortis-Setup.exe` with Inno Setup Compiler (`iscc.exe`):
```powershell
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" "installer\algofortis.iss"
```

### Step 4: Sign Installer (`AlgoFortis-Setup.exe`)
```powershell
signtool.exe sign /v `
  /n "AlgoFortis" `
  /fd SHA256 `
  /tr http://timestamp.digicert.com `
  /td SHA256 `
  "build\installer\AlgoFortis-Setup.exe"
```

---

## 5. Timestamping Requirements

- **Requirement:** Every signature MUST include an RFC 3161 compliant cryptographic timestamp.
- **Purpose:** Ensures the signature remains valid and trusted even after the code-signing certificate expires.
- **Approved Timestamp Authorities (TSA):**
  - DigiCert: `http://timestamp.digicert.com`
  - Sectigo: `http://timestamp.sectigo.com`
- **Digest Algorithm:** `/td SHA256` (Do not use SHA-1).

---

## 6. Post-Signing Verification Procedure

Execute the following verification script on the signed binaries:

```powershell
$binaries = @(
    "build\stage\AlgoFortis.exe",
    "build\installer\AlgoFortis-Setup.exe"
)

foreach ($file in $binaries) {
    Write-Host "Verifying: $file"
    $sig = Get-AuthenticodeSignature $file
    if ($sig.Status -ne "Valid") {
        Write-Error "Signature verification FAILED for $file (Status: $($sig.Status))"
        exit 1
    }
    Write-Host "  Signer: $($sig.SignerCertificate.Subject)"
    Write-Host "  Status: $($sig.Status)"
    Write-Host "  Timestamped: $(if ($sig.TimeStamperCertificate) { 'YES' } else { 'NO' })"
}
```

Detailed SDK verification:
```cmd
signtool.exe verify /pa /v "build\installer\AlgoFortis-Setup.exe"
```

---

## 7. Microsoft Defender SmartScreen Expectations

1. **Initial Beta Window:** If an EV certificate is used, SmartScreen warnings are typically bypassed immediately or within a minimal testing sample.
2. **If Standard OV Certificate is Used:** Beta testers may see:
   > *"Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."*
   Testers must be instructed to click **More info** → **Run anyway**.
3. **Reputation Growth:** SmartScreen reputation builds automatically as unique Windows Defender telemetry records installations across diverse endpoints without malware flags.

---

## 8. Certificate Renewal Procedure

1. **Timeline:** Initiate certificate renewal 30 to 45 days prior to expiration.
2. **Zero Invalidation of Prior Releases:** Existing releases signed with a valid RFC 3161 timestamp continue to run and install with zero warnings even after the signing certificate expires.
3. **New Certificate Validation:** The newly renewed certificate must be verified on a test binary before signing production releases.

---

## 9. Release Hash Handling (Pre-Sign vs. Post-Sign)

> [!WARNING]
> Signing a binary modifies its PE header and appends a Digital Signature table (`IMAGE_DIRECTORY_ENTRY_SECURITY`). This fundamentally changes the binary's cryptographic SHA-256 digest.

1. **Pre-Sign Hashes:** Recorded in internal build logs (`clean_build_manifest.json`) for source compilation verification.
2. **Post-Sign Hashes:** Must be recalculated and recorded in `docs/releases/ALGOfORTIS_LOCAL_V1_RC1_SHA256.txt` (or external beta distribution manifest) as the authoritative user-facing hashes.
3. **Integrity Rule:** Once signed and published, the installer binary hash must never change.
