# One-time setup

The code can run unattended in GitHub Actions, but three external services require account-owner authorization once.

## 1. OpenAI API

A ChatGPT subscription and API billing are separate. Create an OpenAI API key and keep it private. Later add it to the GitHub repository as an Actions secret named `OPENAI_API_KEY`.

## 2. Pexels (recommended, free)

Create a Pexels account, request an API key, and add it as the GitHub Actions secret `PEXELS_API_KEY`. If you skip this, the renderer still works but uses a simple fallback background instead of stock clips.

## 3. Google / YouTube APIs

In Google Cloud Console:

1. Create a project for YouTube Autopilot.
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Configure the OAuth consent screen. If the app is in testing, add the Google account that owns your YouTube channel as a test user. For unattended publishing, check **Google Auth Platform → Audience → Publishing status**. An external app left in **Testing** receives YouTube refresh tokens that expire after seven days. Move the app to **In production** through Google's normal publishing and verification process, if eligible, before expecting durable authorization. Changing this status does not renew an already expired token.
4. Create an OAuth client ID of type **Desktop app**.
5. Download the JSON file and save it locally as `secrets/client_secret.json`. Never commit it.

Then on your Windows PC, from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m autopilot.cli doctor
python -m autopilot.cli auth-youtube
```

A Google browser page will open. Sign in with the channel-owner Google account and approve the requested YouTube upload/read-only analytics permissions. The program writes `secrets/youtube_token.json` locally.

## 4. Add OAuth files to GitHub Secrets safely

Do **not** upload the JSON files to the repository. Encode each locally and copy the encoded value to GitHub Actions secrets:

```powershell
.\scripts\encode_secret.ps1 secrets\client_secret.json
```

Paste the clipboard value into a repository secret named `YOUTUBE_CLIENT_SECRETS_B64`.

Then:

```powershell
.\scripts\encode_secret.ps1 secrets\youtube_token.json
```

Paste that into a repository secret named `YOUTUBE_TOKEN_B64`.

The repository should then have these four Actions secrets:

- `OPENAI_API_KEY`
- `PEXELS_API_KEY` (recommended)
- `YOUTUBE_CLIENT_SECRETS_B64`
- `YOUTUBE_TOKEN_B64`

## 5. First safe cloud test

The daily workflow defaults to `private` uploads. Open the **Actions** tab, choose **Daily YouTube Autopilot**, and use **Run workflow** once. Review the private video in YouTube Studio before allowing any broader visibility.

New unverified YouTube API projects can be restricted to private uploads until Google completes the required API compliance audit. Do not set public mode as a workaround.

## 6. Later: public publishing

After you are satisfied with several private test videos and your Google API project/channel is permitted to publish as intended, set repository variables:

- `UPLOAD_PRIVACY_STATUS=public`
- `ALLOW_PUBLIC_UPLOADS=true`

Until both are set, the code refuses public publishing.

## CurioAxiom Phase 4 authorization

CurioAxiom reuses the same OAuth Desktop application, but it must have a different channel token.
After pulling the latest repository on the machine that contains `secrets/client_secret.json`, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_curioaxiom.ps1
```

Google will ask for authorization once. Select CurioAxiom. The script verifies the exact channel ID
before it installs `CURIOAXIOM_YOUTUBE_TOKEN_B64` or starts the private test. A ByteVexa token fails
closed and is never installed as the CurioAxiom token.

## Recover expired YouTube authorization

If Actions reports `invalid_grant: Token has been expired or revoked`, the account owner must renew each channel separately. In `C:\Users\Lenovo\Documents\youtube-autopilot`, update the local checkout, then run these commands **one at a time**, waiting for each browser flow and script to finish:

```powershell
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\scripts\setup_cloud.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\setup_curioaxiom.ps1
```

Select **ByteVexa** during the first flow and **CurioAxiom** during the second. The scripts verify the exact channel identity before replacing either GitHub Actions token secret. If the local token file is missing, `auth-youtube` opens the browser; do not copy tokens into chat or commit them. If Google Cloud still shows **Testing**, reauthorization will likely need to be repeated in seven days. Check Google's [OAuth refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2) and [publishing-status guidance](https://support.google.com/cloud/answer/15549945) before changing app status; YouTube scopes may require verification. A code retry cannot restore an expired refresh token.
